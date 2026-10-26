import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { I18nProvider } from '@/i18n'
import { $freeTierSignIn } from '@/store/free-tier-sign-in'

import { formatMoney } from './billing-amounts'
import {
  billingDevFixtures,
  loggedOutBillingState,
  loggedOutSubscriptionState,
  okBilling,
  okSubscription,
  postTrainBillingState,
  postTrainSubscriptionState,
  todayBillingState,
  todaySubscriptionState
} from './fixtures.test-util'

import { BillingSettings } from './index'

const apiMocks = vi.hoisted(() => ({
  charge: vi.fn(),
  chargeStatus: vi.fn(),
  fetchBillingState: vi.fn(),
  fetchSubscriptionState: vi.fn(),
  openExternal: vi.fn(),
  previewSubscriptionChange: vi.fn(),
  resumeSubscription: vi.fn(),
  scheduleSubscriptionChange: vi.fn(),
  stepUp: vi.fn(),
  updateAutoReload: vi.fn(),
  updateKeepGoingOnCredits: vi.fn()
}))

vi.mock('./api', () => ({
  // Pass-through provider — the mocked useBillingApi ignores any override anyway.
  BillingApiProvider: ({ children }: { children: ReactNode }) => children,
  useBillingApi: () => ({
    charge: apiMocks.charge,
    chargeStatus: apiMocks.chargeStatus,
    fetchBillingState: apiMocks.fetchBillingState,
    fetchSubscriptionState: apiMocks.fetchSubscriptionState,
    previewSubscriptionChange: apiMocks.previewSubscriptionChange,
    resumeSubscription: apiMocks.resumeSubscription,
    scheduleSubscriptionChange: apiMocks.scheduleSubscriptionChange,
    stepUp: apiMocks.stepUp,
    updateAutoReload: apiMocks.updateAutoReload,
    updateKeepGoingOnCredits: apiMocks.updateKeepGoingOnCredits
  })
}))

function renderBilling(initialEntries: string[] = ['/settings?tab=billing']) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })

  render(
    <MemoryRouter initialEntries={initialEntries}>
      <QueryClientProvider client={client}>
        <BillingSettings />
      </QueryClientProvider>
    </MemoryRouter>
  )

  return client
}

beforeEach(() => {
  apiMocks.fetchBillingState.mockResolvedValue(okBilling(todayBillingState))
  apiMocks.fetchSubscriptionState.mockResolvedValue(okSubscription(todaySubscriptionState))
  Object.defineProperty(window, 'hermesDesktop', {
    configurable: true,
    value: {
      openExternal: apiMocks.openExternal
    }
  })
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('BillingSettings', () => {
  it('preserves the entered credit amount and reports charge failures in Chinese', async () => {
    apiMocks.fetchBillingState.mockResolvedValue(okBilling(postTrainBillingState))
    apiMocks.fetchSubscriptionState.mockResolvedValue(okSubscription(postTrainSubscriptionState))

    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <MemoryRouter>
        <I18nProvider>
          <QueryClientProvider client={client}>
            <BillingSettings />
          </QueryClientProvider>
        </I18nProvider>
      </MemoryRouter>
    )
    await screen.findByText('支付与额度')
    expect(screen.getByText('余额')).toBeTruthy()
    const input = screen.getByRole('spinbutton', { name: '自定义充值金额' }) as HTMLInputElement
    fireEvent.change(input, { target: { value: '37' } })
    expect(input.value).toBe('37')
    expect(apiMocks.charge).not.toHaveBeenCalled()
    apiMocks.charge.mockResolvedValue({
      ok: false,
      refusal: { kind: 'stripe_unavailable', message: '', retryAfter: 120 },
      idempotencyKey: 'fixture-charge'
    })
    fireEvent.click(screen.getByRole('button', { name: '购买' }))
    await screen.findByText(/Stripe 遇到问题/)
    expect(screen.getByText(/Stripe 遇到问题/)).toBeTruthy()
    expect(apiMocks.charge).toHaveBeenCalledTimes(1)
    expect(apiMocks.charge).toHaveBeenCalledWith('37', undefined)
    expect(screen.getAllByText(postTrainSubscriptionState.current!.tier_name!).length).toBeGreaterThan(0)
    client.clear()
  })

  it('renders the post-train payload with enabled buy controls and card provenance', async () => {
    apiMocks.fetchBillingState.mockResolvedValue(okBilling(postTrainBillingState))
    apiMocks.fetchSubscriptionState.mockResolvedValue(okSubscription(postTrainSubscriptionState))

    renderBilling()

    expect(await screen.findByText('$142.50')).toBeTruthy()
    expect(screen.getByText('Visa •••• 4242 - 订阅卡')).toBeTruthy()
    expect(screen.getByRole('button', { name: '$25' }).hasAttribute('disabled')).toBe(false)
    expect(screen.getByRole('button', { name: '$50' }).hasAttribute('disabled')).toBe(false)
    expect(screen.getByRole('button', { name: '$100' }).hasAttribute('disabled')).toBe(false)
    expect(screen.getByRole('spinbutton', { name: '自定义充值金额' })).toBeTruthy()
    expect(screen.getByRole('button', { name: /^购买$/ }).hasAttribute('disabled')).toBe(false)
  })

  it('disables buy controls when no card is on file', async () => {
    const fixture = billingDevFixtures['no-card']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)

    renderBilling()

    // No card → the payment row collapses to a single "Add payment method" link.
    expect(await screen.findByRole('button', { name: /添加支付方式/ })).toBeTruthy()
    expect(screen.queryByText('No card on file')).toBeNull()
    expect(screen.getByRole('button', { name: '$25' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '$50' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '$100' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('spinbutton', { name: '自定义充值金额' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: /^购买$/ }).hasAttribute('disabled')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: /^购买$/ }))

    expect(apiMocks.charge).not.toHaveBeenCalled()
  })

  it('saves enabled auto-refill edits and refreshes billing state', async () => {
    const client = renderBilling()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    apiMocks.updateAutoReload.mockResolvedValue({ data: { ok: true }, ok: true })

    fireEvent.click(await screen.findByRole('button', { name: '管理' }))
    fireEvent.change(screen.getByRole('spinbutton', { name: '自动充值阈值' }), {
      target: { value: '15' }
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: '自动充值金额' }), {
      target: { value: '20' }
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    await waitFor(() =>
      expect(apiMocks.updateAutoReload).toHaveBeenCalledWith({
        enabled: true,
        reload_to_usd: '20',
        threshold_usd: '15'
      })
    )
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['billing', 'state'] }))
    expect(await screen.findByText('自动充值已更新。')).toBeTruthy()
  })

  it('rejects auto-refill amounts outside the billing bounds', async () => {
    renderBilling()

    fireEvent.click(await screen.findByRole('button', { name: '管理' }))
    fireEvent.change(screen.getByRole('spinbutton', { name: '自动充值阈值' }), {
      target: { value: '7.50' }
    })

    expect(screen.getByText(`阈值：最低金额为 ${formatMoney(10)}。`, { collapseWhitespace: false })).toBeTruthy()
    expect(screen.getByRole('button', { name: '保存' }).hasAttribute('disabled')).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(apiMocks.updateAutoReload).not.toHaveBeenCalled()
  })

  it('shows "Keep going on credits" only on window plans and flips it', async () => {
    renderBilling()
    await screen.findByRole('button', { name: '管理' })
    expect(screen.queryByRole('switch', { name: '用额度继续' })).toBeNull()
    cleanup()

    apiMocks.fetchBillingState.mockResolvedValue(okBilling({ ...todayBillingState, keep_going_on_credits: false }))
    apiMocks.updateKeepGoingOnCredits.mockResolvedValue({ data: { ok: true }, ok: true })
    const client = renderBilling()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    const toggle = await screen.findByRole('switch', { name: '用额度继续' })
    expect(toggle.getAttribute('aria-checked')).toBe('false')
    fireEvent.click(toggle)

    await waitFor(() => expect(apiMocks.updateKeepGoingOnCredits).toHaveBeenCalledWith(true))
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['billing', 'state'] }))
  })

  it('renders the enabled auto-refill row without crashing when the card is null', async () => {
    apiMocks.fetchBillingState.mockResolvedValue(
      okBilling({ ...todayBillingState, auto_reload: { ...todayBillingState.auto_reload, card: null } })
    )

    renderBilling()

    expect(await screen.findByText('余额低于 $5 时自动扣款 $10。')).toBeTruthy()
    expect(screen.getByRole('button', { name: '管理' })).toBeTruthy()
  })

  it('requires inline confirmation before disabling auto-refill', async () => {
    renderBilling()

    apiMocks.updateAutoReload.mockResolvedValue({ data: { ok: true }, ok: true })

    fireEvent.click(await screen.findByRole('button', { name: '管理' }))
    fireEvent.click(screen.getByRole('button', { name: '禁用' }))

    expect(screen.getByText('关闭自动充值？')).toBeTruthy()
    expect(apiMocks.updateAutoReload).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '关闭' }))

    // The gateway requires threshold + top_up_amount even to disable, so the current
    // amounts ride along (todayBillingState: threshold $5, reload-to $10).
    await waitFor(() =>
      expect(apiMocks.updateAutoReload).toHaveBeenCalledWith({
        enabled: false,
        reload_to_usd: '10',
        threshold_usd: '5'
      })
    )
  })

  it('opens auto-refill edit without a validation error even when the saved config is below the minimum', async () => {
    // todayBillingState: threshold $5 with min_usd $10 — invalid, but opening
    // Manage must stay silent until the user edits or attempts to save (spec §9).
    renderBilling()

    fireEvent.click(await screen.findByRole('button', { name: '管理' }))

    expect(screen.getByRole('spinbutton', { name: '自动充值阈值' })).toBeTruthy()
    expect(screen.queryByText(`阈值：最低金额为 ${formatMoney(10)}。`, { collapseWhitespace: false })).toBeNull()
    // Save is disabled because the prefilled config is invalid — but no error yet.
    expect(screen.getByRole('button', { name: '保存' }).hasAttribute('disabled')).toBe(true)
  })

  it('navigates to the in-app plans grid from the plan card and back', async () => {
    const fixture = billingDevFixtures['free-personal']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)

    renderBilling()

    fireEvent.click(await screen.findByRole('button', { name: '查看套餐' }))

    expect(await screen.findByText('套餐')).toBeTruthy()
    // No subscription → the free tier is the inert current plan, the three paid
    // tiers are "Choose ↗" upgrades (no "subscribe to Free").
    expect(screen.getByText('当前套餐')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /选择/ }).length).toBe(3)
    expect(screen.queryByRole('button', { name: '降级' })).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '返回账单' }))

    expect(await screen.findByRole('button', { name: '查看套餐' })).toBeTruthy()
  })

  it('renders the current marker and an actionable downgrade when deep-linked to the plans grid', async () => {
    const fixture = billingDevFixtures['subscriber-personal']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)

    renderBilling(['/settings?tab=billing&bview=plans'])

    expect(await screen.findByText('当前套餐')).toBeTruthy()
    // Free sits below Plus → an in-app (enabled) "Downgrade" button, not disabled.
    expect(screen.getByRole('button', { name: '降级' }).hasAttribute('disabled')).toBe(false)
    // Super + Ultra are upgrades.
    expect(screen.getAllByRole('button', { name: /选择/ }).length).toBe(2)
  })

  it('falls back to overview (no live Choose grid) when a team deep-links bview=plans', async () => {
    // Default beforeEach uses todaySubscriptionState (context: 'team') — no in-app
    // plans capability, so the URL must not surface a grid of Choose buttons.
    renderBilling(['/settings?tab=billing&bview=plans'])

    expect(await screen.findByText('支付与额度')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '返回账单' })).toBeNull()
    expect(screen.queryByRole('button', { name: /选择/ })).toBeNull()
  })

  it('falls back to overview when a non-changer personal account deep-links bview=plans', async () => {
    apiMocks.fetchSubscriptionState.mockResolvedValue(
      okSubscription({ ...todaySubscriptionState, can_change_plan: false, context: 'personal' })
    )

    renderBilling(['/settings?tab=billing&bview=plans'])

    expect(await screen.findByText('支付与额度')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '返回账单' })).toBeNull()
    expect(screen.queryByRole('button', { name: /选择/ })).toBeNull()
  })

  it('runs an in-app downgrade: preview → confirm → schedule with the tier id → refetch → overview', async () => {
    const fixture = billingDevFixtures['subscriber-personal']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)
    apiMocks.previewSubscriptionChange.mockResolvedValue({
      data: {
        effect: 'scheduled',
        effective_at: '2026-08-15T00:00:00Z',
        monthly_credits_delta: '-88',
        ok: true,
        target_tier_name: '免费'
      },
      ok: true
    })
    apiMocks.scheduleSubscriptionChange.mockResolvedValue({ data: { ok: true }, ok: true })

    const client = renderBilling(['/settings?tab=billing&bview=plans'])
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    fireEvent.click(await screen.findByRole('button', { name: '降级' }))

    await waitFor(() => expect(apiMocks.previewSubscriptionChange).toHaveBeenCalledWith('cltier000free0000personal'))
    expect(await screen.findByText(/现在不扣费/)).toBeTruthy()
    // Credits delta renders as signed dollars, not the raw wire string "-88".
    expect(screen.getByText(/每月额度变化：−\$88\/月/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '确认降级' }))

    await waitFor(() => expect(apiMocks.scheduleSubscriptionChange).toHaveBeenCalledWith('cltier000free0000personal'))
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['billing', 'subscription'] }))
    // Scheduled → back on the overview.
    expect(await screen.findByText('支付与额度')).toBeTruthy()
    expect(screen.queryByRole('button', { name: '返回账单' })).toBeNull()
  })

  it('surfaces the step-up affordance when scheduling a downgrade needs approval', async () => {
    const fixture = billingDevFixtures['subscriber-personal']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)
    apiMocks.previewSubscriptionChange.mockResolvedValue({
      data: { effect: 'scheduled', effective_at: '2026-08-15T00:00:00Z', ok: true, target_tier_name: '免费' },
      ok: true
    })
    apiMocks.scheduleSubscriptionChange.mockResolvedValue({
      ok: false,
      refusal: { kind: 'insufficient_scope', message: 'billing:manage required' }
    })

    renderBilling(['/settings?tab=billing&bview=plans'])

    fireEvent.click(await screen.findByRole('button', { name: '降级' }))
    fireEvent.click(await screen.findByRole('button', { name: '确认降级' }))

    expect(await screen.findByText('需要批准远程支出:')).toBeTruthy()
    expect(screen.getByRole('button', { name: '验证以继续' })).toBeTruthy()
    // The failed schedule offers a retry in place.
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    expect(apiMocks.scheduleSubscriptionChange).toHaveBeenCalledTimes(1)
  })

  it('undoes a scheduled downgrade from the plan card via resume', async () => {
    const fixture = billingDevFixtures['pending-downgrade']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)
    apiMocks.resumeSubscription.mockResolvedValue({ data: { ok: true }, ok: true })

    const client = renderBilling()
    const invalidate = vi.spyOn(client, 'invalidateQueries')

    expect(await screen.findByText('于 Aug 15 更改为 Free。')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '撤销' }))

    await waitFor(() => expect(apiMocks.resumeSubscription).toHaveBeenCalledTimes(1))
    await waitFor(() => expect(invalidate).toHaveBeenCalledWith({ queryKey: ['billing', 'subscription'] }))
  })

  it('locks out the other downgrade tiles and Back while a schedule is in flight', async () => {
    // Current = Ultra so Free/Plus/Super are all downgrades (three tiles).
    apiMocks.fetchBillingState.mockResolvedValue(billingDevFixtures['subscriber-personal'].billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(
      okSubscription({
        ...todaySubscriptionState,
        can_change_plan: true,
        context: 'personal',
        current: { ...todaySubscriptionState.current, tier_id: 't_ultra', tier_name: '超高' },
        tiers: [
          {
            dollars_per_month_display: '$0',
            is_current: false,
            is_enabled: true,
            monthly_credits: '0.1',
            name: '免费',
            tier_id: 't_free',
            tier_order: 0
          },
          {
            dollars_per_month_display: '$20',
            is_current: false,
            is_enabled: true,
            monthly_credits: '22',
            name: 'Plus',
            tier_id: 't_plus',
            tier_order: 1
          },
          {
            dollars_per_month_display: '$100',
            is_current: false,
            is_enabled: true,
            monthly_credits: '110',
            name: 'Super',
            tier_id: 't_super',
            tier_order: 2
          },
          {
            dollars_per_month_display: '$200',
            is_current: true,
            is_enabled: true,
            monthly_credits: '220',
            name: '超高',
            tier_id: 't_ultra',
            tier_order: 3
          }
        ]
      })
    )
    apiMocks.previewSubscriptionChange.mockResolvedValue({
      data: { effect: 'scheduled', effective_at: '2026-08-15T00:00:00Z', ok: true, target_tier_name: '免费' },
      ok: true
    })

    let settleSchedule: (value: unknown) => void = () => {}
    apiMocks.scheduleSubscriptionChange.mockReturnValue(
      new Promise(resolve => {
        settleSchedule = resolve
      })
    )

    renderBilling(['/settings?tab=billing&bview=plans'])

    const downgrades = await screen.findAllByRole('button', { name: '降级' })
    expect(downgrades.length).toBe(3)

    fireEvent.click(downgrades[0])
    fireEvent.click(await screen.findByRole('button', { name: '确认降级' }))

    // Scheduling in flight → the two remaining tiles + Back are disabled.
    await waitFor(() => {
      const remaining = screen.getAllByRole('button', { name: '降级' })
      expect(remaining.length).toBe(2)
      expect(remaining.every(btn => btn.hasAttribute('disabled'))).toBe(true)
    })
    expect(screen.getByRole('button', { name: '返回账单' }).hasAttribute('disabled')).toBe(true)

    settleSchedule({ data: { ok: true }, ok: true })
  })

  it('disables Undo while the resume is in flight', async () => {
    const fixture = billingDevFixtures['pending-downgrade']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)

    let settleResume: (value: unknown) => void = () => {}
    apiMocks.resumeSubscription.mockReturnValue(
      new Promise(resolve => {
        settleResume = resolve
      })
    )

    renderBilling()

    fireEvent.click(await screen.findByRole('button', { name: '撤销' }))

    await waitFor(() => expect(screen.getByRole('button', { name: '正在撤销…' }).hasAttribute('disabled')).toBe(true))

    settleResume({ data: { ok: true }, ok: true })
  })

  it('moves focus into the confirm panel (role=status) when a downgrade opens', async () => {
    const fixture = billingDevFixtures['subscriber-personal']

    apiMocks.fetchBillingState.mockResolvedValue(fixture.billing)
    apiMocks.fetchSubscriptionState.mockResolvedValue(fixture.subscription)
    apiMocks.previewSubscriptionChange.mockResolvedValue({
      data: { effect: 'scheduled', effective_at: '2026-08-15T00:00:00Z', ok: true, target_tier_name: '免费' },
      ok: true
    })

    renderBilling(['/settings?tab=billing&bview=plans'])

    fireEvent.click(await screen.findByRole('button', { name: '降级' }))

    const panel = await screen.findByRole('status')

    expect(panel.getAttribute('aria-live')).toBe('polite')
    expect(panel).toBe(panel.ownerDocument.activeElement)
  })

  it('renders auto-refill mutation refusals and step-up affordance', async () => {
    renderBilling()

    apiMocks.updateAutoReload.mockResolvedValue({
      ok: false,
      refusal: {
        kind: 'insufficient_scope',
        message: 'billing:manage required'
      }
    })

    fireEvent.click(await screen.findByRole('button', { name: '管理' }))
    fireEvent.change(screen.getByRole('spinbutton', { name: '自动充值阈值' }), {
      target: { value: '15' }
    })
    fireEvent.change(screen.getByRole('spinbutton', { name: '自动充值金额' }), {
      target: { value: '20' }
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(await screen.findByText('需要批准远程支出:')).toBeTruthy()
    expect(screen.getByRole('button', { name: '验证以继续' })).toBeTruthy()
  })

  it('keeps disabled auto-refill portal-only with no enable control', async () => {
    apiMocks.fetchBillingState.mockResolvedValue(okBilling(postTrainBillingState))
    apiMocks.fetchSubscriptionState.mockResolvedValue(okSubscription(postTrainSubscriptionState))

    renderBilling()

    expect((await screen.findAllByText('已关闭')).length).toBeGreaterThan(0)
    expect(screen.getByText('在门户中开启自动充值')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /enable/i })).toBeNull()
    expect(screen.queryByRole('button', { name: '管理' })).toBeNull()
  })

  it('disables buy controls while polling and renders the settled outcome', async () => {
    let settleStatus: (value: unknown) => void = () => {}

    const statusPromise = new Promise(resolve => {
      settleStatus = resolve
    })

    apiMocks.fetchBillingState.mockResolvedValue(okBilling(postTrainBillingState))
    apiMocks.fetchSubscriptionState.mockResolvedValue(okSubscription(postTrainSubscriptionState))
    apiMocks.charge.mockResolvedValue({
      data: {
        charge_id: 'ch_123',
        ok: true
      },
      idempotencyKey: 'key-1',
      ok: true
    })
    apiMocks.chargeStatus.mockReturnValue(statusPromise)

    renderBilling()

    fireEvent.click(await screen.findByRole('button', { name: /^购买$/ }))

    expect(await screen.findByText('处理中…正在确认结算')).toBeTruthy()
    expect(screen.getByRole('button', { name: '$25' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: '$50' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('spinbutton', { name: '自定义充值金额' }).hasAttribute('disabled')).toBe(true)
    expect(screen.getByRole('button', { name: /^购买$/ }).hasAttribute('disabled')).toBe(true)

    settleStatus({
      data: {
        amount_usd: '25',
        ok: true,
        status: 'settled'
      },
      ok: true
    })

    await waitFor(() =>
      expect(screen.getByText(`已添加 ${formatMoney(25)}，正在刷新余额。`, { collapseWhitespace: false })).toBeTruthy()
    )
  })

  it('renders logged-out as a connect card whose sign-in opens the shared dialog', async () => {
    apiMocks.fetchBillingState.mockResolvedValue(okBilling(loggedOutBillingState))
    apiMocks.fetchSubscriptionState.mockResolvedValue(okSubscription(loggedOutSubscriptionState))
    $freeTierSignIn.set({ status: 'closed' })

    renderBilling()

    expect(await screen.findByText('连接你的 Nous 账户')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '登录' }))
    expect($freeTierSignIn.get()).toEqual({ status: 'requested' })
    expect(apiMocks.openExternal).not.toHaveBeenCalled()
    $freeTierSignIn.set({ status: 'closed' })
    expect(screen.queryByText('支付方式')).toBeNull()
    expect(screen.queryByText('用量')).toBeNull()
  })
})
