"""Basic evidence intake, SHA-256 verification and hash-chained audit log.
Not a certified evidence-management or immutable storage system."""
import hashlib, json, os, shutil, uuid
from datetime import datetime, timezone
from pathlib import Path
from werkzeug.utils import secure_filename

ROOT = Path(__file__).resolve().parent / 'evidence_store'
ORIGINALS = ROOT / 'originals'
WORKING = ROOT / 'working'
MANIFEST = ROOT / 'manifest.json'
AUDIT = ROOT / 'audit.jsonl'
for folder in (ORIGINALS, WORKING): folder.mkdir(parents=True, exist_ok=True)

def now(): return datetime.now(timezone.utc).isoformat()
def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def read_manifest():
    if not MANIFEST.exists(): return {}
    try: return json.loads(MANIFEST.read_text(encoding='utf-8'))
    except Exception: return {}
def write_manifest(data):
    tmp=MANIFEST.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2),encoding='utf-8'); os.replace(tmp,MANIFEST)
def audit(event):
    previous='0'*64
    if AUDIT.exists():
        try: previous=json.loads(AUDIT.read_text(encoding='utf-8').splitlines()[-1])['entry_hash']
        except Exception: pass
    item={'timestamp':now(),'event':event,'previous_hash':previous}
    item['entry_hash']=hashlib.sha256(json.dumps(item,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    with AUDIT.open('a',encoding='utf-8') as f: f.write(json.dumps(item)+'\n')
    return item

def intake(file, filename, source, method, examiner):
    evidence_id='MXE-'+uuid.uuid4().hex[:12].upper()
    name=secure_filename(filename or 'evidence.bin') or 'evidence.bin'
    original=ORIGINALS/f'{evidence_id}_{name}'
    working=WORKING/f'{evidence_id}_{name}'
    digest=hashlib.sha256(file).hexdigest()
    with open(original,'xb') as f: f.write(file)
    shutil.copyfile(original,working)
    try: os.chmod(original,0o444)
    except OSError: pass
    record={'evidence_id':evidence_id,'filename':name,'size_bytes':len(file),'sha256':digest,'source':source,'acquisition_method':method,'examiner':examiner,'acquired_at':now(),'original_path':str(original.relative_to(ROOT)),'working_path':str(working.relative_to(ROOT)),'status':'stored'}
    manifest=read_manifest(); manifest[evidence_id]=record; write_manifest(manifest)
    audit({'action':'EVIDENCE_ACQUIRED','evidence_id':evidence_id,'examiner':examiner,'source':source,'method':method,'sha256':digest})
    return record

def verify(evidence_id):
    record=read_manifest().get(evidence_id)
    if not record: return None
    path=ROOT/record['original_path']; actual=sha256(path) if path.exists() else None
    ok=actual==record['sha256']
    audit({'action':'INTEGRITY_CHECK','evidence_id':evidence_id,'result':'MATCH' if ok else 'MISMATCH','actual_sha256':actual})
    return {'evidence_id':evidence_id,'integrity':'MATCH' if ok else 'MISMATCH','expected_sha256':record['sha256'],'actual_sha256':actual,'checked_at':now()}

def record_action(evidence_id, action, examiner, notes=''):
    if evidence_id not in read_manifest(): return None
    return audit({'action':'EXAMINER_ACTION','evidence_id':evidence_id,'action_detail':action,'examiner':examiner,'notes':notes})

def list_evidence(): return list(read_manifest().values())
