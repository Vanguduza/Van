"""Source software inventory over the exact tested wheel artifacts; no admission."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
import uuid


def source_inventory():
    root=Path(__file__).parent
    environment=json.loads((root/'environment.json').read_text())
    manifest_path=root/'locks/wheel-manifest-cp312-linux-x86_64.json'
    manifest=json.loads(manifest_path.read_text());components=[]
    for row in manifest['wheels']:
        purl='pkg:pypi/'+quote(row['name'],safe='')+'@'+quote(row['version'],safe='')
        components.append({'type':'library','bom-ref':purl,'name':row['name'],'version':row['version'],
            'purl':purl,'hashes':[{'alg':'SHA-256','content':row['sha256']}],
            'properties':[{'name':'van:hash-basis','value':'tested-distribution-wheel'},
                {'name':'van:wheel-filename','value':row['wheel']},
                {'name':'van:wheel-bytes','value':str(row['bytes'])}]})
    return {'bomFormat':'CycloneDX','specVersion':'1.6','serialNumber':'urn:uuid:'+str(uuid.uuid4()),'version':1,
        'metadata':{'timestamp':datetime.now(timezone.utc).isoformat(),
            'component':{'type':'application','name':'van-cpu-forecast-source-runtime',
                'version':environment['source_lock_sha256']},
            'properties':[{'name':'van:status','value':'CANDIDATE_SOURCE_INVENTORY_NOT_ADMISSION'},
                {'name':'van:platform','value':'Linux-x86_64-CPython3.12.15-CPU'},
                {'name':'van:base-image','value':environment['base_image']},
                {'name':'van:wheel-manifest-sha256','value':hashlib.sha256(manifest_path.read_bytes()).hexdigest()},
                {'name':'van:scope','value':'Fixed-fixture source tests;no economic or execution authority'}]},
        'components':components}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True)
    args=parser.parse_args();inventory=source_inventory()
    Path(args.output).write_text(json.dumps(inventory,indent=2)+'\n')
    print(json.dumps({'components':len(inventory['components']),'status':'SOURCE_INVENTORY_NOT_ADMISSION'}))
