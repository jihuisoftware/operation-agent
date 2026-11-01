import { choices } from './configuration-choices'

export const themeChoices = choices([
  '工厂与制造企业', '本地门店与商家', '电商与产品商家', '个人号与个人 IP',
  '品牌与企业账号', '专业服务与工作室', '知识教育与培训', '社群与组织运营',
  '家居与收纳', '美食与生活', '运动与健康', '职场与成长', '旅行与城市探索', '科技与数码'
])
export const goalChoices = choices([
  '积累可靠资料并形成每日简报', '持续产出有依据的内容', '解答常见问题并积累用户信任',
  '展示真实案例，获取匹配的业务咨询', '维护已有用户并复盘运营效果'
])
export const audienceChoices = choices(['入门读者', '行业从业者', '潜在客户', '本地消费者', '兴趣爱好者', '已关注用户'])
export const styleChoices = choices(['真实、清楚、具体', '专业务实', '轻松亲切', '简洁客观', '步骤教程', '故事叙述'])
export const timezoneChoices = [
  { value: 'Asia/Shanghai', label: '中国标准时间（上海）' },
  { value: 'Asia/Hong_Kong', label: '香港' }, { value: 'Asia/Singapore', label: '新加坡' },
  { value: 'Asia/Tokyo', label: '东京' }, { value: 'Europe/London', label: '伦敦' },
  { value: 'America/New_York', label: '纽约' }, { value: 'America/Los_Angeles', label: '洛杉矶' },
  { value: 'UTC', label: '世界协调时 UTC' }
]
export const priorityChoices = ['最高', '较高', '普通', '较低', '最低'].map((label, index) => ({ value: String(index + 1), label: `${index + 1} · ${label}` }))
