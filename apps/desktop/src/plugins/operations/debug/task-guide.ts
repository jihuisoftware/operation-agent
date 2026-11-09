export interface TaskGuide { purpose: string; stages: string[]; checks: string[]; path: string; destination: string }
export const guides: Record<string, TaskGuide> = {
  research: { purpose: '取得可追溯的原始资料。', stages: ['检索与去重', '读取正文和图片', '保存来源'], checks: ['核对来源链接、正文完整性和发布时间。', '失败来源与空白正文不能当作有效依据。'], path: '/materials?tab=sources', destination: '检查来源资料' },
  organize: { purpose: '将来源整理成摘要、事实、观点和待核实内容。', stages: ['复用已有整理', '分批或分段整理', '格式兼容与检查点保存', '汇总可用与待处理数量'], checks: ['对照原文检查事实与观点，留意格式跳过记录。', '长文缺段应保持待完善，不应显示完整覆盖。'], path: '/materials?tab=organized', destination: '检查整理资料' },
  analytics: { purpose: '按实际数据计算指标，明确统计范围。', stages: ['读取统计范围', '本地计算指标', '保存统计报告'], checks: ['检查日期范围、样本数和数据权限。', '缺失数据不等于零，不应推断增长。'], path: '/analysis?tab=analytics', destination: '核对统计数据' },
  industry: { purpose: '使用可用证据形成有范围限制的分析。', stages: ['复用有效分析批次', '分析新增证据', '校验引用与权限', '保存分析覆盖'], checks: ['核对新增、复用和未覆盖数量。', '确认结论有来源，历史分析没有被称为今日趋势。'], path: '/analysis?tab=industry', destination: '检查行业分析' },
  topics: { purpose: '形成可供写作的具体选题。', stages: ['读取整理依据', '复用或生成候选', '校验来源', '保存可用选题'], checks: ['比较候选题目和来源，必要时手动指定题目。', '部分可用不代表本次新增选题已全部完成。'], path: '/content?tab=topics', destination: '选择或修改选题' },
  content: { purpose: '生成完整图文并保存为待审版本。', stages: ['确定选题与资料', '生成正文和封面', '保存草稿并检查', '未通过时自动修订与复检（最多两轮）'], checks: ['核对完整正文、图片顺序与来源事实。', '查看检查问题、原稿和修订版本；超时后从已保存版本继续。'], path: '/content?tab=drafts', destination: '审核或编辑图文' },
  publish: { purpose: '提交指定版本并核对平台实际结果。', stages: ['核对账号和授权', '上传图片与填写内容', '提交发布', '只读核对平台结果'], checks: ['对照最终稿和平台笔记核实正文、图片、账号。', '同一内容结果不明先核对；其他稿件可独立发布。'], path: '/content?tab=published', destination: '查看发布记录' },
  comment: { purpose: '检查相关笔记并执行本次授权的主动评论。', stages: ['读取候选笔记', '生成评论', '定位输入框并提交', '核对结果'], checks: ['检查候选笔记上下文和评论内容。', '输入框匹配失败时先人工查看网页，不要反复提交。'], path: '/interactions?tab=comment', destination: '检查主动评论' },
  reply: { purpose: '处理收到的评论并核实回复。', stages: ['读取收到的评论', '生成回复', '提交回复', '核对结果'], checks: ['核对回复对象、原评论和重复处理记录。', '已经提交或结果未知时使用只读核对。'], path: '/interactions?tab=reply', destination: '检查评论回复' },
  dm: { purpose: '根据已确认知识处理收到的私信。', stages: ['读取收到的私信', '匹配知识与处理条件', '提交可执行回复', '保存需人工处理项'], checks: ['检查知识依据是否足够，确认消息来自对方。', '争议、敏感信息和不确定事项应保留人工处理。'], path: '/interactions?tab=dm', destination: '检查私信处理' },
  follow: { purpose: '仅对满足已配置条件的账号回关。', stages: ['读取关注关系', '检查回关条件', '执行回关', '核对关系'], checks: ['核对已关注本账号以及个人资料匹配条件。', '已回关对象不应重复提交。'], path: '/interactions?tab=follow', destination: '检查回关记录' },
  report: { purpose: '根据执行台账生成摘要和完整依据。', stages: ['汇总执行记录', '统计提交与模型消耗', '保存摘要和详情'], checks: ['核对成功数量是否有平台回执。', '查看未知 Token 回执，不把未知用量算成零。'], path: '/reports', destination: '查看运营日报' }
}

export const eventNames: Record<string, string> = {
  progress: '执行进度', pipeline_step_start: '步骤开始', pipeline_step_end: '步骤结束', debug_start: '任务开始', debug_result: '任务结果', action_deferred: '本次未执行（原动作待核对）',
  debug_exception: '执行异常', model_call: '模型请求', usage: '模型用量回执', model_input: '模型输入范围', model_service_error: '模型服务异常',
  model_trace_started: '保存模型请求快照', model_trace_completed: '保存模型返回结果', organization_format: '格式兼容与跳过',
  content_review_completed: '质量检查结果', content_check_reused: '复用有效质量检查', content_revision_completed: '修订版本已保存', content_revision_failed: '自动修订未完成', content_reused: '复用已保存图文',
  organization_batch: '整理批次结果', browser_step: '网页执行步骤', source_attempt: '来源读取', topics_partial: '选题部分可用', topics_reused: '复用已有选题'
}
