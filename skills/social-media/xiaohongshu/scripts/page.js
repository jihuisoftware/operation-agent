// Read only rendered page data; authentication storage and private APIs stay untouched.
(request => {
  const origins = ['https://www.xiaohongshu.com', 'https://creator.xiaohongshu.com'];
  if (!origins.includes(location.origin)) {
    return {status: 'wrong_page'};
  }
  const visible = el => !!el && el.getClientRects().length > 0 &&
    getComputedStyle(el).visibility !== 'hidden';
  const all = selector => [...document.querySelectorAll(selector)].filter(visible);
  const text = el => (el?.innerText || '').trim();
  const firstText = selector => text(all(selector)[0]);
  const base = {url: location.href, title: document.title};
  const challenge = all('[class*="captcha"], [id*="captcha"], [class*="verify-dialog"]');
  if (challenge.length || /安全验证|访问验证/.test(document.title)) {
    return {...base, status: 'verification_required'};
  }
  if (/\/(login|signin)(\/|$)/.test(location.pathname) ||
      all('.login-container, .login-modal, [class*="login-box"]').length) {
    return {...base, status: 'login_required'};
  }
  const selectorFor = el => {
    const parts = [];
    while (el && el !== document.documentElement) {
      const tag = el.tagName.toLowerCase();
      const siblings = [...el.parentElement.children].filter(x => x.tagName === el.tagName);
      parts.unshift(`${tag}:nth-of-type(${siblings.indexOf(el) + 1})`);
      el = el.parentElement;
    }
    return 'html > ' + parts.join(' > ');
  };
  const fields = () => [...document.querySelectorAll('input, textarea, [contenteditable="true"]')]
    .filter(el => el.type === 'file' || visible(el))
    .filter(el => !['password', 'hidden'].includes(el.type))
    .map(el => ({selector: selectorFor(el), tag: el.tagName.toLowerCase(),
      type: el.type || '', placeholder: el.getAttribute('placeholder') || '',
      role: el.getAttribute('role') || '', accept: el.getAttribute('accept') || '',
      editable: el.isContentEditable, disabled: !!el.disabled || !!el.readOnly,
      value: el.type === 'file' ? '' : (el.isContentEditable ? el.innerText : el.value)}));
  const actions = {
    status: () => {
      const ownProfile = all('a[href*="/user/profile/"]')
        .find(el => ['我', '个人主页'].includes(text(el)));
      return {...base, status: 'ready', login: ownProfile ? 'logged_in' : 'unknown',
        account_url: ownProfile?.href || null};
    },
    inspect: () => ({...base, status: 'ready', fields: fields()}),
    search: () => {
      const seen = new Set();
      const notes = [];
      for (const link of all('a[href]')) {
        const url = new URL(link.href, location.href);
        const match = url.pathname.match(/^\/(?:explore|search_result)\/([a-f0-9]{24})$/i);
        if (url.hostname !== 'www.xiaohongshu.com' || !match || seen.has(match[1])) continue;
        seen.add(match[1]);
        const card = link.closest('section, article, .note-item') || link;
        notes.push({id: match[1], url: url.href,
          title: text(card.querySelector('.title')) || text(link) ||
            card.querySelector('img')?.alt || '',
          author: text(card.querySelector('.author, .name')),
          text: text(card).slice(0, 2000)});
        if (notes.length >= request.count) break;
      }
      const empty = all('.empty, .empty-container, [class*="no-result"]')
        .some(el => /暂无|没有|未找到/.test(text(el)));
      return {...base, status: notes.length || empty ? 'ok' : 'page_changed', notes,
        coverage: 'visible_only'};
    },
    read: () => {
      const title = firstText('#detail-title, .note-detail .title');
      const body = firstText('#detail-desc, .note-detail .desc');
      if (!title && !body) return {...base, status: 'page_changed'};
      const comments = all('.comment-item').slice(0, request.count).map(el => ({
        author: text(el.querySelector('.author, .name')),
        text: text(el.querySelector('.content')),
      }));
      return {...base, status: 'ok', note: {title, body,
        author: firstText('.note-detail .author .name, .author-container .username'),
        comments}, coverage: 'visible_only'};
    },
    focus_body: () => {
      if (location.hostname !== 'creator.xiaohongshu.com') return {status: 'wrong_page'};
      const matches = all(request.selector);
      if (matches.length !== 1 || !matches[0].isContentEditable) return {status: 'page_changed'};
      const el = matches[0];
      el.focus();
      const range = document.createRange();
      range.selectNodeContents(el);
      const selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      return {status: 'ready'};
    },
  };
  return actions[request.action] ? actions[request.action]() : {status: 'unsupported_action'};
})
