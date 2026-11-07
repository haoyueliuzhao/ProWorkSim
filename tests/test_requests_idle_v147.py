"""CPU-only isolated keepalive-idle revision; no sockets or Docker."""
import importlib.util
from pathlib import Path
import threading

import pytest

from proworksim import software_benchmark_rescore_v147 as revised
from proworksim import software_benchmark_tcp_transport_v066 as original


def helpers():
    path = Path(__file__).parent/'test_software_benchmark_tcp_transport_v060.py'
    spec = importlib.util.spec_from_file_location('transport_fakes147',path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_keepalive(idle):
    f = helpers()
    scorer = revised.build_scorer(manifest_provider=lambda:{})
    relay = scorer.environment.tls.transport
    channel = f.FakeSocket([f.docker_frame(relay.packet(relay.READY)
        +f.opened(1,80)+relay.packet(relay.DATA,1,b'GET /get HTTP/1.1\r\nHost: httpbin.org\r\n\r\n')),
        f.docker_frame(relay.packet(relay.DONE))])
    peer = f.FakeSocket([b'HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK'],port=80)
    stop,clock = threading.Event(),f.Clock()
    def lapse(readers,writers,exceptional,delay):
        clock.now = idle
        return [],[],[]
    def finish(readers,writers,exceptional,delay):
        clock.now = idle+1
        stop.set()
        return [],[],[]
    steps = iter([([channel],[]),([],[peer]),([peer],[]),([],[channel]),
                  lapse,finish,([],[channel]),([channel],[])])
    def wait(readers,writers,exceptional,delay):
        value = next(steps)
        if callable(value):
            return value(readers,writers,exceptional,delay)
        clock.now += .1
        return value[0],value[1],[]
    result = relay.relay_many(channel,'8.8.8.8',instance_id='psf__requests-1766',
        resolved_ips=('8.8.8.8',),stop_event=stop,clock=clock,wait=wait,
        connector=lambda address,timeout:peer,authorize=lambda task:{},
        limits=relay.Limits(max_connections=512,max_bytes=64*1024**2,
                            max_active=16,wall_seconds=1800,idle_seconds=60))
    return result,relay


def test_keepalive_survives_old60_seconds_then_evaluation_closes_without_false_eof():
    result,_ = run_keepalive(80)
    assert result['ok'] and result['status'] == 'completed'
    assert result['connections'][0]['outcome'] == 'evaluation_stopped'
    assert result['connections'][0]['tcp_completion_evidence'] is False
    assert result['idle_seconds'] == 180 and result['wall_seconds'] == 1800
    assert result['HTTP_completion_inferred_from_byte_counts'] is False


def test_real_idle_and_other_resource_bounds_still_fail_and_original_is_unchanged():
    result,relay = run_keepalive(181)
    assert not result['ok']
    assert result['connections'][0]['outcome'] == 'upstream_idle_timeout'
    with pytest.raises(original.RelayError):
        relay.Limits(idle_seconds=181).validate()
    with pytest.raises(original.RelayError):
        relay.Limits(max_connections=513).validate()
    with pytest.raises(original.RelayError):
        relay.Limits(wall_seconds=1801).validate()
    assert original.Limits().idle_seconds == 60
    assert revised.CONSTRAINTS['maximum_containers'] == 4
    assert revised.CONSTRAINTS['maximum_real_tls_sessions'] == 4
    with pytest.raises(ValueError):
        revised.policy().cpu_set('grader',1)
