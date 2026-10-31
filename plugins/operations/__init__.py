"""Operations business plugin; no state or scheduler is started at import time."""
import json


def register(ctx):
    from .cli import configure, main
    from .store import Store
    ctx.register_cli_command(name="ops", help="每日自动运营", setup_fn=configure, handler_fn=main)
    ctx.register_tool(
        name="operations_status", toolset="operations",
        schema={"name": "operations_status", "description": "读取运营目标、任务、来源和日报；运营授权在工作台配置。",
                "parameters": {"type": "object", "properties": {}}},
        handler=lambda args, **kw: json.dumps(Store().snapshot(), ensure_ascii=False))
