"""Choose a single observed publishing control for the worker holding the command."""
import json
import time

from . import model
from .batch_cancellation import check as check_cancelled
from .policy import local_day, now_iso
from .readiness import web_block_reason
from .runtime_resume import _options
from .workspace_execution import check_running

CONTROLS = {'entry': '首页发布入口（＋）', 'tab': '上传图文页签', 'upload': '图像文件输入框',
            'fill': '标题与正文编辑框', 'submit': '可用的发布按钮'}


def choose(store, body):
    controls = body.get('controls')
    if (not isinstance(controls, list) or not 1 <= len(controls) <= len(CONTROLS)
            or any(not isinstance(key, str) or key not in CONTROLS for key in controls)
            or len(set(controls)) != len(controls)):
        raise ValueError('网页控件列表无效')
    turn = body.get('turn')
    if type(turn) is not int or not 1 <= turn <= len(CONTROLS):
        raise ValueError('发布决策步数超出范围')
    version, policy = store.policy()
    with store.connection() as db:
        cmd = db.execute("SELECT payload FROM commands WHERE id=? AND worker=? AND kind='publish' "
                         "AND state='running' AND expires>?", (body['command_id'], body['worker'], time.time())).fetchone()
        if not cmd:
            raise ValueError('发布任务未在当前执行窗口运行')
        payload = json.loads(cmd['payload'])
        if policy.get('publish_method') != 'computer_use' or version != payload['policy_version']:
            raise ValueError('发布方式或规则已变更')
        check_running(store, web=True, db=db)
        if web_block_reason(db):
            raise ValueError('网页已由人工接管')
        store.manual_run_id = payload.get('manual_run_id')
        store.current_run_id = payload.get('run_id')
        check_cancelled(store, db=db, batch=store.manual_run_id)
        # A delayed HTTP retry cannot spend the model budget twice for the same observation.
        marker = f"publish-decision:{body['command_id']}:{turn}"
        claimed = db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'publish_decision', '{}', ?)",
                             (marker, now_iso())).rowcount
        if not claimed:
            raise ValueError('这一步发布决策已请求过')
    store.run_options = _options(store, store.manual_run_id)
    if (store.manual_run_id or '').startswith('debug:'):
        store.debug_id = store.manual_run_id
    answer = model.generate(store, policy, local_day(policy),
                            '在当前可用控件中选择下一步以发布已授权的小红书图文。可直接上传图片时优先上传。'
                            '仅返回 {"action":"控件键"}。无法确认时返回 {"action":"stop"}。',
                            {'controls': {key: CONTROLS[key] for key in controls}})
    action = answer.get('action') if isinstance(answer, dict) else None
    if action not in controls:
        raise ValueError('模型未选择当前可用的发布控件，已停止')
    return {'action': action}
