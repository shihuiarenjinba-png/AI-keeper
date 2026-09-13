from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
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


def _wait_for_server(url: str, *, open_browser: bool) -> None:
    health_url = f"{url}/_stcore/health"
    for _ in range(120):
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if response.status == 200:
                    if open_browser:
                        webbrowser.open(url, new=1)
                    return
        except Exception:
            time.sleep(0.25)


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
    os.environ.setdefault("STREAMLIT_BROWSER_GATHER_USAGE_STATS", "false")
    os.environ.setdefault("STREAMLIT_SERVER_HEADLESS", "true")

    port = args.port if args.port > 0 else _free_port()
    url = f"http://127.0.0.1:{port}"
    threading.Thread(
        target=_wait_for_server,
        kwargs={"url": url, "open_browser": not args.no_browser},
        daemon=True,
    ).start()

    from streamlit.web import bootstrap

    flag_options = {
        "server.address": "127.0.0.1",
        "server.port": port,
        "server.headless": True,
        "server.fileWatcherType": "none",
        "browser.gatherUsageStats": False,
    }
    bootstrap.run(str(app_script), False, [], flag_options)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
