"""Write a local AppInstaller descriptor from a signed x64 MSIX; never upload a feed."""
from pathlib import Path
import argparse
import sys
from urllib.parse import quote, urlsplit
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def write(package: Path, out: Path, public_base: str, *, update_policy='pinned'):
    from scripts.bundles.release_artifacts import write_appinstaller
    uri = urlsplit(public_base)
    if uri.scheme != 'https' or not uri.netloc or uri.query or uri.fragment or uri.username or uri.password:
        raise ValueError('AppInstaller download base must be an HTTPS directory without credentials or query')
    if package.suffix.lower() != '.msix':
        raise ValueError('Select a single Windows x64 MSIX package')
    with zipfile.ZipFile(package) as archive:
        # Presence is a prerequisite, not cryptographic validation; native acceptance verifies the signature.
        if 'AppxSignature.p7x' not in archive.namelist():
            raise ValueError('Sign the MSIX before generating an install/update descriptor')
        identity = ET.fromstring(archive.read('AppxManifest.xml')).find('{*}Identity')
    if identity is None or identity.get('ProcessorArchitecture') != 'x64':
        raise ValueError('Windows recovery supports x64 packages only')
    base = public_base.rstrip('/')
    write_appinstaller(out, identity=identity.get('Name', ''), publisher=identity.get('Publisher', ''),
                       version=identity.get('Version', ''), self_uri=base + '/' + quote(out.name),
                       artifact_uri=base + '/' + quote(package.name), update_policy=update_policy, arch='x64')
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--public-base', required=True)
    parser.add_argument('--update-policy', choices=['pinned', 'automatic'], default='pinned')
    args = parser.parse_args()
    try:
        print(write(args.package, args.out, args.public_base, update_policy=args.update_policy))
    except (ValueError, OSError, zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
        parser.exit(1, f'Windows descriptor: {exc}\n')


if __name__ == '__main__':
    main()
