"""Local byte-budget and GET-contract controls, without DNS or any socket."""
from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    from proworksim.software_benchmark_candidates_v054 import reference,write_new
    denied=[]
    def audit(event,_args):
        if event in {'socket.connect','socket.bind','socket.getaddrinfo','socket.sendto'}:
            denied.append(event)
            raise RuntimeError('This byte-budget control cannot use a network')
    sys.addaudithook(audit)
    path=ROOT/'tools/check_httpbin_direct_v131.py'
    spec=importlib.util.spec_from_file_location('v131_probe_budget_control',path)
    probe=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(probe)
    class MemorySocket:
        def __init__(self):self.sent=b''
        def sendall(self,raw):self.sent+=raw
        def makefile(self,*_args,**_kwargs):return io.BytesIO(b'abcdefghijk')
        def close(self):pass
    budget=probe.ApplicationBudget(10)
    socket=MemorySocket()
    limited=probe.LimitedSocket(socket,budget)
    limited.sendall(b'GET')
    stream=limited.makefile('rb')
    assert stream.read(7)==b'abcdefg' and budget.used==10
    for operation in (lambda:stream.read(1),lambda:limited.sendall(b'x')):
        try:
            operation()
        except RuntimeError:
            pass
        else:
            raise AssertionError('The shared request/response budget was exceeded')
    assert socket.sent==b'GET' and budget.used==10
    body=json.dumps({'args':{},'headers':{},'url':'https://httpbin.org/get'}).encode()
    assert probe.get_contract_valid(200,body)
    assert not probe.get_contract_valid(502,body)
    assert not probe.get_contract_valid(200,b'<html>error</html>')
    assert probe.MAX_CONNECTIONS==4 and probe.MAX_APPLICATION_BYTES==64*1024
    identity=probe.readonly_panel_identity()
    assert identity['runtime_Docker_authority_required'] is False and identity['credentials_read'] is False
    assert not denied
    out=ROOT/'artifacts/software-benchmark-v131/httpbin-probe-controls-r2/summary.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    return write_new(out,{'version':'v131-httpbin-budget-cpu-control-r1','passed':True,
        'source':reference(__file__),'probe_source':reference(path),
        'actual_LimitedSocket_and_LimitedReader_exercised':True,
        'shared_send_receive_limit_enforced':True,'DNS_resolutions':0,'network_connections':0,
        'readonly_panel_identity':identity,
        'forbidden_network_attempts':denied,'actual_public_endpoint_qualified':False,
        'model_calls':0,'Docker_operations':0})


if __name__=='__main__':
    print(json.dumps(main(),ensure_ascii=False))
