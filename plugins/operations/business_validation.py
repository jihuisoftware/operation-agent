"""Template semantics and explicit sharing gates for imported business records."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import re

from .store import encoded

TEMPLATES = {
    'sales': {'title': '销售订单', 'metrics': {'revenue': '销售额', 'quantity': '销量', 'refund': '退款金额'}},
    'products': {'title': '商品表现', 'metrics': {'revenue': '销售额', 'quantity': '销量', 'views': '浏览量'}},
    'leads': {'title': '获客转化', 'metrics': {'leads': '线索数', 'conversions': '转化数', 'cost': '获客费用'}},
    'content': {'title': '内容表现', 'metrics': {'views': '阅读量', 'likes': '点赞数', 'comments': '评论数', 'shares': '分享数'}},
}
FIELDS = {'day': '日期', 'key': '业务键', 'product': '商品', 'channel': '渠道', 'platform': '平台', 'note': '备注'}
ALIASES = {'day': ['日期', '时间', 'day', 'date'], 'key': ['订单号', 'id', '业务键'], 'product': ['商品', '产品', 'product'],
           'channel': ['渠道', 'channel'], 'platform': ['平台', 'platform'], 'note': ['备注', 'note']}
MONEY = {'revenue', 'refund', 'cost'}
PRIVATE_HEADER = re.compile(r'姓名|电话|手机|邮箱|地址|身份证|客户|联系人|email|phone|address|customer|昵称|name', re.IGNORECASE)


def fields(template):
    if template not in TEMPLATES:
        raise ValueError('请选择业务模板')
    return {**FIELDS, **TEMPLATES[template]['metrics']}


def suggest(headers, template):
    return {key: next((h for h in headers if h.lower() in [s.lower() for s in ALIASES.get(key, [label, key])]), '')
            for key, label in fields(template).items()}


def options(body, headers):
    template = body['template']
    known = fields(template)
    mapping = body['mapping']
    if not isinstance(mapping, dict) or set(mapping) - set(known) or any(v not in headers for v in mapping.values() if v):
        raise ValueError('字段映射无效')
    if not mapping.get('day') or not any(mapping.get(k) for k in TEMPLATES[template]['metrics']):
        raise ValueError('请匹配日期和至少一个指标')
    if body.get('date_format', '%Y-%m-%d') not in ('%Y-%m-%d', '%Y/%m/%d', '%Y%m%d', '%d/%m/%Y', '%m/%d/%Y'):
        raise ValueError('日期格式无效')
    if body.get('semantics', 'increment') not in ('increment', 'snapshot'):
        raise ValueError('请选择增量或累计快照口径')
    currency = body.get('currency', 'CNY')
    if currency not in ('CNY', 'USD', 'EUR', 'JPY', 'HKD'):
        raise ValueError('请选择币种')
    definition = str(body.get('definition', '')).strip()
    if not definition or len(definition) > 500:
        raise ValueError('请填写指标口径（最多 500 字）')
    return {'template': template, 'mapping': {k: v for k, v in mapping.items() if v},
            'date_format': body.get('date_format', '%Y-%m-%d'), 'semantics': body.get('semantics', 'increment'),
            'currency': currency, 'definition': definition, 'dedupe': body.get('dedupe') is True}


def clean_row(raw, config):
    value = {k: str(raw.get(v, '')).strip() for k, v in config['mapping'].items()}
    if any(v.startswith('#') for v in value.values()):
        raise ValueError('包含公式缺少缓存值或 Excel 错误，请转为有效数值')
    try:
        value['day'] = datetime.strptime(value['day'], config['date_format']).date().isoformat()
    except ValueError as exc:
        raise ValueError('日期不符合选定格式') from exc
    if config['dedupe'] and not value.get('key'):
        raise ValueError('去重需要每行都有业务键')
    for key in TEMPLATES[config['template']]['metrics']:
        raw_value = value.get(key, '')
        try:
            number = Decimal(raw_value) if raw_value else None
            if number is not None and (not number.is_finite() or abs(number) > Decimal('1e15')):
                raise ValueError('超出支持的数值范围')
            value[key] = str(number) if number is not None else None
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f'{key} 必须是无单位数值，空白表示缺失') from exc
    return value


def redact(value):
    value = re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', '[邮箱已移除]', str(value))
    value = re.sub(r'\+?\d[\d\s()-]{6,}\d', '[号码已移除]', value)
    return value[:300]


def permissions(body, config):
    mode = body.get('model_mode', 'summary')
    selected = body.get('detail_fields', [])
    public = body.get('public_metrics', [])
    metrics = TEMPLATES[config['template']]['metrics']
    if mode not in ('local', 'summary', 'details') or not isinstance(selected, list) or not isinstance(public, list):
        raise ValueError('数据使用选项无效')
    allowed = {'day', 'product', 'channel', 'platform', 'note', *metrics}
    if set(selected) - allowed or set(public) - set(metrics):
        raise ValueError('业务键及身份字段不能发送，公开范围仅支持汇总指标')
    if any(PRIVATE_HEADER.search(config['mapping'].get(k, '')) for k in selected):
        raise ValueError('包含直接身份字段，不允许发送给模型')
    if mode == 'local' and public:
        raise ValueError('仅本地数据不能同时授权自动内容使用')
    return {'model_mode': mode, 'detail_fields': selected if mode == 'details' else [], 'public_metrics': public}


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()
