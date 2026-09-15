from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path


def _runtime_dir() -> Path:
    frozen_dir = getattr(sys, "_MEIPASS", None)
    if frozen_dir:
        return Path(frozen_dir).resolve()
    return Path(__file__).resolve().parent


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _log(message: str) -> None:
    log_path = os.environ.get("OKINAWA_DESKTOP_LOG", "").strip()
    if not log_path:
        return
    try:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except Exception:
        pass


def _server_is_ready(url: str) -> bool:
    for candidate in (f"{url}/_stcore/health", url):
        try:
            with urllib.request.urlopen(candidate, timeout=1.5) as response:
                if 200 <= response.status < 500:
                    return True
        except Exception:
            continue
    return False


def _wait_for_server(url: str, *, open_browser: bool) -> None:
    for _ in range(240):
        if _server_is_ready(url):
            _log(f"Server ready: {url}")
            if open_browser:
                webbrowser.open(url, new=1)
            return
        time.sleep(0.25)
    _log(f"Server readiness timeout: {url}")


def _run_streamlit(app_script: Path, port: int) -> None:
    # Packaged Streamlit can otherwise auto-detect development mode and reject a
    # custom server.port. Force production-style local server configuration.
    os.environ["STREAMLIT_GLOBAL_DEVELOPMENT_MODE"] = "false"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_ADDRESS"] = "127.0.0.1"
    os.environ["STREAMLIT_SERVER_PORT"] = str(port)
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"

    sys.argv = [
        "streamlit",
        "run",
        str(app_script),
        "--global.developmentMode=false",
        "--server.address=127.0.0.1",
        f"--server.port={port}",
        "--server.headless=true",
        "--server.fileWatcherType=none",
        "--browser.gatherUsageStats=false",
    ]

    from streamlit.web.cli import main as streamlit_main

    _log(f"Starting Streamlit on 127.0.0.1:{port}; app={app_script}")
    streamlit_main()


def main() -> int:
    parser = argparse.ArgumentParser(description="Safe Excel Transfer desktop launcher")
    parser.add_argument("--port", type=int, default=0, help="fixed local port for smoke tests")
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    runtime_dir = _runtime_dir()
    app_script = runtime_dir / "app.py"
    if not app_script.is_file():
        raise FileNotFoundError(f"Application file is missing: {app_script}")

    os.chdir(runtime_dir)
    port = args.port if args.port > 0 else _free_port()
    url = f"http://127.0.0.1:{port}"

    threading.Thread(
        target=_wait_for_server,
        kwargs={"url": url, "open_browser": not args.no_browser},
        daemon=True,
    ).start()

    _run_streamlit(app_script, port)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit as exc:
        _log(f"Launcher exited with code: {exc.code}")
        raise
    except BaseException:
        _log("Launcher failed:\n" + traceback.format_exc())
        raise
