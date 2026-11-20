#!/usr/bin/env python3
"""Verify and compose preserved Pages archives without replacing old files.

Standalone stdlib verifier, also checked into the public deployment repository.
It extracts regular files manually only after checking each declared path,
digest and size. No tar symlinks, hardlinks, traversal or undeclared files.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import tarfile
import uuid

BASE_RELEASE = 'v2026.11.19-005'
BASE_SHA256 = '9ea20d8cdc10183bd9a00f914bd4b7f9583ca726b52c9c6460080334491a0a30'
LIMIT = 1_000_000_000


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(name):
    require(isinstance(name, str), 'Archive path must be text')
    if name == '.nojekyll':
        return name
    parts = PurePosixPath(name).parts
    require(bool(parts) and not name.startswith('/') and '\\' not in name and '\x00' not in name,
            'Invalid archive path')
    require(str(PurePosixPath(name)) == name and all(part not in {'.', '..'} and not part.startswith('.') for part in parts),
            'Unsafe archive path: ' + name)
    require(not any(part in {'private', 'backup', 'backups', 'sources'} for part in parts), 'Private archive path')
    require(not name.startswith(('deployment/', 'tests/', 'video-production/')), 'Source archive path')
    require(not name.startswith('courseware/') or name == 'courseware/instrument-curriculum/learning-cards.json' or name.startswith('courseware/instrument-pilot/assets/'),
            'Internal courseware cannot be published')
    require(PurePosixPath(name).suffix.lower() in {'.html', '.js', '.css', '.json', '.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.ico', '.mp4', '.webm', '.mp3', '.wav', '.flac', '.ogg', '.oga', '.m4a', '.vtt', '.pptx', '.woff', '.woff2', '.ttf'},
            'Unsupported public file type')
    return name


def entries(manifest):
    result = {}
    for item in manifest['files']:
        name = safe_path(item['path'])
        require(name not in result, 'Duplicate manifest entry: ' + name)
        require(isinstance(item['bytes'], int) and item['bytes'] >= 0, 'Invalid file size')
        require(isinstance(item['sha256'], str) and bool(re.fullmatch('[a-f0-9]{64}', item['sha256'])), 'Invalid digest')
        result[name] = item
    require(sum(item['bytes'] for item in result.values()) < LIMIT, 'Pages capacity exceeded')
    return result


def extract_checked(archive, expected, output):
    seen = set()
    with tarfile.open(archive, 'r|gz') as tar:
        for member in tar:
            name = safe_path(member.name)
            require(member.isfile() and not member.issym() and not member.islnk(), 'Archive permits regular files only')
            require(name in expected and name not in seen, 'Undeclared or duplicate archive path: ' + name)
            item = expected[name]
            require(member.size == item['bytes'], 'Archive file size mismatch: ' + name)
            target = output / name
            require(not target.exists(), 'Archive would replace an existing file: ' + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            h = hashlib.sha256()
            with target.open('xb') as out, tar.extractfile(member) as stream:
                copied = 0
                for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                    copied += len(chunk)
                    require(copied <= item['bytes'], 'Expanded size exceeds manifest')
                    h.update(chunk)
                    out.write(chunk)
            require(copied == item['bytes'] and h.hexdigest() == item['sha256'], 'Archive file digest mismatch: ' + name)
            seen.add(name)
    require(seen == set(expected), 'Archive is missing declared public files')


def compose(base_archive, base_manifest, candidate, destination):
    candidate, destination = Path(candidate), Path(destination).absolute()
    require(not destination.exists() and not destination.is_symlink(), 'Destination exists; refusing overwrite')
    receipt = json.loads((candidate / 'release.json').read_text())
    require(receipt['baseRelease'] == BASE_RELEASE and receipt['baseArchiveSha256'] == BASE_SHA256, 'Unexpected base release')
    require(digest(base_archive) == BASE_SHA256, 'Preserved archive SHA256 mismatch')
    require(digest(candidate / 'overlay.tar.gz') == receipt['overlayArchiveSha256'], 'Overlay archive SHA256 mismatch')
    require(digest(candidate / 'site-manifest.json') == receipt['siteManifestSha256'], 'Site manifest SHA256 mismatch')
    require(digest(candidate / 'overlay-manifest.json') == receipt['overlayManifestSha256'], 'Overlay manifest SHA256 mismatch')
    base_data = json.loads(Path(base_manifest).read_text())
    new_data = json.loads((candidate / 'site-manifest.json').read_text())
    overlay_data = json.loads((candidate / 'overlay-manifest.json').read_text())
    require(base_data['release'] == BASE_RELEASE, 'Base manifest release mismatch')
    require(new_data['release'] == receipt['release'] == overlay_data['release'], 'New release IDs do not match')
    base, combined, overlay = entries(base_data), entries(new_data), entries(overlay_data)
    require(not (set(base) & set(overlay)), 'Overlay replaces a preserved file')
    require(all(name.startswith(('v2/', 'assets/music-framework-v2/')) for name in overlay), 'Overlay contains an undeclared public path')
    require({**base, **overlay} == combined, 'Combined manifest changes or omits an old file')
    require(sum(item['bytes'] for item in combined.values()) == receipt['siteBytes'], 'Site byte count mismatch')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = destination.parent / (destination.name + '.incoming-' + uuid.uuid4().hex)
    stage.mkdir()
    try:
        extract_checked(base_archive, base, stage)
        extract_checked(candidate / 'overlay.tar.gz', overlay, stage)
        actual = {path.relative_to(stage).as_posix() for path in stage.rglob('*') if path.is_file()}
        require(actual == set(combined) and not any(path.is_symlink() for path in stage.rglob('*')), 'Final public file set mismatch')
        stage.rename(destination)
        return {'release': receipt['release'], 'files': len(combined), 'bytes': receipt['siteBytes'],
                'preservedFiles': len(base), 'status': 'verified-additive', 'destination': str(destination)}
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-archive', type=Path, required=True)
    parser.add_argument('--base-manifest', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(compose(args.base_archive, args.base_manifest, args.candidate, args.destination), indent=2))
    except (OSError, ValueError, KeyError, tarfile.TarError) as error:
        parser.exit(1, 'Composition refused: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
