import { readFileSync } from 'node:fs'
import { JSDOM } from 'jsdom'
import { describe, expect, test } from 'vitest'

// Execute the shipped page program against DOM fixtures, not source-text assertions.
const script = readFileSync(new URL('../skills/social-media/xiaohongshu/scripts/page.js', import.meta.url), 'utf8')
const note = '0123456789abcdef01234567'

function page(html, url = 'https://www.xiaohongshu.com/explore') {
  const dom = new JSDOM(html, { url, runScripts: 'outside-only' })
  // jsdom has no layout/innerText implementation. These model only visible DOM text.
  Object.defineProperties(dom.window.HTMLElement.prototype, {
    innerText: { get() { return this.textContent } },
    isContentEditable: { get() { return this.getAttribute('contenteditable') === 'true' } },
    getClientRects: { value() { return this.hidden ? [] : [{}] } },
  })
  return {
    document: dom.window.document,
    run: (action, params = {}) => dom.window.eval(`${script}(${JSON.stringify({ action, count: 20, ...params })})`),
    close: () => dom.window.close(),
  }
}

describe('小红书页面控制', () => {
  test('extracts deduplicated note cards with signed links and preserves visible-only coverage', () => {
    const p = page(`<section class="note-item">
      <a href="/explore/${note}?xsec_token=a%2Bb"><img alt="封面"></a>
      <a class="title" href="/explore/${note}?xsec_token=a%2Bb">咖啡记录</a>
      <span class="author">作者甲</span></section>
      <a href="https://evil.test/explore/${note}">错误网站</a>
      <a hidden href="/explore/aaaaaaaaaaaaaaaaaaaaaaaa">不可见</a>`)
    try {
      const result = p.run('search')
      expect(result.status).toBe('ok')
      expect(result.notes).toHaveLength(1)
      expect(result.notes[0]).toMatchObject({ id: note, title: '咖啡记录', author: '作者甲',
        url: `https://www.xiaohongshu.com/explore/${note}?xsec_token=a%2Bb` })
      expect(result.coverage).toBe('visible_only')
    } finally { p.close() }
  })

  test.each([
    ['<div class="login-container">扫码登录</div>', 'login_required'],
    ['<div class="captcha">完成验证</div>', 'verification_required'],
    ['<h1>正在加载</h1>', 'page_changed'],
    ['<div class="empty-container">暂无相关笔记</div>', 'ok'],
  ])('distinguishes blocked, loading and explicitly empty pages', (html, status) => {
    const p = page(html)
    try { expect(p.run('search').status).toBe(status) } finally { p.close() }
  })

  test('does not treat another author profile link as proof of login', () => {
    const p = page('<a href="/user/profile/abc">作者乙</a>')
    try {
      expect(p.run('status').login).toBe('unknown')
      p.document.querySelector('a').textContent = '我'
      expect(p.run('status').login).toBe('logged_in')
    } finally { p.close() }
  })

  test('reads detail text and only the requested visible comments', () => {
    const p = page(`<div id="detail-title">标题</div><div id="detail-desc">笔记正文</div>
      <div class="comment-item"><span class="name">用户甲</span><div class="content">评论甲</div></div>
      <div class="comment-item"><div class="content">评论乙</div></div>`)
    try {
      const result = p.run('read', { count: 1 })
      expect(result.note).toMatchObject({ title: '标题', body: '笔记正文',
        comments: [{ author: '用户甲', text: '评论甲' }] })
    } finally { p.close() }
  })

  test('selectors resolve to their original fields and focus selects the full rich text', () => {
    const p = page(`<input placeholder="填写标题" value="现有标题"><input type="password" value="secret">
      <input type="file" accept="image/*" hidden><div contenteditable="true">第一段\n第二段 </div>`,
    'https://creator.xiaohongshu.com/publish/publish')
    try {
      const fields = p.run('inspect').fields
      expect(fields).toHaveLength(3)
      for (const field of fields) expect(p.document.querySelectorAll(field.selector)).toHaveLength(1)
      const body = fields.find(f => f.editable)
      expect(body.value).toBe('第一段\n第二段 ')
      expect(p.run('focus_body', { selector: body.selector }).status).toBe('ready')
      expect(p.document.defaultView.getSelection().toString()).toBe(body.value)
      expect(fields.find(f => f.type === 'file').value).toBe('')
    } finally { p.close() }
  })

  test.each(['https://example.com', 'https://creator.xiaohongshu.com:8443', 'http://www.xiaohongshu.com'])(
    'refuses to read or focus on a foreign origin: %s', url => {
    const p = page('<div contenteditable="true">草稿</div>', url)
    try {
      expect(p.run('inspect').status).toBe('wrong_page')
      expect(p.run('focus_body', { selector: 'div' }).status).toBe('wrong_page')
    } finally { p.close() }
  })
})
