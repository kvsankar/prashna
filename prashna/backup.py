"""Create and restore portable Prashna data archives.

This module is intentionally runnable inside the published container so a
Docker-only installation does not need Python or sqlite tooling on the host.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import sqlite3
import sys
import tarfile
import tempfile
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ARCHIVE_FORMAT = 1


def _db_path() -> Path:
    return Path(os.environ.get("PRASHNA_DB_PATH", "/data/prashna.db"))


def _uploads_path() -> Path:
    return Path(os.environ.get("PRASHNA_UPLOADS_DIR", "/app/uploads"))


def _add_bytes(archive: tarfile.TarFile, name: str, payload: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(payload)
    info.mode = 0o600
    info.mtime = 0
    archive.addfile(info, io.BytesIO(payload))


def create_archive(destination: Path) -> Path:
    """Create a consistent SQLite + uploads archive at *destination*."""
    source_db = _db_path()
    uploads = _uploads_path()
    if not source_db.is_file():
        raise RuntimeError(f"database not found: {source_db}")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="prashna-backup-") as temp:
        snapshot = Path(temp) / "prashna.db"
        # closing(): a connection's `with` only commits. The snapshot must be
        # closed before the temporary folder goes, or Windows can't delete it.
        with closing(sqlite3.connect(source_db)) as source, closing(sqlite3.connect(snapshot)) as target:
            source.backup(target)

        manifest = {
            "format": ARCHIVE_FORMAT,
            "created_at": datetime.now(UTC).isoformat(),
            "database": "prashna.db",
            "uploads": "uploads/",
        }
        with tarfile.open(destination, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            _add_bytes(
                archive,
                "manifest.json",
                (json.dumps(manifest, sort_keys=True) + "\n").encode(),
            )
            archive.add(snapshot, arcname="prashna.db", recursive=False)
            if uploads.is_dir():
                for path in sorted(uploads.rglob("*")):
                    if path.is_symlink() or not path.is_file():
                        continue
                    relative = path.relative_to(uploads).as_posix()
                    archive.add(path, arcname=f"uploads/{relative}", recursive=False)
    return destination


def _extract_checked(archive_path: Path, destination: Path) -> None:
    seen: set[str] = set()
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            name = PurePosixPath(member.name)
            if (
                member.name in seen
                or name.is_absolute()
                or ".." in name.parts
                or member.issym()
                or member.islnk()
                or not (
                    member.name in {"manifest.json", "prashna.db"}
                    or (name.parts and name.parts[0] == "uploads")
                )
            ):
                raise RuntimeError(f"unsafe backup member: {member.name}")
            seen.add(member.name)
            if member.isdir():
                (destination / Path(*name.parts)).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                raise RuntimeError(f"unsupported backup member: {member.name}")
            source = archive.extractfile(member)
            if source is None:
                raise RuntimeError(f"cannot read backup member: {member.name}")
            target = destination / Path(*name.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as output:
                shutil.copyfileobj(source, output)

    required = {"manifest.json", "prashna.db"}
    if not required.issubset(seen):
        raise RuntimeError("backup is missing manifest.json or prashna.db")


def _validate_snapshot(snapshot: Path, manifest_path: Path) -> None:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != ARCHIVE_FORMAT:
        raise RuntimeError(f"unsupported backup format: {manifest.get('format')!r}")
    with closing(sqlite3.connect(f"file:{snapshot}?mode=ro", uri=True)) as connection:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise RuntimeError(f"backup database failed quick_check: {result!r}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    if "users" not in tables or "sessions" not in tables:
        raise RuntimeError("backup database is not a Prashna database")


def restore_archive(archive_path: Path, *, confirmed: bool = False) -> Path | None:
    """Restore an archive after creating a sibling pre-restore backup.

    Returns that backup, or None when there was no database to keep (a new
    machine), in which case the restore goes ahead without one.
    """
    if not confirmed:
        raise RuntimeError("restore requires --confirm and a stopped Prashna service")
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        raise RuntimeError(f"backup not found: {archive_path}")

    with tempfile.TemporaryDirectory(prefix="prashna-restore-") as temp:
        extracted = Path(temp)
        _extract_checked(archive_path, extracted)
        snapshot = extracted / "prashna.db"
        _validate_snapshot(snapshot, extracted / "manifest.json")

        pre_restore = None
        if _db_path().is_file():
            stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
            pre_restore = archive_path.with_name(f"prashna-pre-restore-{stamp}.tar.gz")
            create_archive(pre_restore)

        target_db = _db_path()
        target_db.parent.mkdir(parents=True, exist_ok=True)
        staged_db = target_db.with_name(f".{target_db.name}.restore")
        shutil.copy2(snapshot, staged_db)
        os.replace(staged_db, target_db)
        for suffix in ("-wal", "-shm", "-journal"):
            target_db.with_name(target_db.name + suffix).unlink(missing_ok=True)

        uploads = _uploads_path()
        uploads.mkdir(parents=True, exist_ok=True)
        for current in uploads.iterdir():
            if current.is_dir() and not current.is_symlink():
                shutil.rmtree(current)
            else:
                current.unlink()
        restored_uploads = extracted / "uploads"
        if restored_uploads.is_dir():
            for source in restored_uploads.rglob("*"):
                relative = source.relative_to(restored_uploads)
                target = uploads / relative
                if source.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif source.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, target)
    return pre_restore


# The help that `prashna backup --help` and `python -m prashna.backup --help`
# show; written for the people who run Prashna (UC-X-15).
DESCRIPTION = (
    "Copy Prashna's data (the database and the uploaded images) into one "
    "backup file, or put a backup file back. Stop Prashna before you restore."
)


def add_commands(parser: argparse.ArgumentParser) -> None:
    """Add the `create` and `restore` commands to `parser`."""
    commands = parser.add_subparsers(dest="backup_command", required=True, metavar="{create,restore}")
    create = commands.add_parser(
        "create", help="write a backup file",
        description="Write Prashna's database and uploaded images into one backup file. "
                    "Prashna can keep running.")
    create.add_argument("archive", type=Path,
                        help="the backup file to write, for example prashna-backup.tar.gz")
    restore = commands.add_parser(
        "restore", help="put a backup file back (stop Prashna first)",
        description="Replace Prashna's database and uploaded images with the contents of a "
                    "backup file. Stop Prashna first. Before anything is replaced, any current "
                    "data is saved to a prashna-pre-restore-<time>.tar.gz file beside the "
                    "backup file.")
    restore.add_argument("archive", type=Path, help="the backup file to restore")
    restore.add_argument("--confirm", action="store_true",
                         help="confirm that Prashna is stopped and that its current data "
                              "may be replaced; without it, nothing changes")


def run(args: argparse.Namespace) -> int:
    """Carry out a parsed `create` or `restore` command."""
    # A failure is one plain line, not a traceback (UC-X-10).
    if args.backup_command == "create":
        try:
            print(create_archive(args.archive))
        except (RuntimeError, OSError) as exc:
            print(f"Backup failed: {exc}", file=sys.stderr)
            return 1
        return 0
    try:
        pre_restore = restore_archive(args.archive, confirmed=args.confirm)
    except (RuntimeError, OSError, tarfile.TarError, sqlite3.Error, ValueError) as exc:
        print(f"Restore failed: {exc}", file=sys.stderr)
        return 1
    previous = f"previous state: {pre_restore}" if pre_restore else "there was no previous data"
    print(f"restored {args.archive}; {previous}")
    return 0


def main(argv: list[str] | None = None, prog: str | None = None) -> int:
    parser = argparse.ArgumentParser(prog=prog, description=DESCRIPTION)
    add_commands(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main(prog="python -m prashna.backup"))
