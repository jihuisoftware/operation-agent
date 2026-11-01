"""The ordered stages of one profile's operations plan."""
from copy import deepcopy

TIMES = {"research": ["09:00"], "organize": ["09:10"], "analytics": ["09:12"], "industry": ["09:16"], "topics": ["09:20"], "content": ["09:40"], "publish": ["10:00"],
         "comments": ["11:00", "15:00", "19:00"], "dm": ["11:00", "15:00", "19:00"],
         "follow": ["11:00", "15:00", "19:00"], "report": ["21:00"]}
ACTION_MODULE = {"publish": "publish", "comment": "comments", "reply": "comments", "dm": "dm", "follow": "follow"}
EXTERNAL = frozenset({"publish", "comments", "dm", "follow"})


def upgrade(policy):
    result = deepcopy(policy)
    if result.get("schema_version") == 5:
        return result
    if result.get("schema_version") != 4:
        result = _upgrade_topics(result)
        result['modules']['organize'] = any(result['modules'].get(k, False) for k in ('research', 'topics', 'content'))
        result['times']['organize'] = list(result['times']['research'])
    for stage in ('analytics', 'industry'):
        result['modules'][stage] = False
        result['times'][stage] = list(TIMES[stage])
    result['schema_version'] = 5
    return result


def _upgrade_topics(result):
    if result.get('schema_version') == 3:
        return result
    if result.get("schema_version", 1) not in (1, 2):
        raise ValueError("不支持的运营规则版本")
    if result.get("schema_version") == 2:
        result["modules"]["topics"] = result["modules"].get("research", False)
        result["times"]["topics"] = list(result["times"].get("research", TIMES["topics"]))
        result["schema_version"] = 3
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
    result["modules"]["topics"] = result["modules"]["research"]
    result["times"]["topics"] = list(result["times"]["research"])
    result["schema_version"] = 3
    return result
