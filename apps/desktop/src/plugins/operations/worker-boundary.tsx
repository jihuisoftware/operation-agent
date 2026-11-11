import { Button, host } from '@hermes/plugin-sdk'
import { Component, type ReactNode } from 'react'

import { browserDockStyle } from './browser-dock'

interface Props { children: ReactNode; visible: boolean }
interface State { error: Error | null }

/** A broken account view must release its worker and leave an explicit recovery entry. */
export class WorkerBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State { return { error } }

  componentDidCatch() {
    host.notify({ kind: 'error', message: '运营网页执行器发生错误，已停止接收新任务；请打开运营画面重新连接。' })
  }

  render() {
    if (!this.state.error) { return this.props.children }

    return <section aria-hidden={!this.props.visible || undefined} aria-label="运营执行器故障" className="flex flex-col gap-3 overflow-auto bg-background p-4 text-foreground"
      inert={!this.props.visible || undefined} style={browserDockStyle(this.props.visible)}>
      <p role="alert">运营网页执行器发生错误，已停止接收新任务。</p>
      <p className="text-sm">已保存的排期仍保留。重新连接不会清除账号阻塞，也不会重发结果未知的动作。</p>
      <details className="text-sm"><summary>错误详情</summary><p className="break-words">{this.state.error.message}</p></details>
      <Button onClick={() => this.setState({ error: null })} variant="outline">重新连接执行器</Button>
    </section>
  }
}
