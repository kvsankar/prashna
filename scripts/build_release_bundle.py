"""Build version-pinned Prashna Compose release archives."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ROOT / "compose.yaml": "compose.yaml",
    ROOT / "compose.env.example": "compose.env.example",
    ROOT / "distribution" / "README.md": "README.md",
}


def _validate_version(version: str) -> None:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("version must be numeric MAJOR.MINOR.PATCH")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_bundle(version: str, output_dir: Path) -> list[Path]:
    _validate_version(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    bundle_name = f"prashna-{version}"
    with tempfile.TemporaryDirectory(prefix="prashna-release-") as temp:
        bundle = Path(temp) / bundle_name
        bundle.mkdir()
        for source, relative in FILES.items():
            target = bundle / relative
            shutil.copy2(source, target)

        compose = bundle / "compose.yaml"
        compose.write_text(
            compose.read_text(encoding="utf-8").replace(
                "${PRASHNA_IMAGE_TAG:-latest}",
                f"${{PRASHNA_IMAGE_TAG:-{version}}}",
            ),
            encoding="utf-8",
        )
        env_file = bundle / "compose.env.example"
        env_file.write_text(
            env_file.read_text(encoding="utf-8").replace(
                "PRASHNA_IMAGE_TAG=latest",
                f"PRASHNA_IMAGE_TAG={version}",
            ),
            encoding="utf-8",
        )

        tar_path = output_dir / f"{bundle_name}.tar.gz"
        with tarfile.open(tar_path, "w:gz", format=tarfile.PAX_FORMAT) as archive:
            archive.add(bundle, arcname=bundle_name)

        zip_path = output_dir / f"{bundle_name}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(bundle.rglob("*")):
                if path.is_file():
                    archive.write(path, Path(bundle_name) / path.relative_to(bundle))

    checksums = output_dir / "SHA256SUMS"
    artifacts = [tar_path, zip_path]
    checksums.write_text(
        "".join(f"{_sha256(path)}  {path.name}\n" for path in artifacts),
        encoding="utf-8",
    )
    return [*artifacts, checksums]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    for artifact in build_bundle(args.version, args.output_dir):
        print(artifact)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
