"""Versioned scoring rubric; missing or non-finite values never authorize publication."""
import math

VERSION = 'review-scores-v1'
TEXT = {'evidence': 40, 'relevance': 20, 'structure': 20, 'originality': 20}
VISUAL = {'readability': 40, 'layout': 25, 'relevance': 20, 'consistency': 15}


def instruction(kind):
    weights = TEXT if kind == 'text' else VISUAL
    return ('同时返回 scores 对象，各维度取0到100分并给出评分依据。维度及权重：' + str(weights)
            + '。正文 evidence=依据可靠性、relevance=主题受众匹配、structure=结构清晰、originality=表达原创；'
            '图片 readability=文字可读性、layout=版式层次、relevance=主题贴合、consistency=风格一致。'
            '分数不能替代pass和问题列表，事实或授权问题不得被高分掩盖。评分规则：' + VERSION)


def score(result, kind):
    weights = TEXT if kind == 'text' else VISUAL
    values = result.get('scores') or {}
    if not isinstance(values, dict):
        return None
    numbers = [values.get(key) for key in weights]
    if any(type(n) not in (int, float) or not math.isfinite(n) or not 0 <= n <= 100 for n in numbers):
        return None
    return round(sum(values[key] * weight for key, weight in weights.items()) / 100, 2)


def decide(policy, text, visual):
    scores = {'text': score(text, 'text'), 'visual': score(visual, 'visual')}
    if text.get('pass') is not True or text.get('issues'):
        return False, '自动文本检查未通过，等待人工审核', scores
    if visual.get('pass') is not True or visual.get('issues'):
        return False, '图片检查未通过或不可用，等待人工审核', scores
    if policy['mode'] == 'score':
        if None in scores.values():
            return False, '评分缺失或格式无效，等待人工审核', scores
        if min(scores.values()) < policy['threshold']:
            return False, '正文或图片评分未达到门槛，等待人工审核', scores
    return policy['mode'] != 'manual', '等待人工审核' if policy['mode'] == 'manual' else '自动审核通过，等待可用发布时段', scores
