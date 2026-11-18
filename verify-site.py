import hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1]).resolve()
manifest=json.loads(Path(sys.argv[2]).read_text())
expected={x['path']:x for x in manifest['files']}
actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
assert actual==set(expected), 'Public file set mismatch'
assert not any(p.is_symlink() for p in root.rglob('*')), 'Symlinks are forbidden'
for name,record in expected.items():
    p=root/name
    assert p.resolve().is_relative_to(root), 'Escaping path'
    assert p.stat().st_size==record['bytes'], name
    assert hashlib.sha256(p.read_bytes()).hexdigest()==record['sha256'], name
assert sum(x['bytes'] for x in expected.values()) < 1_000_000_000, 'Pages size limit'
print('Verified', len(expected), 'public files for', manifest['release'])
