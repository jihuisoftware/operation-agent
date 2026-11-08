"""Publication checks that must remain valid across artwork generation and commit."""
import hashlib

from .store import encoded


def asset_revisions(db, identities):
    rows = db.execute("SELECT id,data FROM objects WHERE kind='asset' AND id IN (SELECT value FROM json_each(?))",
                      (encoded(identities),)).fetchall()
    return {row[0]: hashlib.sha256(row[1].encode()).hexdigest() for row in rows}


def confirm_assets(db, identities, expected):
    if set(expected) != set(identities) or asset_revisions(db, identities) != expected:
        raise ValueError('提交期间图片已变化或撤回，请重新核对')
