#!/usr/bin/env python3
"""Standalone dashboard server entry point for background processes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from kimi_swarm.web_dashboard import run_standalone


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--state-path", type=str, default=str(Path.home() / ".kimi" / "kimi-swarm-state.json"))
    args = parser.parse_args()

    run_standalone(port=args.port, state_path=Path(args.state_path))


if __name__ == "__main__":
    main()
