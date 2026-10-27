"""Rehearsal launcher: start every device in the config on THIS machine, each
as its own process with its own sockets. For the real thing, run
``python -m story.node --id <ID>`` on each laptop instead.

    python -m story.local            # starts L1..L5, opens L1 and L5 in the browser
    python -m story.local --no-browser
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from .node import lan_ip, load_config


def main() -> None:
    parser = argparse.ArgumentParser(description="Start every EcoMesh device on this machine")
    parser.add_argument("--config", default=str(Path(__file__).with_name("mesh.json")))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--only", help="comma-separated device ids to start on this machine, e.g. L1,L2,L3")
    parser.add_argument("--secret")
    parser.add_argument("--sign", action="store_true")
    parser.add_argument("--phone", action="store_true",
                        help="serve the screens on every interface so a phone on the same Wi-Fi can open them")
    args = parser.parse_args()
    web_host = "0.0.0.0" if args.phone else "127.0.0.1"

    cfg = load_config(args.config)
    mine = [i.strip() for i in args.only.split(",")] if args.only else list(cfg["nodes"])
    unknown = [i for i in mine if i not in cfg["nodes"]]
    if unknown:
        raise SystemExit(f"unknown device(s) {unknown}; config has {sorted(cfg['nodes'])}")
    procs = []
    for node_id in mine:
        cmd = [sys.executable, "-m", "story.node", "--id", node_id, "--config", args.config, "--web-host", web_host]
        if args.secret:
            cmd += ["--secret", args.secret]
        if args.sign:
            cmd += ["--sign"]
        procs.append(subprocess.Popen(cmd))
    print("\n  Started", ", ".join(mine), "as separate processes. Ctrl+C stops them all.\n")
    for node_id in mine:
        spec = cfg["nodes"][node_id]
        phone = f"   phone: http://{lan_ip()}:{spec['web']}" if args.phone else ""
        print(f"  {spec['label']:<16} http://127.0.0.1:{spec['web']}{phone}")
    try:
        if not args.no_browser:
            time.sleep(4)
            for node_id in dict.fromkeys((mine[0], mine[-1])):
                webbrowser.open(f"http://127.0.0.1:{cfg['nodes'][node_id]['web']}")
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        pass
    finally:
        for p in procs:
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
