"""Suggested module combinations; selecting one never grants external-action permission."""

SCENARIOS = [
    {
        "id": "industry-watch", "kind": "scenario", "title": "行业资讯追踪", "category": "推荐场景",
        "description": "适合每天跟进一个主题：采集来源、筛选变化，晚上整理结论。",
        "output": "来源清单、关键变化、可追溯的信息日报", "modules": ["research", "report"],
        "defaults": {"goal": "每天跟进主题的新信息，保留原始链接，区分事实与观点，汇总值得关注的变化。",
                     "style": "简洁客观，注明来源和待核实事项"},
    },
    {
        "id": "draft-workshop", "kind": "scenario", "title": "选题与草稿", "category": "推荐场景",
        "description": "适合先积累内容：根据当天资料生成选题和图文草稿，保留版本供后续编辑。",
        "output": "选题依据、标题正文、草稿版本与检查结果", "modules": ["research", "content", "report"],
        "defaults": {"goal": "从可靠来源中选择与主题相关的选题，形成可修改的图文草稿，并总结资料与内容缺口。",
                     "style": "结构清晰，有具体依据，不虚构个人经历"},
    },
    {
        "id": "xiaohongshu-daily", "kind": "scenario", "title": "小红书日更", "category": "推荐场景",
        "description": "适合有账号和授权素材的日常更新：采集、生产、检查后发布，再汇总结果。发布须单独授权。",
        "output": "图文版本、发布结果或跳过原因、运营日报",
        "modules": ["research", "content", "publish", "report"],
        "defaults": {"goal": "围绕主题持续更新有依据的图文内容，使用授权素材，记录实际发布结果与未完成原因。",
                     "style": "自然清晰，标题准确，避免夸张承诺和重复内容"},
    },
    {
        "id": "comment-care", "kind": "scenario", "title": "评论维护", "category": "推荐场景",
        "description": "适合分时段处理评论：结合原文回复问题，记录待处理事项；主动评论与回复分别授权。",
        "output": "评论回复记录、待处理问题、互动日报", "modules": ["comments", "report"],
        "defaults": {"goal": "及时处理与主题相关的评论问题，依据原文提供有内容的回应，将无法确认的问题留待处理。",
                     "style": "友好具体，不重复发送推广话术"},
    },
    {
        "id": "inbound-support", "kind": "scenario", "title": "咨询回复", "category": "推荐场景",
        "description": "适合处理收到的私信：依据已确认知识回答，争议、承诺和不确定问题转待处理。",
        "output": "私信回复记录、待处理咨询与每日汇总", "modules": ["dm", "report"],
        "defaults": {"goal": "依据已确认的回复知识处理收到的咨询，记录未能回答的问题，不主动群发私信或作未经确认的承诺。",
                     "style": "礼貌简洁，明确事实与待确认事项"},
    },
    {
        "id": "daily-review", "kind": "scenario", "title": "每日复盘", "category": "推荐场景",
        "description": "适合集中查看运营成果：根据执行台账汇总当天完成情况、异常和次日建议。",
        "output": "可导出的日报、异常清单与次日建议", "modules": ["report"],
        "defaults": {"goal": "每天根据实际执行记录复盘目标完成情况、失败原因和可获取指标，提出不扩大授权范围的次日建议。",
                     "style": "以记录为依据，明确缺失数据，建议具体可执行"},
    },
]
