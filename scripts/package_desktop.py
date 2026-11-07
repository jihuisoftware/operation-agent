#!/usr/bin/env python3
"""Local configuration and preflight for the existing complete macOS bundle builder."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.bundles.local_signing import available_identities, configure, executable, notary_ready, verify_app
from pm.store import current_target

FIELDS = {'python', 'target', 'developer_dir', 'variant', 'github_repository', 'update_base_url',
          'release_tag', 'signing_identity', 'notary_profile'}
SIGNING_ENV = ('CSC_LINK', 'CSC_KEY_PASSWORD', 'CSC_NAME', 'CSC_KEYCHAIN', 'APPLE_API_KEY', 'APPLE_API_KEY_ID',
               'APPLE_API_ISSUER', 'APPLE_API_KEY_P8', 'APPLE_NOTARY_PROFILE', 'APPLE_SIGNING_IDENTITY')


def capture(args, root=ROOT, env=None):
    result = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True, encoding='utf-8', timeout=30, check=False)
    if result.returncode:
        raise ValueError(f'{Path(args[0]).name} 检查失败（退出码 {result.returncode}）')
    return result.stdout.strip()


def git(*args, root=ROOT):
    return capture([executable('git'), *args], root)


def repository(root):
    result = subprocess.run([executable('git'), 'remote', 'get-url', 'origin'], cwd=root, capture_output=True,
                            text=True, encoding='utf-8', timeout=15, check=False)
    remote = result.stdout.strip()
    if remote.startswith('git@github.com:'):
        path = remote.partition(':')[2]
    else:
        parsed = urlsplit(remote)
        path = parsed.path.lstrip('/') if parsed.hostname == 'github.com' else ''
    value = path.removesuffix('.git')
    return value if re.fullmatch(r'[\w.-]+/[\w.-]+', value) else ''


def write_config(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or path.parent.is_symlink():
        raise ValueError('本机打包配置不能使用符号链接')
    fd, temporary = tempfile.mkstemp(prefix='.config-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def initialize(root, path):
    if path.exists():
        raise ValueError('本机配置已存在，未覆盖；请编辑现有配置或运行setup-signing')
    target = current_target()
    if target not in {'darwin-arm64', 'darwin-x64'}:
        raise ValueError('此打包入口仅支持macOS')
    value = {'python': str(Path(sys.executable).resolve()), 'target': target,
             'developer_dir': capture([executable('xcode-select'), '-p'], root), 'variant': 'bundled',
             'github_repository': repository(root), 'update_base_url': '', 'release_tag': '',
             'signing_identity': '', 'notary_profile': 'operations-notary'}
    write_config(path, value)
    launcher = path.parent / 'package.sh'
    command = [value['python'], str(root / 'scripts/package_desktop.py'), '--config', str(path)]
    launcher.write_text('#!/bin/sh\nset -eu\nexec ' + shlex.join(command) + ' "$@"\n', encoding='utf-8')
    launcher.chmod(0o700)
    print(f'已生成本机配置：{path}\n本机入口：{launcher}\n默认build为完整测试包；正式签名需另外运行setup-signing。')


def read_config(path):
    value = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(value, dict) or set(value) != FIELDS or any(not isinstance(item, str) for item in value.values()):
        raise ValueError('本机配置字段无效；密码和API私钥不能写进配置，请用init创建配置')
    if value['variant'] not in {'bundled', 'light'} or value['target'] not in {'darwin-arm64', 'darwin-x64'}:
        raise ValueError('构建版本或架构无效')
    if value['github_repository'] and not re.fullmatch(r'[\w.-]+/[\w.-]+', value['github_repository']):
        raise ValueError('github_repository需为owner/repo')
    if not value['notary_profile'].strip() or any(char in value['notary_profile'] for char in '\n\r\0'):
        raise ValueError('公证钥匙串配置名无效')
    if value['update_base_url']:
        from scripts.releases.r2 import public_artifact_url
        if urlsplit(value['update_base_url']).scheme != 'https':
            raise ValueError('正式更新地址必须使用HTTPS')
        public_artifact_url(value['update_base_url'], 'preflight')
    return value


def environment(config, signed):
    env = {key: value for key, value in os.environ.items() if key not in SIGNING_ENV}
    env['DEVELOPER_DIR'] = config['developer_dir']
    if config['github_repository']:
        env['GITHUB_REPOSITORY'] = config['github_repository']
    if config['update_base_url']:
        env['CLOUDFLARE_R2_PUBLIC_URL'] = config['update_base_url']
    else:
        env.pop('CLOUDFLARE_R2_PUBLIC_URL', None)
    env['CSC_IDENTITY_AUTO_DISCOVERY'] = 'true' if signed else 'false'
    if signed:
        # electron-builder selects the certificate type itself and rejects its prefix in CSC_NAME.
        env.update(CSC_NAME=config['signing_identity'].removeprefix('Developer ID Application:').strip(),
                   APPLE_NOTARY_PROFILE=config['notary_profile'])
    return env


def preflight(root, path, config, signed, tag):
    errors = []
    env = environment(config, signed)
    print(f"目标：{config['target']} / {config['variant']}\nPython：{config['python']}\n产物：{root / 'apps/desktop/release'}")
    if current_target() != config['target']:
        errors.append('本机架构与配置不一致，请重新初始化对应机器的配置')
    python = Path(config['python'])
    if not python.is_file():
        errors.append('配置的Python不存在，请更新本机配置和入口脚本')
    else:
        capture([str(python), '-c', 'import sys; sys.exit(sys.version_info < (3,11))'], root)
    for tool in ('clang', *(['notarytool', 'stapler'] if signed else [])):
        capture([executable('xcrun'), '--find', tool], root, env)
    if git('status', '--porcelain', '--untracked-files=all', root=root):
        errors.append('工作区有未提交改动；请核对并提交，完整构建只打包HEAD，不会自动提交或stash')
    if not (root / 'LICENSE').is_file():
        errors.append('缺少pyproject.toml引用的LICENSE')
    if git('ls-files', '--', '.desktop-packaging', root=root):
        errors.append('本机打包目录中有被Git跟踪的文件，请先移出版本控制')
    if path.is_relative_to(root):
        result = subprocess.run([executable('git'), 'check-ignore', '-q', '--', str(path.relative_to(root))],
                                cwd=root, timeout=15, check=False)
        if result.returncode:
            errors.append('本机配置没有被Git忽略，请检查.gitignore')
    if signed:
        errors.extend(signing_errors(root, config, tag, env))
    print('模式：签名并提交Apple公证' if signed else '模式：完整本机测试包，不做Apple公证')
    for error in errors:
        print('未就绪：' + error)
    return not errors


def signing_errors(root, config, tag, env):
    errors = []
    version = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8-sig'))['project']['version']
    if not tag or tag != 'v' + version or version == '0.0.0':
        errors.append('签名发行需指定与pyproject版本一致的已有稳定标签，且版本不能为0.0.0')
    elif git('rev-parse', '--verify', 'refs/tags/' + tag + '^{commit}', root=root) != git('rev-parse', 'HEAD', root=root):
        errors.append('发行标签没有指向当前HEAD')
    if not config['signing_identity'] or config['signing_identity'] not in available_identities(env):
        errors.append('未配置有效的Developer ID Application分发身份；请取得证书后运行setup-signing')
    if not notary_ready(config['notary_profile'], env):
        errors.append('公证钥匙串配置不存在或无法验证；请运行setup-signing')
    return errors


def build_command(root, config, signed, tag):
    revision = ['--tag', tag] if signed else ['--commit', git('rev-parse', 'HEAD', root=root)]
    return [config['python'], str(root / 'scripts/bundles/desktop.py'), *revision, '--variant', config['variant'], '--clean']


def main(argv=None):
    parser = argparse.ArgumentParser(description='本机macOS完整打包、签名配置和只读预检查；不会发布安装包或创建Git标签')
    parser.add_argument('--config', type=Path, default=ROOT / '.desktop-packaging/config.json')
    parser.add_argument('command', nargs='?', choices=['init', 'check', 'build', 'setup-signing'], default='build')
    parser.add_argument('--signed', action='store_true', help='使用本机Developer ID与钥匙串凭据签名、公证')
    parser.add_argument('--tag', default='', help='已存在且指向HEAD的稳定标签，如v0.1.0')
    args = parser.parse_args(argv)
    path = args.config.expanduser().absolute()
    try:
        if args.command == 'init':
            initialize(ROOT, path)
            return 0
        config = read_config(path)
        if args.command == 'setup-signing':
            write_config(path, configure(config, environment(config, True)))
            print('已配置分发身份与公证钥匙串；密码未写入项目文件。')
            return 0
        tag = args.tag or config['release_tag']
        if not preflight(ROOT, path, config, args.signed, tag):
            return 2
        command = build_command(ROOT, config, args.signed, tag)
        print('构建命令：' + shlex.join(command))
        if args.command == 'build':
            subprocess.run(command, cwd=ROOT, env=environment(config, args.signed), check=True, timeout=14400)
            if args.signed:
                verify_app(ROOT / 'apps/desktop/release', environment(config, True))
            print('构建完成。正式分发前仍需核对签名、公证票据和原生安装/更新结果。')
        return 0
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print('打包准备失败：' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
