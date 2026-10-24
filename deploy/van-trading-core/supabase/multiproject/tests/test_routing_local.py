"""Real local Nginx + labelled HTTP stubs; NOT GoTrue/PostgREST/database tests.

No source secrets, Docker daemon, remote network or VAN service is used.
"""
import http.client
import json
import pathlib
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from test_render import mod
from test_hardening import two_projects


def unused_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0))
        return sock.getsockname()[1]


def handler(label):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body=json.dumps({'stub':label,'path':self.path,'headers':dict(self.headers)}).encode()
            self.send_response(200);self.send_header('Content-Length',str(len(body)))
            self.end_headers();self.wfile.write(body)
        def log_message(self,*args):
            pass
    return Handler


@unittest.skipUnless(shutil.which('nginx'),'nginx binary not installed; routing NOT TESTED')
class LocalNginxRouting(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.servers=[]; cls.threads=[]; cls.proc=None
        cls.addClassCleanup(cls.cleanup)
        cls.root=pathlib.Path(cls.temp.name)
        cls.projects=mod.validate(two_projects()); cls.ports={}
        configs=[]
        for project in cls.projects:
            port=unused_port();cls.ports[project['slug']]=port
            text=mod.emit_nginx(project).replace('listen 8080','listen 127.0.0.1:'+str(port))
            for suffix,service_port in [('auth',9999),('rest',3000),('storage',5000)]:
                label=project['slug']+'/'+suffix
                server=ThreadingHTTPServer(('127.0.0.1',0),handler(label))
                thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                cls.servers.append(server);cls.threads.append(thread)
                text=text.replace('tenant-'+project['slug']+'-'+suffix+':'+str(service_port),
                                  '127.0.0.1:'+str(server.server_port))
            configs.append(text)
        config='\n'.join(['daemon off;','master_process off;',
            'pid '+str(cls.root/'pid')+';', 'error_log '+str(cls.root/'error.log')+';',
            'events { worker_connections 128; }','http { access_log off;',*configs,'}'])
        path=cls.root/'nginx.conf';path.write_text(config)
        check=subprocess.run(['nginx','-t','-p',str(cls.root)+'/', '-c',str(path)],capture_output=True,text=True,timeout=10)
        if check.returncode:
            raise AssertionError(check.stderr)
        cls.proc=subprocess.Popen(['nginx','-p',str(cls.root)+'/', '-c',str(path)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            if cls.proc.poll() is not None:
                raise AssertionError(cls.proc.stderr.read().decode())
            try:
                for port in cls.ports.values():
                    with socket.create_connection(('127.0.0.1',port),timeout=.2):
                        pass
                return
            except OSError:
                time.sleep(.05)
        raise AssertionError('local nginx did not become reachable')

    @classmethod
    def cleanup(cls):
        if cls.proc is not None:
            cls.proc.terminate()
            try: cls.proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                cls.proc.kill();cls.proc.communicate(timeout=5)
        for server in cls.servers:
            server.shutdown();server.server_close()
        for thread in cls.threads: thread.join(timeout=2)
        cls.temp.cleanup()

    def call(self,p,path,host=None,extra=None):
        conn=http.client.HTTPConnection('127.0.0.1',self.ports[p['slug']],timeout=3)
        try:
            conn.request('GET',path,headers={'Host':host or p['hostname'],**(extra or {})})
            response=conn.getresponse();return response.status,response.read()
        finally:conn.close()

    def test_routes_both_projects_to_only_their_own_stubs(self):
        for project in self.projects:
            for suffix in ('auth','rest','storage'):
                with self.subTest(project=project['slug'],service=suffix):
                    code,body=self.call(project,'/'+suffix+'/v1/identity?probe=1')
                    self.assertEqual(code,200)
                    data=json.loads(body)
                    self.assertEqual(data['stub'],project['slug']+'/'+suffix)
                    self.assertEqual(data['path'],'/identity?probe=1')

    def test_foreign_or_unknown_host_is_rejected(self):
        for project,other in [(self.projects[0],self.projects[1]),(self.projects[1],self.projects[0])]:
            for host in (other['hostname'],'unknown.example.invalid'):
                with self.subTest(project=project['slug'],host=host):
                    code,_=self.call(project,'/auth/v1/identity',host=host)
                    self.assertEqual(code,421)

    def test_spoofed_routing_headers_removed_or_replaced(self):
        for project in self.projects:
            code,body=self.call(project,'/rest/v1/identity',extra={
                'X-Tenant-ID':'other','X-Project-ID':'other','X-Dial-Project-ID':'other',
                'X-Forwarded-Host':'evil.example','X-Forwarded-Proto':'http',
                'X-Forwarded-For':'evil','Forwarded':'for=evil;host=evil',
                'X-Forwarded-Path':'/other','X-Forwarded-Prefix':'/other',
                'Authorization':'Bearer TEST_ONLY_NOT_A_TOKEN','apikey':'TEST_ONLY_NOT_A_KEY'})
            self.assertEqual(code,200)
            headers={k.lower():v for k,v in json.loads(body)['headers'].items()}
            for removed in ('x-tenant-id','x-project-id','forwarded','x-forwarded-path'):
                self.assertNotIn(removed,headers)
            self.assertEqual(headers['x-dial-project-id'],project['project_uuid'])
            self.assertEqual(headers['x-forwarded-host'],project['hostname'])
            self.assertEqual(headers['x-forwarded-proto'],'https')
            self.assertEqual(headers['x-forwarded-prefix'],'/rest/v1')
            self.assertNotIn('evil',headers['x-forwarded-for'])
            self.assertEqual(headers['authorization'],'Bearer TEST_ONLY_NOT_A_TOKEN')

    def test_unqualified_routes_and_readiness_stay_closed(self):
        for project in self.projects:
            for path in ('/_health','/functions/v1/test','/realtime/v1/websocket'):
                with self.subTest(project=project['slug'],path=path):
                    code,_=self.call(project,path);self.assertEqual(code,503)
            code,_=self.call(project,'/project/default');self.assertEqual(code,404)


if __name__=='__main__':unittest.main()
