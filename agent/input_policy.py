"""Profile-owned parsing preferences; never rewrite cached conversation history."""


def parsing_allowed(kind, config=None):
    if kind not in {'images', 'files'}:
        raise ValueError('Unknown parsing kind')
    if config is None:
        from hermes_cli.config import load_config_readonly
        config = load_config_readonly()
    settings = config.get('token_saving', {})
    if not isinstance(settings, dict) or settings.get('enabled') is not True:
        return True
    return settings.get('parse_' + kind) is True


def parsing_notice(kind):
    label = {'images': '图像', 'files': '文件'}[kind]
    return f'节省 Token 模式已关闭{label}解析；本次未读取其内容。可在设置 → 模型 → 节省 Token 模式中开启。请勿改用其他工具绕过此偏好。'


def pdf_parsing_notice(profile_home):
    from pathlib import Path
    from hermes_cli.config_effective import load_user_config_effective
    path = Path(profile_home) / 'config.yaml'
    config = load_user_config_effective(path) if path.exists() else {}
    for kind in ('files', 'images'):
        if not parsing_allowed(kind, config):
            return parsing_notice(kind)
    return None
