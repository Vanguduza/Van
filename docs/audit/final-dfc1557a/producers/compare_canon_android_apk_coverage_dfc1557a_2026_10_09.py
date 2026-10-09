"""Compare actual signed APK contents and ZIP layout without changing either APK."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,struct,zipfile

OUT=Path('/workspace/van-audit')
OLD_ROOT=OUT/'canon-android-build-fix-2026-10-09'
ROOT=OUT/'canon-chromium-runtime-fix-2026-10-09'
REVISION='dfc1557ab99ad8d41cf84714e1bb671e89b045e6'
RESULT=OUT/'canon-android-apk-content-layout-dfc1557a-2026-10-09.json'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda:stream.read(1024*1024),b''):h.update(data)
    return h.hexdigest()

def entries_and_layout(path):
    rows={};ranges=[];names=[]
    with zipfile.ZipFile(path) as z:
        for entry in z.infolist():
            names.append(entry.filename)
            with z.open(entry) as stream:
                h=hashlib.sha256()
                for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
            z.fp.seek(entry.header_offset);header=z.fp.read(30)
            assert len(header)==30 and header[:4]==b'PK\x03\x04'
            name_size,extra_size=struct.unpack_from('<HH',header,26)
            data_offset=entry.header_offset+30+name_size+extra_size
            end=data_offset+entry.compress_size;descriptor_size=0
            if entry.flag_bits&8:
                z.fp.seek(end);signature=z.fp.read(4)
                descriptor_size=(4 if signature==b'PK\x07\x08' else 0)+(20 if max(entry.file_size,entry.compress_size)>0xffffffff else 12)
                end+=descriptor_size
            rows[entry.filename]={'bytes':entry.file_size,'sha256':h.hexdigest(),'compressed_bytes':entry.compress_size,
                                  'compression':entry.compress_type,'local_header_offset':entry.header_offset,
                                  'local_name_bytes':name_size,'local_extra_bytes':extra_size,'data_offset':data_offset,
                                  'descriptor_bytes':descriptor_size,'entry_end':end}
            ranges.append((entry.header_offset,end,entry.filename))
        assert len(names)==len(set(names)),'Duplicate APK ZIP entry names'
        cd_offset=z.start_dir
        z.fp.seek(cd_offset-24);footer=z.fp.read(24)
        assert footer[8:]==b'APK Sig Block 42'
        block_size=struct.unpack_from('<Q',footer,0)[0]+8;block_start=cd_offset-block_size
        z.fp.seek(block_start);assert struct.unpack('<Q',z.fp.read(8))[0]==block_size-8
        z.fp.seek(max(0,path.stat().st_size-65557));tail=z.fp.read();marker=tail.rfind(b'PK\x05\x06')
        assert marker>=0
        eocd_offset=path.stat().st_size-len(tail)+marker
        assert eocd_offset+22+struct.unpack_from('<H',tail,marker+20)[0]==path.stat().st_size
        assert struct.unpack_from('<I',tail,marker+16)[0]==cd_offset
        gaps=[];previous=0
        for start,end,name in sorted(ranges):
            assert start>=previous and end<=block_start,'Overlapping referenced entries/signature block'
            if start>previous:gaps.append((previous,start))
            previous=end
        if block_start>previous:gaps.append((previous,block_start))
        gap_records=[]
        for start,end in gaps:
            z.fp.seek(start);data=z.fp.read(end-start)
            gap_records.append({'start':start,'end':end,'bytes':end-start,'sha256':hashlib.sha256(data).hexdigest(),
                                'zero_bytes':data.count(b'\0'),'contains_unreferenced_zip_local_header':b'PK\x03\x04' in data})
        categories={'compressed_entry_data':sum(x['compressed_bytes'] for x in rows.values()),
                    'local_fixed_headers_and_names':sum(30+x['local_name_bytes'] for x in rows.values()),
                    'local_extra_padding_fields':sum(x['local_extra_bytes'] for x in rows.values()),
                    'data_descriptors':sum(x['descriptor_bytes'] for x in rows.values()),
                    'unreferenced_gaps':sum(x['bytes'] for x in gap_records),'apk_signing_block':block_size,
                    'central_directory':eocd_offset-cd_offset,'eocd_and_comment':path.stat().st_size-eocd_offset}
        assert sum(categories.values())==path.stat().st_size
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path),'entry_count':len(rows),'entries':rows,
            'layout_categories':categories,'unreferenced_gaps':gap_records}

def main():
    assert not RESULT.exists()
    old_receipt=OUT/'canon-corrected-android-ffa18d57-2026-10-09-result.json'
    new_receipt=OUT/'canon-corrected-android-dfc1557a-2026-10-09-result.json'
    old_qual=json.loads(old_receipt.read_text());new_qual=json.loads(new_receipt.read_text())
    assert old_qual['qualified_as_android_debug_source_pass'] and new_qual['qualified_as_android_debug_source_pass']
    assert new_qual['revision']==REVISION
    old=entries_and_layout(Path(old_qual['apk']['path']));new=entries_and_layout(Path(new_qual['apk']['path']))
    assert old['sha256']==old_qual['apk']['sha256'] and new['sha256']==new_qual['apk']['sha256']
    generated=ROOT/'android/app/build/generated/voice-assets'
    sealed={p.relative_to(generated).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)}
            for p in sorted(generated.rglob('*')) if p.is_file()}
    assert len(sealed)==46
    expected={'assets/'+name:record for name,record in sealed.items()}
    for apk in (old,new):
        assert {name for name in apk['entries'] if name.startswith('assets/voice/')}==set(expected)
        assert all({k:apk['entries'][name][k] for k in ('bytes','sha256')}==record for name,record in expected.items())
    manifest=ROOT/'android/voice/voice_asset_manifest.json'
    assert (generated/'voice/voice_asset_manifest.json').read_bytes()==manifest.read_bytes()
    pinned=json.loads(manifest.read_text());assert len(pinned['files'])==45 and pinned['owner_profile_included'] is False
    for weight in pinned['files']:
        actual=new['entries']['assets/voice/bundle/'+weight['path']]
        assert actual['bytes']==weight['size'] and actual['sha256']==weight['sha256']
    native_qual=json.loads((OUT/'canon-corrected-android-dfc1557a-2026-10-09-native-alignment.json').read_text())
    natives={x['path']:{'bytes':x['bytes'],'sha256':x['sha256']} for x in native_qual['native_libraries']}
    assert len(natives)==7
    for apk in (old,new):
        assert {name for name in apk['entries'] if name.startswith('lib/') and name.endswith('.so')}==set(natives)
        assert all({k:apk['entries'][name][k] for k in ('bytes','sha256')}==value for name,value in natives.items())
    old_names=set(old['entries']);new_names=set(new['entries'])
    changed=[]
    for name in sorted(old_names&new_names):
        left=old['entries'][name];right=new['entries'][name]
        if any(left[k]!=right[k] for k in ('bytes','sha256','compressed_bytes','compression')):
            changed.append({'path':name,'before':left,'after':right,'content_changed':left['sha256']!=right['sha256']})
    category_delta={k:new['layout_categories'][k]-old['layout_categories'][k] for k in new['layout_categories']}
    assert sum(category_delta.values())==new['bytes']-old['bytes']
    assert sha(Path(old['path']))==old['sha256'] and sha(Path(new['path']))==new['sha256']
    record={'schema_version':1,'recorded_at_utc':datetime.now(timezone.utc).isoformat(),'revision':REVISION,
            'scope':'actual signed debug APK contents/layout only; no rebuild or deployment',
            'old_qualified_receipt_sha256':sha(old_receipt),'new_qualified_receipt_sha256':sha(new_receipt),
            'old_apk':old,'new_apk':new,'entry_sets_equal':old_names==new_names,
            'only_in_old':sorted(old_names-new_names),'only_in_new':sorted(new_names-old_names),
            'changed_entries':changed,'size_delta':new['bytes']-old['bytes'],'layout_category_delta':category_delta,
            'source_pinned_voice_files_and_manifest_verified':True,'generic_weights_verified':45,'voice_entries_verified':46,
            'all_seven_native_libraries_byte_identical_and_16k_qualified':True,'apks_unchanged_during_comparison':True,
            'production_owner_profile_verified':False,'physical_handset_tests_executed':0,'runner_sha256':sha(Path(__file__))}
    RESULT.write_text(json.dumps(record,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'result':str(RESULT),'entry_sets_equal':record['entry_sets_equal'],'entries':new['entry_count'],
                      'changed_entries':[{'path':x['path'],'content_changed':x['content_changed'],'size_delta':x['after']['bytes']-x['before']['bytes'],
                                          'compressed_delta':x['after']['compressed_bytes']-x['before']['compressed_bytes']} for x in changed],
                      'size_delta':record['size_delta'],'layout_category_delta':category_delta,
                      'all46_voice_entries_match_pins':True,'all7_natives_identical':True}),flush=True)

if __name__=='__main__':main()
