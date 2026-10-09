"""Inspect the actual qualified debug APK's 16KiB ELF/ZIP alignment; never install it."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,importlib.util,json,os,subprocess,sys,zipfile,struct
ROOT=Path(sys.argv[1]).resolve();REVISION=sys.argv[2];OUT=Path('/workspace/van-audit');STATE=Path('/workspace/.onboarding')
STEM='canon-corrected-android-'+REVISION[:8]+'-2026-10-09'
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def git(*args):return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()
def main():
    result=OUT/(STEM+'-native-alignment.json');log=OUT/(STEM+'-zipalign.log')
    assert not result.exists() and not log.exists()
    qualified_path=OUT/(STEM+'-result.json');qualified=json.loads(qualified_path.read_text())
    assert qualified['revision']==REVISION and qualified['qualified_as_android_debug_source_pass'] is True
    assert git('rev-parse','HEAD')==REVISION and not git('status','--porcelain=v1')
    apk=Path(qualified['apk']['path']);before=sha(apk)
    assert before==qualified['apk']['sha256']
    spec=importlib.util.spec_from_file_location('canon_native_release_validator',ROOT/'tools/release/owner_release.py')
    release=importlib.util.module_from_spec(spec);spec.loader.exec_module(release)
    libraries=[];failure=None
    try:
        with zipfile.ZipFile(apk) as archive:
            native=[entry for entry in archive.infolist() if entry.filename.startswith('lib/') and entry.filename.endswith('.so')]
            assert native and {entry.filename.split('/')[1] for entry in native}=={'arm64-v8a'}
            for entry in sorted(native,key=lambda e:e.filename):
                content=archive.read(entry);release.require_native_page_alignment(content)
                offset=struct.unpack_from('<Q',content,32)[0];size,count=struct.unpack_from('<HH',content,54)
                segments=[struct.unpack_from('<Q',content,offset+index*size+48)[0] for index in range(count)
                          if struct.unpack_from('<I',content,offset+index*size)[0]==1]
                data_offset=None
                if entry.compress_type==zipfile.ZIP_STORED:
                    archive.fp.seek(entry.header_offset);local=archive.fp.read(30)
                    assert len(local)==30 and local[:4]==b'PK\x03\x04'
                    name_size,extra_size=struct.unpack_from('<HH',local,26)
                    data_offset=entry.header_offset+30+name_size+extra_size
                    assert data_offset%16384==0
                libraries.append({'path':entry.filename,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest(),
                                  'elf_load_segment_alignments':segments,'zip_compression':entry.compress_type,
                                  'uncompressed_zip_data_offset':data_offset,'supports_16k_pages':True})
    except Exception as exc:
        failure={'type':type(exc).__name__,'message':str(exc)}
    tool=STATE/'android-sdk/build-tools/36.0.0/zipalign';command=[str(tool),'-c','-P','16','-v','4',str(apk)]
    with log.open('w') as output:code=subprocess.call(command,stdout=output,stderr=subprocess.STDOUT)
    after=sha(apk);passed=failure is None and bool(libraries) and code==0 and before==after
    record={'schema_version':1,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'revision':REVISION,
            'scope':'actual qualified debug APK ELF/ZIP alignment only; no owner release or deployment',
            'apk':{'path':str(apk),'sha256_before':before,'sha256_after':after,'bytes':apk.stat().st_size},
            'qualified_android_receipt':{'path':str(qualified_path),'sha256':sha(qualified_path)},
            'source_release_validator_sha256':sha(ROOT/'tools/release/owner_release.py'),'runner_sha256':sha(Path(__file__)),
            'native_libraries':libraries,'native_inspection_failure':failure,
            'zipalign':{'command':command,'exit_code':code,'binary_sha256':sha(tool),'log_path':str(log),'log_sha256':sha(log)},
            'qualified_16kb_native_alignment':passed,'production_signing_verified':False,'owner_release_built':False,
            'physical_handset_tests_executed':0,'source_head_after':git('rev-parse','HEAD'),'source_status_after':git('status','--porcelain=v1')}
    result.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'result':str(result),'native_libraries':len(libraries),'passed':passed,'failure':failure,'zipalign_exit_code':code}))
    return 0 if passed else 1
if __name__=='__main__':sys.exit(main())
