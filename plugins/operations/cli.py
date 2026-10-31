"""CLI and Desktop share the same service and records."""
import json
from pathlib import Path
from .store import Store


def configure(parser):
    parser.add_argument("action", choices=["status", "tick", "configure", "pause", "resume", "report"])
    parser.add_argument("--file")
    parser.add_argument("--day")


def _configure(store, args):
    from .runtime import ensure_schedule
    if not args.file:
        raise ValueError("configure 需要 --file JSON配置文件")
    value = json.loads(Path(args.file).read_text(encoding="utf-8-sig"))
    store.configure(value, store.policy()[0])
    if value.get("enabled"):
        ensure_schedule(store)


def _pause(store, args):
    version, policy = store.policy()
    store.configure({**policy, "paused": args.action == "pause"}, version)


def _report(store, args):
    from .report import daily_report
    from .policy import local_day
    return daily_report(store, args.day or local_day(store.policy()[1]))["markdown"]


def main(args):
    from .runtime import tick
    store = Store()
    handlers = {
        "configure": _configure, "pause": _pause, "resume": _pause,
        "tick": lambda store, args: tick(store), "report": _report,
        "status": lambda store, args: json.dumps(store.snapshot(), ensure_ascii=False, indent=2),
    }
    result = handlers[args.action](store, args)
    if result is not None:
        print(result)
