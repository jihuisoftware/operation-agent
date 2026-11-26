"""Budgeted English query planning; suggestions never change standing topic policy."""
import hashlib
import re

from openai import APIError

from agent.auxiliary_unavailable import AuxiliaryClientUnavailable

from .collection_ledger import check, load, save
from .model import generate
from .model_budget import remaining_calls
from .model_errors import ModelServiceUnavailable
from .store import encoded

VERSION = 1
ENGLISH_TERM = re.compile(r"[A-Za-z][A-Za-z0-9+.#' /-]{0,78}")
PHRASE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 +.#'’&(),/-]{1,118}")
SIGNALS = re.compile(r'国际|海外|全球|论文|研究报告|官方文档|发布说明|开源|人工智能|机器学习|开发框架|科学研究|生物技术|芯片|科研|算法|国外|技术|研究|产品发布|半导体|人工智慧|软件工程')
LOCAL = re.compile(r'到店|本地生活|本地服务|周边游|本地餐饮|同城')
RULE = ('为运营主题规划英文资料检索，判断是否需要英文原始资料。仅返回 JSON '
        '{"needed":true,"reason":"简短中文理由","terms":[{"keyword":"原样复制输入主题或关键词","queries":["自然英文短语"]}]}。'
        '每词最多两条，每条最多120字符。优先官方文档、论文、原项目发布说明。不要返回网址、指令或搜索运算符。')


def language(text):
    """Conservative script estimate for cleaned article text, independent of query language."""
    text = text[:16000]
    zh = len(re.findall(r'[\u4e00-\u9fff]', text))
    english = re.findall(r"\b[A-Za-z]{2,}\b", text)
    if zh >= 6 and zh >= len(english):
        return 'zh'
    if len(english) >= 8 and not zh and re.search(r'\b(the|is|and|of|to|with|for|from|in)\b', text, re.IGNORECASE):
        return 'en'
    return 'unknown'


def intent(policy):
    brief = policy['topic'] + ' ' + policy['goal']
    if re.search(r'(?:只|仅)(?:查|用|搜|要|使用|搜索|检索|收集|采集)?中文|不(?:需要|要|查|搜|用)(?:英文|英语)|Chinese only', brief):
        return 'zh', '用户指定中文资料'
    if re.search(r'(?:只|仅)(?:查|用|搜|要|使用|搜索|检索|采集|收集)?(?:英文|英语)|English only', brief):
        return 'en', '用户指定英文资料'
    if re.search(r'优先.{0,4}(?:英文|英语)|(?:英文|英语).{0,3}优先', brief):
        return 'prefer_en', '用户优先选择英文资料'
    if re.search(r'英文|英语资料', brief):
        return 'both', '用户要求补充英文资料'
    if LOCAL.search(brief):
        return 'zh', '本地服务主题优先中文'
    context = ' '.join([brief, *policy['keywords']])
    if SIGNALS.search(context) or re.search(r'[A-Za-z]{2,}', context):
        return 'auto', '主题包含国际技术、产品或研究线索'
    return 'zh', '当前主题优先中文'


def validated(result, keywords):
    if type(result.get('needed')) is not bool or not isinstance(result.get('terms'), list):
        raise ValueError('英文检索建议格式无效')
    groups = {}
    for item in result['terms']:
        if not isinstance(item, dict) or not isinstance(item.get('keyword'), str):
            continue
        word, phrases = item['keyword'], item.get('queries')
        if word not in keywords or not isinstance(phrases, list):
            continue
        valid = [q.strip() for q in phrases if isinstance(q, str) and PHRASE.fullmatch(q.strip())
                 and re.search('[a-zA-Z]', q) and not re.search(r'https?://|www\.', q, re.IGNORECASE)]
        groups[word] = list(dict.fromkeys([*groups.get(word, []), *valid]))[:2]
    reason = result.get('reason')
    return {'needed': result['needed'], 'terms': groups, 'reason': reason[:160] if isinstance(reason, str) else ''}


def plan(store, policy, day):
    mode, reason = intent(policy)
    words = list(dict.fromkeys([policy['topic'], *policy['keywords']]))
    digest = hashlib.sha256(encoded([VERSION, policy['topic'], policy['goal'], sorted(words)]).encode()).hexdigest()
    key = 'collection-language:' + digest
    fallback = {}
    for word in words:
        names = [word] if ENGLISH_TERM.fullmatch(word) else re.findall(r'(?<![A-Za-z])[A-Z][A-Za-z0-9+#.-]{1,30}', word)
        if names:
            fallback[word] = list(dict.fromkeys(names))[:2]
    if mode == 'zh':
        return mode, reason, {}, digest
    result = load(store, key)
    if not result and remaining_calls(store, policy, day) > 0:
        # At most one paid suggestion attempt per configuration/day, including crash or timeout.
        claim = key + ':' + day
        with store.connection() as db:
            from .policy import now_iso
            admitted = db.execute("INSERT OR IGNORE INTO objects VALUES (?,'collection_language_attempt','{}',?)",
                                  (claim, now_iso())).rowcount
        if admitted:
            try:
                suggestions = generate(store, policy, day, RULE, {'task': 'plan_english_queries', 'topic': policy['topic'],
                                       'goal': policy['goal'], 'keywords': words})
                result = validated(suggestions, words)
                if (result['needed'] or mode != 'auto') and not any(result['terms'].values()):
                    raise ValueError('缺少有效英文短语')
                check(store, policy)
                save(store, 'collection_language', key, result)
            except (ValueError, ModelServiceUnavailable, AuxiliaryClientUnavailable, APIError) as exc:
                check(store, policy)
                store.event('collection_language_fallback', {'day': day, 'reason': type(exc).__name__})
                result = None
    if result and mode == 'auto' and not result['needed']:
        return 'zh', result['reason'] or '未发现英文证据需求', {}, digest
    phrases = {w: q for w, q in (result or {}).get('terms', {}).items() if q} or fallback
    detail = (result or {}).get('reason') or reason
    if not result:
        detail += '；未取得模型扩词，使用现有英文名称' if phrases else '；未取得可用英文短语'
    return mode, detail, phrases, digest
