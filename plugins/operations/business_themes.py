"""Business presets contain positioning suggestions, never invented business facts."""

_BUSINESSES = [
    {
        "id": "business-factory", "title": "工厂与制造企业",
        "description": "适合源头生产、加工定制与供应业务，围绕真实生产能力建立采购信任。",
        "subtypes": ["源头工厂", "加工定制", "设备制造", "批发供应"],
        "content_directions": ["生产流程", "工艺细节", "质量检验", "产品应用", "交付案例"],
        "questions": ["可以生产或定制哪些产品？", "起订量和交期如何确认？", "有哪些可核实的质检与交付资料？"],
        "defaults": {"goal": "展示真实生产流程、工艺与交付能力，解答采购关注的问题，获取匹配的采购咨询。",
                     "audience": "采购负责人、品牌方、批发商及有定制需求的客户",
                     "style": "专业务实，以工艺、实拍和可核实资料说明能力，不虚构产能与资质",
                     "keywords": ["采购需求", "加工定制", "生产工艺", "质量检验"]},
    },
    {
        "id": "business-local", "title": "本地门店与商家",
        "description": "适合服务周边消费者的门店，展示特色与体验，促进到店和预约。",
        "subtypes": ["餐饮", "美业", "零售", "家政", "民宿", "生活服务"],
        "content_directions": ["门店特色", "服务流程", "商品介绍", "消费指南", "本地活动"],
        "questions": ["门店地址与营业时间是什么？", "需要如何预约？", "有哪些已确认的服务项目和价格？"],
        "defaults": {"goal": "展示门店特色、真实服务流程和消费体验，帮助周边客户了解服务并发起到店或预约咨询。",
                     "audience": "门店周边居民、到访游客及有相关服务需求的消费者",
                     "style": "亲切具体，突出真实场景，不编造优惠、评价与服务效果",
                     "keywords": ["本地消费需求", "到店体验", "服务预约", "消费指南"]},
    },
    {
        "id": "business-commerce", "title": "电商与产品商家",
        "description": "适合销售具体商品的账号，用产品信息和使用场景帮助用户选购。",
        "subtypes": ["自有商品", "网店", "独立品牌", "分销"],
        "content_directions": ["使用演示", "选购指南", "场景搭配", "常见问题", "售后知识"],
        "questions": ["产品适合哪些使用场景？", "有哪些已确认的规格和价格？", "配送与售后政策是什么？"],
        "defaults": {"goal": "通过真实产品演示、选购指南和使用问题解答展示商品价值，促进匹配的购买咨询。",
                     "audience": "正在比较、选购或使用相关商品的消费者",
                     "style": "清楚实用，以真实规格和体验说明适用范围，不虚构销量与功效",
                     "keywords": ["产品选购", "使用场景", "商品常见问题", "售后需求"]},
    },
    {
        "id": "business-personal", "title": "个人号与个人 IP",
        "description": "适合围绕个人经验、兴趣和专业能力持续分享，形成清晰账号定位。",
        "subtypes": ["生活记录", "职场成长", "兴趣分享", "专业博主"],
        "content_directions": ["真实经历", "经验分享", "个人观点", "成长记录", "系列专题"],
        "questions": ["有哪些可以公开的真实经历？", "希望帮助哪一类读者？", "哪些个人信息不适合公开？"],
        "defaults": {"goal": "围绕个人定位分享有依据的经验、观点和成长记录，形成系列内容，积累关注与信任。",
                     "audience": "对所选领域感兴趣、处于相似阶段或需要相关经验的读者",
                     "style": "自然真诚，保留个人表达，不把参考资料改写成自己的经历",
                     "keywords": ["领域新话题", "读者常见问题", "成长经验", "实践方法"]},
    },
    {
        "id": "business-brand", "title": "品牌与企业账号",
        "description": "适合企业官方账号与品牌传播，展示产品理念、团队和真实发展动态。",
        "subtypes": ["企业官方号", "创业公司", "连锁品牌"],
        "content_directions": ["品牌故事", "产品理念", "团队日常", "企业动态", "客户案例"],
        "questions": ["哪些品牌与企业资料可以公开？", "有哪些获得授权的客户案例？", "对外合作如何联系？"],
        "defaults": {"goal": "通过可核实的品牌故事、产品理念和企业动态建立认知，吸引匹配的客户与合作机会。",
                     "audience": "潜在客户、合作伙伴及关注品牌和行业发展的用户",
                     "style": "专业一致，表达清晰，案例需授权，不虚构客户背书与企业成绩",
                     "keywords": ["行业动态", "客户需求", "品牌关注点", "合作机会"]},
    },
    {
        "id": "business-service", "title": "专业服务与工作室",
        "description": "适合通过作品、方法和服务流程展示专业能力的团队或工作室。",
        "subtypes": ["设计", "摄影", "装修", "软件开发", "咨询"],
        "content_directions": ["作品展示", "案例拆解", "服务流程", "方法分享", "常见误区"],
        "questions": ["具体提供哪些服务？", "项目周期与报价如何确认？", "有哪些可公开的作品与案例？"],
        "defaults": {"goal": "通过获授权作品、案例拆解和服务方法说明专业能力，让潜在客户理解服务范围并发起咨询。",
                     "audience": "有相关项目需求、正在比较服务方案的个人与企业客户",
                     "style": "专业易懂，说明过程与适用边界，不承诺未经确认的报价或结果",
                     "keywords": ["项目需求", "服务流程", "方案比较", "客户常见误区"]},
    },
    {
        "id": "business-education", "title": "知识教育与培训",
        "description": "适合知识分享、技能教学和课程介绍，帮助学习者理解方法与学习路径。",
        "subtypes": ["技能教学", "语言学习", "职业培训", "兴趣课程"],
        "content_directions": ["入门教程", "知识问答", "练习方法", "学习路径", "课程介绍"],
        "questions": ["内容适合什么基础的学习者？", "课程安排和费用是否已确认？", "有哪些实际可用的练习资料？"],
        "defaults": {"goal": "持续提供准确的入门教程、练习方法和学习路径，帮助学习者判断需求并咨询适合的课程。",
                     "audience": "对相关知识或技能有学习需求的初学者和进阶学习者",
                     "style": "循序渐进，示例清晰，不虚构学员成绩或保证学习结果",
                     "keywords": ["入门学习", "知识问答", "练习方法", "学习难点"]},
    },
    {
        "id": "business-community", "title": "社群与组织运营",
        "description": "适合围绕共同兴趣或目标组织活动、分享资源和促进成员参与。",
        "subtypes": ["兴趣社群", "行业协会", "俱乐部", "公益组织"],
        "content_directions": ["活动预告", "成员故事", "资源分享", "活动回顾", "主题讨论"],
        "questions": ["参与条件和报名方式是什么？", "活动时间、地点与费用是否已确认？", "成员故事是否获得公开授权？"],
        "defaults": {"goal": "围绕社群目标分享资源、介绍已确认活动并回顾真实成果，吸引合适成员参与和交流。",
                     "audience": "对社群主题感兴趣的潜在成员、现有成员及合作组织",
                     "style": "友好包容，参与方式明确，保护成员隐私，不虚构活动规模与成果",
                     "keywords": ["社群话题", "活动需求", "资源分享", "成员常见问题"]},
    },
]

BUSINESS_THEMES = [
    {**item, "kind": "business", "category": "业务主题", "modules": ["research", "organize", "analytics", "industry", "topics", "content", "publish", "comments", "dm", "report"],
     "output": "主题相关的来源、图文草稿与运营日报",
     "defaults": {"topic": item["title"], **item["defaults"]}}
    for item in _BUSINESSES
]


def validate_business_selection(theme, subtype):
    if not theme:
        if subtype:
            raise ValueError("选择业务子类前请先选择业务主题")
        return
    selected = next((item for item in BUSINESS_THEMES if item["id"] == theme), None)
    if selected is None or (subtype and subtype not in selected["subtypes"]):
        raise ValueError("业务主题或子类无效")
