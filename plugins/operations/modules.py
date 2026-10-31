"""The ordered stages of one profile's operations plan."""
from copy import deepcopy

TIMES = {"research": ["09:00"], "content": ["09:40"], "publish": ["10:00"],
         "comments": ["11:00", "15:00", "19:00"], "dm": ["11:00", "15:00", "19:00"],
         "follow": ["11:00", "15:00", "19:00"], "report": ["21:00"]}
ACTION_MODULE = {"publish": "publish", "comment": "comments", "reply": "comments", "dm": "dm", "follow": "follow"}
EXTERNAL = frozenset({"publish", "comments", "dm", "follow"})


def upgrade(policy):
    result = deepcopy(policy)
    if result.get("schema_version") == 2:
        return result
    allowed = result.get("allowed", {})
    times = result.get("times", {})
    result["modules"] = {"research": True, "content": allowed.get("publish", False),
                         "publish": allowed.get("publish", False),
                         "comments": allowed.get("comment", False) or allowed.get("reply", False),
                         "dm": allowed.get("dm", False), "follow": allowed.get("follow", False), "report": True}
    result["times"] = {**deepcopy(TIMES), **{k: v for k, v in times.items() if k in TIMES}}
    result["times"]["content"] = times.get("publish", TIMES["content"])
    for key in ("comments", "dm", "follow"):
        result["times"][key] = times.get("interact", TIMES[key])
    result["schema_version"] = 2
    return result
