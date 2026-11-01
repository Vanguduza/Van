import asyncio,hashlib,json,tempfile,zipfile
from pathlib import Path
import van_gateway.auth.reenrollment as source
from test_owner_device_reenrollment_recovery import test_interrupted_migration_ddl_restarts_without_losing_original_replacement,test_two_competing_intents_have_one_exact_winner_and_normal_revoke_has_same_barrier
ROOT=Path('/workspace/van-lanes-20261101/reenrollment')
OUT=Path('/workspace/van-reenrollment-independent-review-20261101')
HAND=Path('/workspace/van-reenrollment-recovery-evidence-20261101/HANDOFF.json')
h=json.loads(HAND.read_text())
def pins():return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in h['source_files']}
before=pins();assert before==h['source_files']
(OUT/'before.json').write_text(json.dumps(before,indent=2))
async def run():
    results=[]
    for name,probe in [('migration60 interrupted DDL restart preserving original intent',test_interrupted_migration_ddl_restarts_without_losing_original_replacement),('competing original intents and normal revoke barrier',test_two_competing_intents_have_one_exact_winner_and_normal_revoke_has_same_barrier)]:
        with tempfile.TemporaryDirectory(prefix='van-lac348-review-',dir='/tmp') as temp:
            await probe(Path(temp))
        results.append({'case':name,'result':'PASS'})
    return results
results=asyncio.run(run());after=pins();assert after==before
(OUT/'after.json').write_text(json.dumps(after,indent=2))
record={'imports':{'reenrollment':source.__file__},'results':results,'source_pins_match_handoff':True,'source_unchanged_during_probe':True,'temporary_cleanup':'Owned /tmp TemporaryDirectory removed after each probe; no native transport, actual SQLite and fixture CA only.'}
(OUT/'probe-results.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
