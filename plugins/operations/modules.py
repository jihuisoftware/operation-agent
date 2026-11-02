"""The ordered stages of one profile's operations plan."""

TIMES = {"research": ["09:00"], "organize": ["09:10"], "analytics": ["09:12"], "industry": ["09:16"], "topics": ["09:20"], "content": ["09:40"], "publish": ["10:00"],
         "comments": ["11:00", "15:00", "19:00"], "dm": ["11:00", "15:00", "19:00"],
         "follow": ["11:00", "15:00", "19:00"], "report": ["21:00"]}
ACTION_MODULE = {"publish": "publish", "comment": "comments", "reply": "comments", "dm": "dm", "follow": "follow"}
EXTERNAL = frozenset({"publish", "comments", "dm", "follow"})
