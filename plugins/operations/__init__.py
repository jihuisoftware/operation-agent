"""Operations business plugin; no state or scheduler is started at import time."""
import json


def register(ctx):
    from .cli import configure, main
    ctx.register_cli_command(name="ops", help="每日自动运营", setup_fn=configure, handler_fn=main)
    ctx.register_tool(
        name="operations_status", toolset="operations",
        schema={"name": "operations_status", "description": "读取运营目标、任务、来源和日报；运营授权在工作台配置。",
                "parameters": {"type": "object", "properties": {"business_id": {"type": "string"}, "topic_id": {"type": "string"}}}},
        handler=status)


def status(args, **kwargs):
    from .workspaces import Workspaces
    directory = Workspaces()
    catalog = directory.catalog()
    scoped = args.get('business_id') or args.get('topic_id') or len([t for t in catalog['topics'] if not t['archived']]) == 1
    value = directory.store(args.get('business_id'), args.get('topic_id')).snapshot() if scoped else catalog
    return json.dumps(value, ensure_ascii=False)
