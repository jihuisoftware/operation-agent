"""Stage the desktop Python backend; no terminal frontend is required."""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.bundles.native import stage_native


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--cache", type=Path, help="persistent uv build cache")
    args = parser.parse_args(argv)
    args.frontends = {}
    return stage_native(args)


if __name__ == "__main__":
    raise SystemExit(main())
