"""Sticker sheets and their individually selectable poses. IDs persist in saved covers."""

GROUPS = {
    'Kico 软萌小白': {
        'kico': '软萌小白', 'kico-cat': '抱猫咪', 'kico-bone': '抱小狗', 'kico-hat': '蛋糕帽',
    },
    '粉红兔子': {
        'rabbit': '托盘女仆', 'rabbit-foot': '抱臂伸脚', 'rabbit-nails': '展示美甲',
        'rabbit-shadow': '阴影表情', 'rabbit-drive': '握方向盘', 'rabbit-flex': '展示肌肉',
    },
    '小玉': {
        'girl': '星星背包女孩', 'girl-plush': '抱玩偶', 'girl-flower': '头戴小花', 'girl-buns': '双丸子头',
    },
    '日本小人': {
        'school': '微笑女孩', 'school-toast': '叼吐司', 'school-bracelet': '晒手链',
        'school-glasses': '彩色眼镜', 'school-point': '向下指', 'school-cat': '猫咪装扮',
    },
    '韩系小人 · 头像': {
        'bonnet': '花边帽女孩', 'bonnet-earmuffs': '星星毛线帽', 'bonnet-braids': '橙色双辫',
        'bonnet-bow': '蝴蝶结帽', 'bonnet-check': '蓝格帽', 'bonnet-curlers': '卷发筒',
    },
    '韩系小人 · 全身': {
        'bunny-girl': '兔耳女孩', 'bunny-girl-pink': '粉色长耳帽', 'bunny-girl-deer': '与小鹿依偎',
        'bunny-girl-bag': '白帽提包', 'bunny-girl-cat': '黑猫帽', 'bunny-girl-hood': '星空斗篷',
    },
    '日系小人': {
        'bear-girl': '抱熊女孩', 'bear-girl-music': '耳机听歌', 'bear-girl-point': '双手指向',
        'bear-girl-friends': '玩偶合照', 'bear-girl-curry': '花环与咖喱', 'bear-girl-hat': '白熊帽比耶',
        'bear-girl-dinner': '举起刀叉', 'bear-girl-drink': '捧杯喝饮料', 'bear-girl-trip': '拎包出游',
    },
}
CHARACTERS = {key: label for poses in GROUPS.values() for key, label in poses.items()}


def character_options():
    return [{'id': key, 'label': label, 'group': group}
            for group, poses in GROUPS.items() for key, label in poses.items()]


def variations(spec):
    selected = spec.get('variant', 'kico')
    poses = next(list(poses) for poses in GROUPS.values() if selected in poses)
    index = poses.index(selected)
    return [{**spec, 'variant': key} for key in (poses[index:] + poses[:index])[:3]]
