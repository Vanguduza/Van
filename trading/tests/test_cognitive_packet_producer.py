"""Real first-pass HTTP transport and account worker, synthetic qualified fixture identities."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
import pytest
from vati.cognition.packet_producer import PacketProducer
from vati.cognition.fabric import FabricError, TriAnalystPlane
from vati.core.ledger import Ledger
from test_vati_cognitive_fabric import setup_plane, packet, second


def sources():
    return [{'enabled':True,'provider_product':p,'source_id':p,'analysis_lineage_id':lineage,
        'endpoint':'http://127.0.0.1:1/packet'} for p,lineage in [('van-native','native-lineage'),('openai-programmatic','openai-lineage')]]


def qualified():
    from vati.core.canonical import canonical_hash
    plane, _, signal=setup_plane()
    ev=plane.evidence(symbol='XAUUSD',state={'market_data_hash':canonical_hash(['synthetic-market'])},source_refs=[canonical_hash(['synthetic-source'])],now_ms=102,deadline_ms=1000)
    for source in sources():
        plane.qualified[source['provider_product']].update(source_id=source['source_id'],analysis_lineage_id=source['analysis_lineage_id'],approved_data_classes=['INTERNAL_SANITIZED'])
    return plane,ev,signal


def test_real_loopback_http_independent_first_pass_to_existing_admission_gate():
    plane,ev,_=qualified();seen=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            seen.append(request)
            result=packet(ev) if request['provider_product']=='van-native' else second(ev)
            body=json.dumps(result).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        configured=[{**s,'endpoint':f'http://127.0.0.1:{server.server_port}/packet'} for s in sources()]
        producer=PacketProducer(plane,sources=configured,clock=lambda:104)
        assert [r['state'] for r in producer.poll()]==['ACCEPTED','ACCEPTED']
        assert len(plane._rows('CognitiveAdmissionEnvelope'))==1
        assert seen[0]['context']==seen[1]['context']
        assert seen[0]['context']['prior_lane_outputs_seen']==[]
        assert 'Watch breakout' not in json.dumps(seen)
        assert 'BUY_IF_TRIGGER' not in json.dumps(seen)
        assert producer.poll()==[]
        assert len(seen)==2
        assert not list(plane.ledger.iter(kind=__import__('vati.core.events',fromlist=['EventKind']).EventKind.RISK_DECISION))
    finally:server.shutdown();server.server_close();thread.join()


@pytest.mark.parametrize('mode',['missing-qualification','same-lineage','unapproved-data','unsanitized-state','wrong-model','paid','secret-echo','timeout','late'])
def test_transport_and_qualification_refusals_never_admit(mode,monkeypatch):
    plane,ev,_=qualified();configured=sources()[:1]
    if mode=='missing-qualification':plane.qualified={}
    if mode=='same-lineage':plane.qualified['van-native']['analysis_lineage_id']='other-source'
    if mode=='unapproved-data':plane.qualified['van-native']['approved_data_classes']=[]
    if mode=='unsanitized-state':
        from vati.core.canonical import canonical_hash
        ev=plane.evidence(symbol='XAUUSD',state={'private_owner_goal':'must not be sent'},source_refs=[canonical_hash(['synthetic-source'])],now_ms=102,deadline_ms=1000)
    if mode=='paid':
        with pytest.raises(FabricError,match='NOT_T2'):PacketProducer(plane,sources=[{**configured[0],'provider_product':'muse-spark-api'}],clock=lambda:104)
        return
    if mode=='secret-echo':
        monkeypatch.setenv('PACKET_TEST_CREDENTIAL','synthetic-do-not-persist')
        configured[0]['credential_ref']='env://PACKET_TEST_CREDENTIAL'
    calls=[]
    def transport(**request):
        calls.append(request)
        if mode=='timeout':raise TimeoutError('private endpoint/credential details')
        response=packet(ev)
        if mode=='wrong-model':response['model_or_agent_id']='wrong-model'
        if mode=='secret-echo':return 200,b'synthetic-do-not-persist'
        return 200,json.dumps(response).encode()
    stamps=iter([104,104,1001,1001,1001,1001,1001]) if mode=='late' else None
    producer=PacketProducer(plane,sources=configured,clock=lambda:next(stamps) if stamps else 104,transport=transport)
    result=producer.poll()
    if mode in ('missing-qualification','same-lineage','unapproved-data','unsanitized-state'):assert calls==[]
    else:assert result[0]['state']=='REFUSED'
    assert plane._rows('CognitiveAdmissionEnvelope')==[]
    assert 'synthetic-do-not-persist' not in json.dumps(plane.projection())
    assert 'private endpoint' not in json.dumps(plane.projection())


def test_actual_account_worker_uses_its_own_connection_and_default_is_disabled(tmp_path):
    from vati.app.account_service import AccountCoordinatorService
    service=AccountCoordinatorService(SimpleNamespace(cognitive_fabric={}))
    service._start_packet_worker();assert service._packet_worker is None
    path=tmp_path/'worker.sqlite';ledger=Ledger(path);plane=TriAnalystPlane(ledger,account_alias='test')
    service=AccountCoordinatorService(SimpleNamespace(account_alias='test',ledger=str(path),poll_seconds=.01,
        cognitive_fabric={'packet_sources':sources()}),clock=lambda:104)
    service.tri_analyst=plane;service._start_packet_worker()
    assert service._packet_worker.is_alive()
    service._packet_worker_stop.set();service._packet_worker.join(timeout=1)
    assert not service._packet_worker.is_alive()
    assert list(ledger.iter())==[]  # No qualifications/discoveries => no model request or fabricated activity.
    ledger.close()


def test_actual_account_worker_calls_real_http_and_writes_admission_without_main_loop(tmp_path):
    from vati.app.account_service import AccountCoordinatorService
    from vati.core.events import make_event, EventKind
    original,ev,_=qualified();path=tmp_path/'actual-worker.sqlite';ledger=Ledger(path)
    for event in original.ledger.iter():ledger.append(event)
    ledger.append(make_event(EventKind.COGNITIVE_FABRIC,'vati-account-service',
        {'record_type':'ProviderQualification','account_alias':'test','providers':original.qualified},event_time_ms=103,received_time_ms=103))
    seen=[];called=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])));seen.append(request)
            response=packet(ev) if request['provider_product']=='van-native' else second(ev)
            body=json.dumps(response).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
            if len(seen)==2:called.set()
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    configured=[{**s,'endpoint':f'http://127.0.0.1:{server.server_port}/packet'} for s in sources()]
    service=AccountCoordinatorService(SimpleNamespace(account_alias='test',ledger=str(path),poll_seconds=.01,cognitive_fabric={'packet_sources':configured}),clock=lambda:104)
    service.tri_analyst=TriAnalystPlane(ledger,account_alias='test')
    try:
        service._start_packet_worker();assert called.wait(timeout=2)
        deadline=time.monotonic()+2
        while not service.tri_analyst._rows('CognitiveAdmissionEnvelope') and time.monotonic()<deadline:time.sleep(.01)
        assert len(service.tri_analyst._rows('CognitiveAdmissionEnvelope'))==1
        assert seen[0]['context']==seen[1]['context']
        assert ledger.count(EventKind.RISK_DECISION)==0
        assert ledger.count(EventKind.EXECUTION_RECEIPT)==0
        assert service.coordinator is None  # Main order pipeline was never constructed or called.
    finally:
        service._packet_worker_stop.set();service._packet_worker.join(timeout=2)
        server.shutdown();server.server_close();thread.join();ledger.close()


@pytest.mark.parametrize('field,value',[('directional_thesis',{'unsupported':'object'}),
    ('directional_thesis',['BUY']),('uncertainty',{}),('prior_lane_outputs_seen',''),
    ('supporting_evidence',[{}]),('regime_assessment',{}),('generated_at_ms',True)])
def test_actual_http_malformed_packet_is_refused_without_poisoning_next_poll(field,value):
    plane,ev,_=qualified();calls=[]
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers['Content-Length']));calls.append(1)
            response=packet(ev);response[field]=value;body=json.dumps(response).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        configured=[{**sources()[0],'endpoint':f'http://127.0.0.1:{server.server_port}/packet'}]
        producer=PacketProducer(plane,sources=configured,clock=lambda:104)
        result=producer.poll()
        assert result[0]['state']=='REFUSED'
        assert result[0]['reason'].startswith('PACKET_')
        assert result[0]['content_hash']
        assert plane._rows('TradeAnalysisPacket')==[]
        assert plane._rows('CognitiveAdmissionEnvelope')==[]
        assert not any(r['state']=='ACCEPTED' for r in plane._rows('PacketTransportResult'))
        assert producer.poll()==[] and len(calls)==1
        # Other valid/native evidence still consolidates: the rejected response never persists.
        plane.packet(packet(ev),now_ms=104);plane.packet(second(ev),now_ms=104)
        assert plane.admission(candidate_id='signal',evidence_epoch=ev['evidence_epoch'],now_ms=105)['independence_gate_passed']
    finally:server.shutdown();server.server_close();thread.join()
