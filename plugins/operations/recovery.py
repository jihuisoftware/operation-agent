"""Read-only restart reconciliation. No resubmission is performed here."""
import json
from .policy import now_iso
from .store import encoded


def reconcile_pending(store, policy, day):
    from .workflow import browser
    with store.connection() as db:
        pending = [dict(row) for row in db.execute("SELECT * FROM actions WHERE state IN ('unknown','submitted') ORDER BY created LIMIT 5")]
    for row in pending:
        identity = f"reconcile:{day}:{row['id']}"
        if any(r["id"] == identity for r in store.objects("reconciliation", day)):
            continue
        action, previous = json.loads(row["data"]), json.loads(row["result"])
        if policy["account_id"] and action["account_id"] != policy["account_id"]:
            continue
        store.put("reconciliation", {"day": day, "action_id": row["id"], "started": now_iso()}, identity)
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
