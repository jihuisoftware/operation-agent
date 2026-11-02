import { Button } from '@hermes/plugin-sdk'

import type { PolicyFieldsProps } from './blueprint-fields'

export function AccountSelection({ policy, onChange }: PolicyFieldsProps) {
  return (
    <div className="space-y-2">
      <p>无需预填账号。在“账号登录”打开小红书并扫码，任务使用内嵌网页当前登录的账号。</p>
      <p className="text-muted-foreground">执行前自动识别账号并记录；未登录时提示登录，任务准备后切换账号会停止该动作。</p>
      {policy.account_id && (
        <>
          <p>当前规则限定账号：{policy.account_id}</p>
          <Button onClick={() => onChange({ ...policy, account_id: '' })} variant="outline">
            改为使用当前扫码登录账号
          </Button>
        </>
      )}
    </div>
  )
}
