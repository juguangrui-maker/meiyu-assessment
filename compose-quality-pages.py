#!/usr/bin/env python3
"""Verify 005 + 006, then apply an explicitly bounded learner-entry repair."""
import argparse,importlib.util,json,shutil,uuid
from pathlib import Path
HERE=Path(__file__).resolve().parent
path=HERE/'compose_versioned_pages.py'
if not path.exists():path=HERE/'compose-versioned-pages.py'
spec=importlib.util.spec_from_file_location('quality_parent_composer',path);v2=importlib.util.module_from_spec(spec);spec.loader.exec_module(v2)
PARENT='v2026.11.21-006'
PARENT_MANIFEST='6000052c98bd5308acb640b002212df9b0a6a72b7edeccb97edc83fa4df45824'
PARENT_OVERLAY='be628d50fe12f83e61a7c478e30216d3d80d6701c0991d95685f650af5ca8567'
REPLACEMENTS={'index.html','v2/index.html','v2/music-assessment.html','v2/music-framework-entry.js'}
VERSION_FILES={'index.html','music-assessment.html','music-assessment.css','music-assessment.js','music-framework-data.js','music-framework-bank.js','music-framework-entry.js','music-foundation-data.js','music-quality-policy.js','health.json'}
def permitted(name):return name in REPLACEMENTS|{'music-quality-guard.js','music-assessment.html'} or name in {'v2.1/'+f for f in VERSION_FILES} or name.startswith(('assets/music-quality-v3/','assets/level1-revision-v1/'))
def compose(base_archive,base_manifest,parent,candidate,destination):
    parent,candidate,destination=Path(parent),Path(candidate),Path(destination).absolute();v2.require(not destination.exists(),'Destination exists')
    v2.require(v2.digest(parent/'site-manifest.json')==PARENT_MANIFEST,'006 manifest changed')
    v2.require(v2.digest(parent/'overlay.tar.gz')==PARENT_OVERLAY,'006 overlay changed')
    receipt=json.loads((candidate/'release.json').read_text());v2.require(receipt['parentRelease']==PARENT,'Wrong parent')
    for name,field in [('overlay.tar.gz','overlayArchiveSha256'),('overlay-manifest.json','overlayManifestSha256'),('site-manifest.json','siteManifestSha256')]:v2.require(v2.digest(candidate/name)==receipt[field],'Candidate hash mismatch: '+name)
    old=v2.entries(json.loads((parent/'site-manifest.json').read_text()));new=v2.entries(json.loads((candidate/'overlay-manifest.json').read_text()));combined=v2.entries(json.loads((candidate/'site-manifest.json').read_text()))
    v2.require(all(permitted(n) for n in new),'Undeclared repair path')
    v2.require(set(old)&set(new)==REPLACEMENTS,'Unexpected parent replacement set')
    v2.require({**old,**new}==combined,'Unchanged parent file omitted or altered')
    evidence=receipt['entryReplacements'];v2.require({e['path'] for e in evidence}==REPLACEMENTS,'Missing original entry receipts')
    for e in evidence:v2.require(e['before']==old[e['path']] and e['after']==new[e['path']],'Original entry digest mismatch')
    destination.parent.mkdir(parents=True,exist_ok=True);stage=destination.parent/(destination.name+'.incoming-'+uuid.uuid4().hex);patch=destination.parent/(destination.name+'.patch-'+uuid.uuid4().hex)
    try:
        v2.compose(base_archive,base_manifest,parent,stage)
        patch.mkdir();v2.extract_checked(candidate/'overlay.tar.gz',new,patch)
        for name in new:
            target=stage/name;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():v2.require(name in REPLACEMENTS and v2.digest(target)==old[name]['sha256'],'Unexpected target replacement')
            (patch/name).replace(target)
        actual={p.relative_to(stage).as_posix() for p in stage.rglob('*') if p.is_file()}
        v2.require(actual==set(combined),'Final file set mismatch')
        v2.require(not any(p.is_symlink() for p in stage.rglob('*')),'Symlink in site')
        stage.rename(destination)
        return {'status':'verified-quality-repair','files':len(combined),'bytes':sum(x['bytes'] for x in combined.values()),'originalFilesUnchanged':len(old)-len(REPLACEMENTS),'entryReplacements':sorted(REPLACEMENTS)}
    finally:
        for p in [stage,patch]:
            if p.exists():shutil.rmtree(p)
def main():
    p=argparse.ArgumentParser();p.add_argument('--base-archive',required=True,type=Path);p.add_argument('--base-manifest',required=True,type=Path);p.add_argument('--parent',required=True,type=Path);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--destination',required=True,type=Path);a=p.parse_args();print(json.dumps(compose(a.base_archive,a.base_manifest,a.parent,a.candidate,a.destination),indent=2))
if __name__=='__main__':main()
