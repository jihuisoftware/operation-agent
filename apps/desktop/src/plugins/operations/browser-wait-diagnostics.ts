/** Bounded timing metadata only: no DOM text, credentials or query strings. */
export class WaitDiagnostics {
  private sequence = 0
  private active = new Map<number, { id: number; label: string; budget_ms: number; started: number; guest: boolean }>()
  private recent: { label: string; elapsed_ms: number }[] = []

  start(label: string, budget: number, guest: boolean) {
    const id = ++this.sequence
    this.active.set(id, { id, label, budget_ms: budget, started: Date.now(), guest })

    return id
  }

  finish(id: number) {
    const row = this.active.get(id)

    if (!row) { return }
    this.recent.push({ label: row.label, elapsed_ms: Date.now() - row.started })
    this.recent = this.recent.slice(-16)
    this.active.delete(id)
  }

  timeout(id: number) {
    return { timed_out: this.active.get(id)?.label,
      pending: [...this.active.values()].slice(-16).map(({ started, ...row }) => ({ ...row, elapsed_ms: Date.now() - started })),
      recent: [...this.recent] }
  }
}
