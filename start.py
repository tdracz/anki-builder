#!/usr/bin/env python3
"""
Cross-platform launcher.
Builds the frontend (if needed), starts the FastAPI server, and opens the browser.

Usage:
    python start.py
    python start.py --port 8000
    python start.py --no-browser
"""

import argparse
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"
DIST = FRONTEND / "dist"


def build_frontend():
    if not DIST.exists() or not list(DIST.glob("*.html")):
        print("Building frontend…")
        result = subprocess.run(["npm", "run", "build"], cwd=FRONTEND)
        if result.returncode != 0:
            print("Frontend build failed.", file=sys.stderr)
            sys.exit(1)
        print("Frontend built.")
    else:
        print("Frontend already built (dist/ exists).")


def main():
    parser = argparse.ArgumentParser(description="Start the Vocab Builder app.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="Force frontend rebuild")
    args = parser.parse_args()

    if args.rebuild and DIST.exists():
        import shutil
        shutil.rmtree(DIST)

    build_frontend()

    url = f"http://localhost:{args.port}/app"

    if not args.no_browser:
        def _open():
            time.sleep(1.5)
            webbrowser.open(url)
        threading.Thread(target=_open, daemon=True).start()

    print(f"\nStarting server at {url}\nPress Ctrl+C to stop.\n")

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=args.port,
        reload=False,
    )


if __name__ == "__main__":
    main()
