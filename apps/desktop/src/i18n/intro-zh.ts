import type { Translations } from './types'

const operationsIntros = [
  '想运营什么主题？直接输入你的方向，或让我提供几个候选供你选择。',
  '告诉我你的主题、受众和目标，我们可以从选题、内容草稿或活动计划开始。',
  '主题由你定义。带上品牌资料或已有素材，我会帮你整理成可审核的内容。',
  '还没确定方向？说说你的兴趣、业务或资源，我会提出候选主题，由你选择。',
  '输入本次运营的主题和渠道，也可以上传素材，让我们一起规划下一步。'
]

/** Personality controls the response voice; the operations topic always belongs to the user. */
export const introZh: Translations['intro'] = {
  stock: {
    helpful: operationsIntros,
    concise: operationsIntros,
    technical: operationsIntros,
    creative: operationsIntros,
    teacher: operationsIntros,
    kawaii: operationsIntros,
    catgirl: operationsIntros,
    pirate: operationsIntros,
    shakespeare: operationsIntros,
    surfer: operationsIntros,
    noir: operationsIntros,
    uwu: operationsIntros,
    philosopher: operationsIntros,
    hype: operationsIntros,
    none: operationsIntros
  },
  custom: label => [...operationsIntros.slice(0, 4), `告诉我本次运营的主题和目标，我会以 ${label} 模式协助你。`]
}
