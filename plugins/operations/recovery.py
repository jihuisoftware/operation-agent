"""Read-only restart reconciliation. No resubmission is performed here."""
import json
from datetime import datetime, UTC
from .policy import now_iso
from .store import encoded


def reconcile_pending(store, policy, day, now=None):
    from .workflow import browser
    now = now or datetime.now(UTC)
    history = store.objects("reconciliation", day)
    attempted = 0
    with store.connection() as db:
        pending = [dict(row) for row in db.execute("SELECT * FROM actions WHERE state IN ('unknown','submitted') ORDER BY created")]
    for row in pending:
        attempts = [r for r in history if r["action_id"] == row["id"]]
        if len(attempts) >= 3 or any((now - datetime.fromisoformat(r["started"])).total_seconds() < 300 for r in attempts):
            continue
        action, previous = json.loads(row["data"]), json.loads(row["result"])
        if policy["account_id"] and action["account_id"] != policy["account_id"]:
            continue
        if attempted >= 5:
            break
        attempted += 1
        identity = f"reconcile:{day}:{row['id']}:{len(attempts) + 1}"
        store.put("reconciliation", {"day": day, "action_id": row["id"], "started": now.isoformat()}, identity)
        try:
            result = browser(store, "verify", {**action, "result_url": previous.get("url")})
        except (ValueError, TimeoutError) as exc:
            store.event("reconciliation_error", {"day": day, "action_id": row["id"], "error": str(exc)})
            continue
        store.event("reconciliation", {"day": day, "action_id": row["id"], "result": result})
        if result.get("state") not in {"confirmed", "published"} or not result.get("evidence"):
            continue
        with store.connection() as db:
            db.execute("UPDATE actions SET state=?,result=? WHERE id=? AND state IN ('unknown','submitted')",
                       (result["state"], encoded({**result, "verified_at": now_iso(), "verified_by": "page"}), row["id"]))
