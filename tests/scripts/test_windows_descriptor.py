"""A one-architecture feed uses the identity embedded in its package, never a guessed bundle."""
import zipfile
import xml.etree.ElementTree as ET
import pytest

from scripts.bundles.windows_descriptor import write


def test_descriptor_keeps_package_identity_and_is_pinned_by_default(tmp_path):
    package = tmp_path / '营运 app.msix'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('AppxManifest.xml', '<Package><Identity Name="Agent" Publisher="CN=Test &amp; Co" Version="1.2.3.4" ProcessorArchitecture="x64"/></Package>')
        archive.writestr('AppxSignature.p7x', b'test signature placeholder; native verification is separate')
    out = write(package, tmp_path / 'preview.appinstaller', 'https://example.invalid/releases')
    root = ET.parse(out).getroot()
    assert root.find('{*}MainBundle') is None
    main = root.find('{*}MainPackage')
    assert main.get('ProcessorArchitecture') == 'x64' and main.get('Publisher') == 'CN=Test & Co'
    assert main.get('Version') == '1.2.3.4' and '%20' in main.get('Uri')
    assert root.find('{*}UpdateSettings') is None
    write(package, out, 'https://example.invalid/releases', update_policy='automatic')
    assert ET.parse(out).getroot().find('{*}UpdateSettings') is not None


def test_unsigned_package_cannot_be_offered_as_an_installer(tmp_path):
    package = tmp_path / 'unsigned.msix'
    with zipfile.ZipFile(package, 'w') as archive:
        archive.writestr('AppxManifest.xml', '<Package/>')
    out = tmp_path / 'bad.appinstaller'
    with pytest.raises(ValueError, match='Sign the MSIX'):
        write(package, out, 'https://example.invalid')
    assert not out.exists()
