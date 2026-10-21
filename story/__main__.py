"""One-page EcoMesh demo for non-technical viewers.

    python -m story                  # http://127.0.0.1:8000
    python -m story --host 0.0.0.0   # reachable from a phone on the same Wi-Fi

Runs the same engine and API as ``python -m api.server`` (five-node demo
preset) but serves ``story/index.html`` instead of the full React site.
"""

from __future__ import annotations

import argparse
import socket
from pathlib import Path

import uvicorn
from fastapi.responses import FileResponse

from api.server import create_app

PAGE = Path(__file__).with_name("index.html")


def _lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="EcoMesh one-page story demo")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    app = create_app(initial_preset="demo5", serve_ui=False)

    @app.get("/", include_in_schema=False)
    async def index():
        return FileResponse(PAGE)

    shown = _lan_ip() if args.host == "0.0.0.0" else args.host
    print(f"\n  EcoMesh story demo:  http://{shown}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
