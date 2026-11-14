"""Real frozen relay function with fake sockets and replayed raw HTTP journals."""
import copy
import json
from types import ModuleType
import pytest

import test_software_benchmark_tcp_transport_v060 as controls
from proworksim import software_benchmark_tcp_transport_v066 as original
from proworksim import software_benchmark_tcp_transport_v203_2_3_r4 as observed
from proworksim.software_benchmark_expansion_episode_v069 import clone_namespace
from proworksim.software_benchmark_candidates_v054 import reference

REQUEST=b'GET /get HTTP/1.1\r\nHost: httpbin.org\r\n\r\n'
REPLY=b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok'


def run_idle(tmp_path,monkeypatch,*,reply=REPLY,port=80,pending_docker=False):
    private=ModuleType('_isolated_http_relay_control')
    private.__dict__.update(clone_namespace(original))
    observed.bind_transport(private)
    private.http_capture_context['path']=tmp_path/'http.jsonl'
    monkeypatch.setattr(controls,'relay',private)
    monkeypatch.setattr(original.socket,'socket',lambda *args,**kwargs:pytest.fail('Real socket forbidden'))
    frame=controls.docker_frame
    channel=controls.FakeSocket([frame(private.packet(private.READY)+controls.opened(1,port)
        +private.packet(private.DATA,1,REQUEST)),frame(private.packet(private.DONE))])
    peer=controls.FakeSocket([reply],port=port)
    clock=controls.Clock()
    def lapse(readers,writers,event):
        clock.now=61
        return [],[],[]
    schedule=[([channel],[]),([],[peer]),([peer],[])]
    if not pending_docker:schedule.append(([],[channel]))
    schedule += [lapse,([],[channel]),controls.stop_step,([],[channel]),([channel],[])]
    result,_=controls.run(channel,[peer],schedule,clock=clock)
    assert bytes(peer.sent)==REQUEST
    assert (private.DATA,1,reply) in private.PacketDecoder().feed(channel.sent)
    assert result['application_payload_bytes']==len(REQUEST)+len(reply)
    replay=observed.validate_capture(result['http_frame_audit'],expected_path=tmp_path/'http.jsonl')
    return result,replay


def test_proved_complete_idle_http_closure_is_replayed_and_bytes_unchanged(tmp_path,monkeypatch):
    result,replay=run_idle(tmp_path,monkeypatch)
    assert result['ok'] and result['network_errors']==[]
    assert result['connections'][0]['outcome']=='completed_http_keepalive_idle_close'
    assert replay['proved_completed_idle_closures']==1
    proof=result['connections'][0]['http_observation']
    assert proof['framing']['complete_framing'] and proof['upstream_pending']==proof['docker_pending']==0


@pytest.mark.parametrize('case',['truncated','queued','tls'])
def test_incomplete_or_undelivered_or_encrypted_exchange_keeps_original_error(tmp_path,monkeypatch,case):
    options={'reply':REPLY.replace(b'Length: 2',b'Length: 3')} if case=='truncated' else {'pending_docker':True} if case=='queued' else {'port':443}
    result,replay=run_idle(tmp_path,monkeypatch,**options)
    assert not result['ok'] and result['status']=='network_failed'
    assert result['connections'][0]['outcome']=='upstream_idle_timeout'
    assert replay['proved_completed_idle_closures']==0
    if case=='tls':assert result['http_frame_audit']['raw_http_bytes']==0


def test_tampered_complete_claim_fails_independent_stream_replay(tmp_path,monkeypatch):
    result,_=run_idle(tmp_path,monkeypatch)
    audit=copy.deepcopy(result['http_frame_audit']);path=tmp_path/'http.jsonl'
    records=[json.loads(line) for line in path.read_text().splitlines()]
    next(row for row in records if row['event']=='idle')['framing']['responses_completed']=99
    path.write_text(''.join(observed.canonical(row)+'\n' for row in records))
    audit['capture']=reference(path)
    with pytest.raises(ValueError,match='differs from raw stream'):
        observed.validate_capture(audit,expected_path=path)


def test_shared_importable_frozen_transport_cannot_be_mutated():
    with pytest.raises(ValueError,match='private'):observed.bind_transport(original)
