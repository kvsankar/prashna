"""The `prashna` command: run Prashna on this computer (UC-X-15).

    prashna                    start on http://127.0.0.1:8000 and open the browser
    prashna --port 8080        use another port
    prashna --data-dir DIR     keep the database and uploads in DIR
    prashna backup create F    archive the data folder (see `prashna backup --help`)
    prashna --tunnel cloudflare  also reach it from the internet (or: --tunnel ngrok)

Data lives in the per-user app-data folder unless --data-dir or
PRASHNA_DATA_DIR says otherwise. An explicit --data-dir wins over
PRASHNA_DB_PATH and PRASHNA_UPLOADS_DIR. On the first run the browser
opens the one-time setup page, so creating the admin needs no
copy-and-paste.
"""
from __future__ import annotations

import argparse
import os
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from importlib import metadata
from pathlib import Path


def _version() -> str:
    try:
        return metadata.version("prashna")
    except metadata.PackageNotFoundError:
        return "0+unknown"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prashna", description="Live Q&A and quizzes for any session with an audience.")
    parser.add_argument("--host", default="127.0.0.1",
                        help="address to listen on (default 127.0.0.1; 0.0.0.0 to allow other devices)")
    parser.add_argument("--port", type=int, default=8000, help="port to listen on (default 8000)")
    parser.add_argument("--data-dir", help="folder for the database and uploads "
                        "(default: PRASHNA_DATA_DIR or your app-data folder); "
                        "when given, PRASHNA_DB_PATH and PRASHNA_UPLOADS_DIR are ignored")
    parser.add_argument("--no-browser", action="store_true", help="don't open the browser")
    parser.add_argument("--tunnel", choices=["cloudflare", "ngrok"],
                        help="also make Prashna reachable from the internet: a Cloudflare quick "
                             "tunnel (needs cloudflared, no account) or ngrok (needs a signed-in ngrok)")
    parser.add_argument("--version", action="version", version=f"prashna {_version()}")
    commands = parser.add_subparsers(dest="command")
    reset = commands.add_parser("reset-password", help="set a new password for the admin (when it is forgotten)")
    # Accept --data-dir after the subcommand too; SUPPRESS keeps a value given
    # before the subcommand from being reset to None.
    reset.add_argument("--data-dir", default=argparse.SUPPRESS, help="folder holding the database")
    backup = commands.add_parser("backup", add_help=False, help="create or restore a backup of the data folder")
    backup.add_argument("args", nargs=argparse.REMAINDER)
    return parser


def _data_dir(arg: str | None) -> Path:
    chosen = arg or os.environ.get("PRASHNA_DATA_DIR")
    if chosen:
        return Path(chosen).expanduser().resolve()
    from .db import default_data_dir
    return default_data_dir()


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET6 if ":" in host else socket.AF_INET) as sock:
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _launch_browser(url: str) -> None:
    """Open `url`. A BROWSER setting (the usual way to choose a browser) is
    launched directly: webbrowser's discovery of every installed browser can
    take several seconds on Linux desktops before it tries BROWSER."""
    for entry in filter(None, os.environ.get("BROWSER", "").split(os.pathsep)):
        command = entry.replace("%s", url) if "%s" in entry else f"{entry} {shlex.quote(url)}"
        try:
            subprocess.Popen(shlex.split(command))
            return
        except OSError:
            continue
    webbrowser.open(url)


def _open_when_ready(host: str, port: int, url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.2)
    _launch_browser(url)


def _plural(count: int, noun: str, plural: str | None = None) -> str:
    return f"{count} {noun if count == 1 else plural or noun + 's'}"


def _summarize(session) -> tuple[str, str | None]:
    """What an existing database holds, and the admin to sign in as when
    there is exactly one password admin."""
    from sqlalchemy import func, select

    from . import models as m
    admins = session.execute(select(m.User.username, m.User.password_hash)).all()
    sessions = session.scalar(select(func.count()).select_from(m.Session)) or 0
    quizzes = session.scalar(select(func.count()).select_from(m.Quiz)) or 0
    names = ", ".join(name for name, _ in admins[:3]) + (", ..." if len(admins) > 3 else "")
    who = f"{_plural(len(admins), 'admin')} ({names})" if admins else "no admin yet"
    password_admins = [name for name, password_hash in admins if password_hash]
    sign_in_as = password_admins[0] if len(admins) == 1 and password_admins else None
    return f"{who}, {_plural(sessions, 'session')}, {_plural(quizzes, 'quiz', 'quizzes')}", sign_in_as


def _read_new_password() -> tuple[str, str]:
    if sys.stdin.isatty():
        import getpass
        return getpass.getpass("New password: "), getpass.getpass("Repeat it: ")
    lines = sys.stdin.read().splitlines() + ["", ""]
    return lines[0], lines[1]


def _reset_password(db_path: Path) -> int:
    """`prashna reset-password`: set a new admin password from the machine
    that holds the data folder (UC-X-15). Existing sign-ins stay valid."""
    if not db_path.is_file() or db_path.stat().st_size == 0:
        print(f"No Prashna database in {db_path.parent}.", file=sys.stderr)
        return 1
    from sqlalchemy import select

    from . import auth, db
    from . import models as m
    from .main import MIN_PASSWORD_LEN
    with db.SessionLocal() as session:
        admins = session.scalars(select(m.User).where(m.User.password_hash != "")).all()
        if not admins:
            print("No admin yet. Start `prashna` and create one with the setup link it shows.", file=sys.stderr)
            return 1
        if len(admins) > 1:
            names = ", ".join(a.username for a in admins)
            print(f"More than one admin ({names}); this command expects one.", file=sys.stderr)
            return 1
        admin = admins[0]
        first, second = _read_new_password()
        if first != second:
            print("The two passwords did not match. Nothing changed.", file=sys.stderr)
            return 1
        if len(first) < MIN_PASSWORD_LEN:
            print(f"The password must be at least {MIN_PASSWORD_LEN} characters. Nothing changed.", file=sys.stderr)
            return 1
        try:
            admin.password_hash = auth.hash_password(first)
        except ValueError:  # longer than bcrypt's 72 bytes
            print(f"The password must be at most {auth.MAX_PASSWORD_BYTES} bytes. Nothing changed.", file=sys.stderr)
            return 1
        session.commit()
        print(f"Password changed for {admin.username}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    data_dir = _data_dir(args.data_dir)
    # Set before the server modules are imported; they read these at import.
    # An explicit --data-dir wins for every file; otherwise PRASHNA_DB_PATH and
    # PRASHNA_UPLOADS_DIR, when set, win over the data folder (UC-X-15).
    for name, path in (("PRASHNA_DB_PATH", data_dir / "prashna.db"),
                       ("PRASHNA_UPLOADS_DIR", data_dir / "uploads")):
        if args.data_dir or not os.environ.get(name):
            os.environ[name] = str(path)
    if args.command == "reset-password":
        return _reset_password(Path(os.environ["PRASHNA_DB_PATH"]))
    data_dir.mkdir(parents=True, exist_ok=True)

    if args.command == "backup":
        from .backup import main as backup_main
        return backup_main(args.args)

    if not _port_free(args.host, args.port):
        print(f"Port {args.port} is already in use. Start on another port, "
              f"for example: prashna --port {args.port + 1}", file=sys.stderr)
        return 1

    db_path = Path(os.environ["PRASHNA_DB_PATH"])
    db_existed = db_path.is_file() and db_path.stat().st_size > 0
    from . import auth, db, diagnostics
    diagnostics.send_to_file(data_dir / "prashna.log")
    db.init_db()
    with db.SessionLocal() as session:
        token = auth.setup_token(session)
        holdings, sign_in_as = _summarize(session)
    shown_host = "127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host
    address = f"http://{shown_host}:{args.port}"
    url = f"{address}/#setup={token}" if token else f"{address}/"

    tunnel = None
    public_url = None
    if args.tunnel:
        from .tunnel import PROGRAMS, Tunnel, TunnelError
        print(f"Starting the {PROGRAMS[args.tunnel]} tunnel...", flush=True)
        try:
            tunnel = Tunnel(args.tunnel, args.port, shown_host)
            public_url = tunnel.wait_for_url()
        except TunnelError as error:
            print(error, file=sys.stderr)
            return 1
        if args.tunnel == "cloudflare":
            from .tunnel import wait_until_resolvable
            print("Waiting for the public address to come online (about 15 seconds)...", flush=True)
            wait = float(os.environ.get("PRASHNA_TUNNEL_DNS_WAIT_SECS") or 60)
            if not wait_until_resolvable(public_url, wait):
                print("The public address may need a little longer before it works.", flush=True)
        tunnel.on_unexpected_exit = lambda: print(
            "\nThe tunnel stopped. Participants can no longer reach Prashna; "
            "restart Prashna to get a new address.", file=sys.stderr, flush=True)

    print(f"\nPrashna is running at {address}")
    if public_url:
        print(f"Participants join at: {public_url}")
    print(f"Data folder: {data_dir}")
    if db_existed:
        print(f"Using existing data: {db_path} ({holdings})")
    else:
        print(f"Created a new database: {db_path}")
    if not token:
        who = f"as {sign_in_as}" if sign_in_as else "with your admin account"
        print(f"Sign in at {address}/ {who}." + ("" if args.no_browser else " Opening it in your browser."))
    if token:
        if args.no_browser:
            print(f"Create your admin account here (one-time link): {url}")
        else:
            print("Opening the one-time setup page in your browser to create your admin account.")
    print("Press Ctrl+C to stop.\n", flush=True)
    if not args.no_browser:
        threading.Thread(target=_open_when_ready, args=(shown_host, args.port, url), daemon=True).start()

    import uvicorn

    from . import main as server
    server.ANNOUNCE_SETUP_LINK = False
    server.PUBLIC_URL = public_url
    if tunnel:
        # uvicorn re-raises SIGINT/SIGTERM after shutting down, which ends the
        # process before `finally` runs; it calls these handlers when it does.
        # Each hands over to the handler that was installed before it, so
        # default behaviour (and any tool watching the process) is kept.
        previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}

        def stop_tunnel_then_continue(signum: int, _frame: object) -> None:
            assert tunnel is not None
            tunnel.stop()
            signal.signal(signum, previous[signal.Signals(signum)])
            signal.raise_signal(signum)

        for sig in previous:
            signal.signal(sig, stop_tunnel_then_continue)
    try:
        uvicorn.run(server.app, host=args.host, port=args.port, log_level="warning")
    finally:
        if tunnel:
            tunnel.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
