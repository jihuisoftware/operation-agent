"""Local macOS signing setup; credentials remain in the user's Keychain."""
import re
import subprocess

from hermes_platform.resolver import locate_command


def executable(name):
    found = locate_command(name)
    if not found.found:
        raise ValueError(f'找不到 {name}，请检查开发工具和PATH')
    return found.command[0]


def identities(output):
    found = []
    for line in output.splitlines():
        match = re.fullmatch(r'\s*\d+\)\s+[A-Fa-f0-9]{40}\s+"(Developer ID Application:[^"]+)"\s*', line)
        if match and match[1] not in found:
            found.append(match[1])
    return found


def available_identities(env):
    result = subprocess.run([executable('security'), 'find-identity', '-v', '-p', 'codesigning'],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=30, check=False)
    if result.returncode:
        raise ValueError('无法读取代码签名身份，请解锁登录钥匙串后重试')
    return identities(result.stdout)


def notary_ready(profile, env):
    result = subprocess.run([executable('xcrun'), 'notarytool', 'history', '--keychain-profile', profile, '--output-format', 'json'],
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=45, check=False)
    return result.returncode == 0


def configure(config, env):
    choices = available_identities(env)
    if not choices:
        raise ValueError('没有可用的 Developer ID Application 分发身份。请先取得证书并连同私钥导入钥匙串；Apple Development 不能替代。')
    identity = config['signing_identity']
    if identity not in choices:
        if len(choices) == 1:
            identity = choices[0]
        else:
            for index, name in enumerate(choices, 1):
                print(f'{index}. {name}')
            selected = input('选择用于分发的证书编号：').strip()
            if not selected.isdigit() or not 1 <= int(selected) <= len(choices):
                raise ValueError('证书选择无效')
            identity = choices[int(selected) - 1]
    print('接下来由Apple工具交互输入公证凭据，凭据保存在钥匙串，不写入配置文件。')
    subprocess.run([executable('xcrun'), 'notarytool', 'store-credentials', config['notary_profile']],
                   env=env, check=True, timeout=600)
    return {**config, 'signing_identity': identity}


def verify_app(directory, env):
    apps = [*directory.glob('*.app'), *directory.glob('*/*.app')]
    if len(apps) != 1:
        raise ValueError('无法唯一确定本次应用产物，请检查release目录')
    app = str(apps[0])
    commands = [
        [executable('codesign'), '--verify', '--deep', '--strict', '--verbose=2', app],
        [executable('spctl'), '--assess', '--type', 'execute', '--verbose=4', app],
        [executable('xcrun'), 'stapler', 'validate', app],
    ]
    for command in commands:
        subprocess.run(command, env=env, check=True, timeout=180)
    print('应用签名、Gatekeeper和公证票据检查通过。')
