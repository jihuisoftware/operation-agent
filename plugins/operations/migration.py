"""Atomic policy and occurrence migration; old audit rows remain readable."""
import json
import uuid
from .modules import upgrade
from .policy import now_iso


def migrate(db):
    db.execute("BEGIN IMMEDIATE")
    repair_orphan_actions(db)
    row = db.execute("SELECT version,data FROM settings WHERE id=1").fetchone()
    old = json.loads(row["data"])
    if old.get("schema_version") == 2:
        return
    new = upgrade(old)
    version = row["version"] + 1
    db.execute("UPDATE settings SET version=?,data=? WHERE id=1", (version, json.dumps(new, ensure_ascii=False)))
    for number, policy in ((row["version"], old), (version, new)):
        db.execute("INSERT OR IGNORE INTO objects VALUES (?, 'policy', ?, ?)",
                   (f"policy:{number}", json.dumps({"version": number, "policy": policy}, ensure_ascii=False), now_iso()))
    db.execute("UPDATE commands SET state='cancelled' WHERE state='queued'")
    db.execute("UPDATE actions SET state='cancelled' WHERE state='queued'")
    # Preserve at-most-once across the split, including interrupted old occurrences.
    old_runs = list(db.execute("SELECT * FROM runs WHERE stage IN ('interact','publish')"))
    for run in old_runs:
        targets = ("comments", "dm", "follow") if run["stage"] == "interact" else ("content",)
        for stage in targets:
            db.execute("INSERT OR IGNORE INTO runs VALUES (?,?,?,?,?,?,?,?,?)", (
                uuid.uuid4().hex, run["day"], stage, run["slot"], run["version"], "migrated",
                f"旧阶段 {run['stage']} 已认领，本次不重放", run["started"], run["ended"]))
    db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'policy_migration', ?)",
               (now_iso(), json.dumps({"from_version": row["version"], "version": version})))


def repair_orphan_actions(db):
    rows = db.execute("SELECT id FROM actions WHERE state='queued' AND NOT EXISTS (SELECT 1 FROM commands WHERE commands.action_id=actions.id)").fetchall()
    if not rows:
        return
    evidence = {"evidence": "旧动作未创建执行命令，已取消占位；未重发任何外部动作", "at": now_iso()}
    db.executemany("UPDATE actions SET state='cancelled',result=? WHERE id=?", [(json.dumps(evidence, ensure_ascii=False), r[0]) for r in rows])
    db.execute("INSERT INTO events(at,kind,data) VALUES (?, 'orphan_actions_cancelled', ?)",
               (now_iso(), json.dumps({"action_ids": [r[0] for r in rows], **evidence}, ensure_ascii=False)))
