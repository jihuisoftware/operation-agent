"""Local packaging keeps machine settings private and signing explicitly fail-closed."""
import json
import subprocess
import sys

import pytest

from scripts import package_desktop as package
from scripts.bundles import local_signing


def config():
    return {'python': sys.executable, 'target': package.current_target(), 'developer_dir': '/fixture/Xcode', 'variant': 'bundled',
            'github_repository': 'fixture/operations', 'update_base_url': '', 'release_tag': '',
            'signing_identity': 'Developer ID Application: Fixture (ABCDEFGHIJ)', 'notary_profile': 'fixture-notary'}


def test_development_revoked_and_unrelated_certificates_are_not_release_identities():
    output = '\n'.join([
        '  1) ' + 'A' * 40 + ' "Apple Development: Fixture (ABCDEFGHIJ)"',
        '  2) ' + 'B' * 40 + ' "Developer ID Application: Revoked (ABCDEFGHIJ)" (CSSMERR_TP_CERT_REVOKED)',
        '  3) ' + 'C' * 40 + ' "Developer ID Application: Fixture (ABCDEFGHIJ)"',
        '  4) ' + 'D' * 40 + ' "Developer ID Installer: Fixture (ABCDEFGHIJ)"',
    ])
    assert local_signing.identities(output) == ['Developer ID Application: Fixture (ABCDEFGHIJ)']


def test_unsigned_environment_never_inherits_signing_credentials_or_update_origin(monkeypatch):
    for key in package.SIGNING_ENV:
        monkeypatch.setenv(key, 'fixture-secret')
    monkeypatch.setenv('CLOUDFLARE_R2_PUBLIC_URL', 'https://unrelated.invalid')
    value = package.environment(config(), False)
    assert not set(package.SIGNING_ENV) & value.keys()
    assert value['CSC_IDENTITY_AUTO_DISCOVERY'] == 'false'
    assert 'CLOUDFLARE_R2_PUBLIC_URL' not in value
    signed = package.environment(config(), True)
    assert signed['CSC_NAME'] == 'Fixture (ABCDEFGHIJ)'
    assert signed['APPLE_NOTARY_PROFILE'] == 'fixture-notary'
    assert 'CSC_KEY_PASSWORD' not in signed and 'APPLE_API_KEY' not in signed


@pytest.mark.platforms('macos')
def test_initialization_writes_private_config_and_working_launcher_without_overwriting(tmp_path, monkeypatch):
    root = tmp_path / 'project with spaces'
    root.mkdir()
    (root / 'scripts').mkdir()
    (root / 'scripts/package_desktop.py').write_text('import sys\nprint(sys.argv[1:])\n')
    monkeypatch.setattr(package, 'repository', lambda _: 'fixture/operations')
    monkeypatch.setattr(package, 'capture', lambda *args: '/Applications/Xcode.app/Contents/Developer')
    path = root / '.desktop-packaging/config.json'
    package.initialize(root, path)
    saved = package.read_config(path)
    assert saved['target'] == package.current_target() and saved['variant'] == 'bundled'
    assert saved['signing_identity'] == ''
    assert path.stat().st_mode & 0o777 == 0o600
    result = subprocess.run([str(path.parent / 'package.sh'), 'check'], capture_output=True,
                            text=True, encoding='utf-8', check=True, timeout=10)
    assert str(path) in result.stdout and 'check' in result.stdout
    with pytest.raises(ValueError, match='未覆盖'):
        package.initialize(root, path)


@pytest.mark.parametrize('extra', [{'password': 'fixture-secret'}, {'update_base_url': 'https://user:secret@example.com'}, {'update_base_url': 'http://example.com'}])
def test_configuration_refuses_plaintext_password_fields_and_credential_urls(tmp_path, extra):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({**config(), **extra}))
    with pytest.raises(ValueError):
        package.read_config(path)


def test_missing_distribution_identity_prevents_keychain_setup(monkeypatch):
    monkeypatch.setattr(local_signing, 'available_identities', lambda _: [])
    monkeypatch.setattr(local_signing.subprocess, 'run', lambda *_a, **_kw: pytest.fail('不能开始公证凭据写入'))
    with pytest.raises(ValueError, match='Developer ID Application'):
        local_signing.configure(config(), {})


def test_build_uses_canonical_builder_and_never_passes_upload_or_secret_arguments(tmp_path, monkeypatch):
    monkeypatch.setattr(package, 'git', lambda *args, **kw: 'a' * 40)
    normal = package.build_command(tmp_path, config(), False, '')
    assert normal == [sys.executable, str(tmp_path / 'scripts/bundles/desktop.py'), '--commit', 'a' * 40, '--variant', 'bundled', '--clean']
    signed = package.build_command(tmp_path, config(), True, 'v0.1.0')
    assert '--tag' in signed and '--commit' not in signed and '--publish' not in signed


def test_signed_preflight_reports_missing_signing_and_notary_credentials(tmp_path, monkeypatch):
    (tmp_path / 'pyproject.toml').write_text('[project]\nversion="0.1.0"\n')
    monkeypatch.setattr(package, 'git', lambda *args, **kwargs: 'a' * 40)
    monkeypatch.setattr(package, 'available_identities', lambda _: [])
    monkeypatch.setattr(package, 'notary_ready', lambda *_: False)
    errors = package.signing_errors(tmp_path, config(), 'v0.1.0', {})
    assert len(errors) == 2 and any('分发身份' in error for error in errors) and any('公证' in error for error in errors)


def test_failed_gatekeeper_validation_never_reports_signed_build_as_verified(tmp_path, monkeypatch):
    (tmp_path / 'mac-arm64/Application.app').mkdir(parents=True)
    monkeypatch.setattr(local_signing, 'executable', lambda name: name)
    calls = []
    def execute(argv, **kwargs):
        calls.append(argv)
        if argv[0] == 'spctl':
            raise subprocess.CalledProcessError(1, argv)
    monkeypatch.setattr(local_signing.subprocess, 'run', execute)
    with pytest.raises(subprocess.CalledProcessError):
        local_signing.verify_app(tmp_path, {})
    assert [row[0] for row in calls] == ['codesign', 'spctl']
