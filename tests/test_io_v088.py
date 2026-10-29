from contextlib import contextmanager
import errno
import fcntl
import io
import json
import os
import resource
import select
import socket
import struct
import threading
import time
from types import SimpleNamespace

import pytest

from proworksim import software_benchmark_io_v088 as fixed
from proworksim import software_benchmark_docker_actor_v066 as original


@pytest.fixture(autouse=True)
def own_test_process_descriptor_capacity():
    before = resource.getrlimit(resource.RLIMIT_NOFILE)
    if before[1] <= 2049:
        pytest.skip('The test process hard limit cannot allocate a descriptor above FD_SETSIZE')
    if before[0] <= 2049:
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(4096, before[1]), before[1]))
    try:
        yield
    finally:
        resource.setrlimit(resource.RLIMIT_NOFILE, before)


@contextmanager
def high_socket_pair():
    source, peer = socket.socketpair()
    descriptor = fcntl.fcntl(source.fileno(), fcntl.F_DUPFD_CLOEXEC, 2048)
    source.close()
    try:
        high = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM, fileno=descriptor)
    except BaseException:
        os.close(descriptor)
        peer.close()
        raise
    try:
        yield high, peer
    finally:
        high.close()
        peer.close()


@contextmanager
def high_pipe():
    low_read, low_write = os.pipe()
    read = fcntl.fcntl(low_read, fcntl.F_DUPFD_CLOEXEC, 2048)
    write = fcntl.fcntl(low_write, fcntl.F_DUPFD_CLOEXEC, 2048)
    os.close(low_read)
    os.close(low_write)
    os.set_blocking(read, False)
    os.set_blocking(write, False)
    try:
        yield read, write
    finally:
        for descriptor in (read, write):
            try:
                os.close(descriptor)
            except OSError:
                pass


def frame(stream, data):
    return struct.pack('>BxxxI', stream, len(data))+data


def test_real_high_descriptor_select_failure_and_poll_readiness_order():
    with high_socket_pair() as (channel, peer):
        assert channel.fileno() >= 2048
        peer.sendall(b'ready')
        with pytest.raises(ValueError, match='filedescriptor out of range'):
            select.select([channel], [], [], 0)
        read, write, exceptional = fixed.poll_select([channel, channel.fileno(), channel], [channel], [], .1)
        assert read == [channel, channel.fileno(), channel]
        assert write == [channel] and exceptional == []
        assert channel.recv(5) == b'ready'


def test_poll_timeout_eof_and_invalid_descriptor_are_not_success():
    with high_socket_pair() as (channel, peer):
        assert fixed.poll_select([channel], [], [], .01) == ([], [], [])
        peer.shutdown(socket.SHUT_WR)
        assert fixed.poll_select([channel], [], [], .1)[0] == [channel]
        assert channel.recv(1) == b''
        descriptor = channel.fileno()
        channel.close()
        with pytest.raises(OSError) as error:
            fixed.poll_select([descriptor], [], [], 0)
        assert error.value.errno == errno.EBADF
    with pytest.raises(ValueError):
        fixed.poll_select([-1], [], [], 0)
    with pytest.raises(ValueError):
        fixed.poll_select([], [], [], -.01)


def test_exceptional_only_peer_hup_keeps_original_timeout():
    with high_socket_pair() as (channel, peer):
        peer.close()
        observed = select.poll()
        observed.register(channel, select.POLLPRI)
        assert observed.poll(0)[0][1] & select.POLLHUP
        started = time.monotonic()
        assert fixed.poll_select([], [], [channel], .04) == ([], [], [])
        assert time.monotonic()-started >= .035


def test_private_fifo_high_fd_frames_deadline_and_eof():
    fifo = fixed.fifo_module()
    with high_pipe() as (read, write):
        fifo.write_frame(write, {'id': 1, 'payload': '中文'}, time.monotonic()+.1)
        fifo.write_frame(write, {'id': 2}, time.monotonic()+.1)
        reader = fifo.LineReader(read)
        assert reader.read(time.monotonic()+.1) == {'id': 1, 'payload': '中文'}
        assert reader.read(time.monotonic()+.1) == {'id': 2}
        with pytest.raises(TimeoutError):
            reader.read(time.monotonic()+.01)
        os.close(write)
        with pytest.raises(EOFError):
            reader.read(time.monotonic()+.1)
    assert fixed.original_fifo.LineReader.read.__globals__['select'] is select


def test_fifo_full_pipe_preserves_write_deadline_without_retrying_frame():
    fifo = fixed.fifo_module()
    with high_pipe() as (_, write):
        while True:
            try:
                os.write(write, b'x'*4096)
            except BlockingIOError:
                break
        with pytest.raises(TimeoutError, match='write deadline'):
            fifo.write_frame(write, {'id': 1}, time.monotonic()+.01)


def test_docker_channel_high_fd_demultiplexing_order_and_clean_eof():
    with high_socket_pair() as (stream, peer):
        stderr = io.BytesIO()
        channel = fixed.DockerStdioChannel(stream, stderr)
        data = frame(1, b'{"id":1}\n{"id":')+frame(2, b'warning\n')+frame(1, b'2}\n')
        peer.sendall(data)
        peer.shutdown(socket.SHUT_WR)
        assert channel.readline(time.monotonic()+.1) == b'{"id":1}\n'
        assert channel.readline(time.monotonic()+.1) == b'{"id":2}\n'
        assert stderr.getvalue() == b'warning\n'
        assert channel.readline(time.monotonic()+.1) == b''
        assert channel.eof


def test_docker_channel_deadline_and_partial_frame_remain_fail_closed():
    with high_socket_pair() as (stream, peer):
        channel = fixed.DockerStdioChannel(stream, io.BytesIO())
        with pytest.raises(TimeoutError, match='deadline'):
            channel.readline(time.monotonic()+.01)
        peer.sendall(frame(1, b'{"incomplete":'))
        peer.shutdown(socket.SHUT_WR)
        with pytest.raises(RuntimeError, match='partial JSON line'):
            channel.readline(time.monotonic()+.1)


def test_actual_private_episode_and_provider_channels_both_use_poll():
    from proworksim.software_benchmark_episodes_v076 import api_episode
    from proworksim import software_benchmark_episode_v066 as original_episode
    delegate = fixed.bind_episode(api_episode(SimpleNamespace()))
    namespace = delegate.run_episode.__globals__
    assert namespace['_run'].__globals__['DockerStdioChannel'] is fixed.DockerStdioChannel
    assert delegate.OwnedActorPair.attach.__globals__['DockerStdioChannel'] is fixed.DockerStdioChannel
    assert original_episode.DockerStdioChannel is original.DockerStdioChannel
    assert original.OwnedActorPair.attach.__globals__['DockerStdioChannel'] is original.DockerStdioChannel
    assert original.DockerStdioChannel.readline.__globals__['select'] is select
    with pytest.raises(PermissionError):
        fixed.bind_episode(original_episode)
    with high_socket_pair() as (stream, peer):
        pair = object.__new__(delegate.OwnedActorPair)
        pair.objects = {'actor': SimpleNamespace(id='synthetic')}
        pair.channels = []
        pair.client = SimpleNamespace(api=SimpleNamespace(attach_socket=lambda *a, **kw: stream))
        channel = pair.attach('actor', io.BytesIO())
        peer.sendall(frame(1, b'{"synthetic":true}\n'))
        assert isinstance(channel, fixed.DockerStdioChannel)
        assert channel.readline(time.monotonic()+.1) == b'{"synthetic":true}\n'


def test_actual_model_ready_and_one_synthetic_request_use_high_fd_channel(monkeypatch):
    from proworksim import software_benchmark_host_usage_v066 as broker
    from proworksim import software_benchmark_dispatch_v066 as policy
    monkeypatch.setattr(policy, 'require_v066_allowed', lambda *args, **kwargs: None)
    stop, ready = threading.Event(), threading.Event()

    class SyntheticTransport:
        port, timeout_seconds, calls = 18219, 1800, 0

        def validate_identity(self, slot):
            assert slot == 'synthetic-test'

        def post(self, path, payload):
            assert path == '/chat/completions' and payload == {'synthetic': True}
            self.calls += 1
            stop.set()
            return {'synthetic_result': True}

    transport = SyntheticTransport()
    with high_socket_pair() as (stream, peer):
        channel = fixed.DockerStdioChannel(stream, io.BytesIO())
        peer.sendall(frame(1, fixed.original_fifo.encoded_frame(
            {'type': 'model_bridge_ready', 'version': broker.WIRE_VERSION})))
        peer.sendall(frame(1, fixed.original_fifo.encoded_frame(
            {'id': 1, 'path': '/chat/completions', 'payload': {'synthetic': True}})))
        result = broker.serve_model_channel(channel, endpoint='http://127.0.0.1:18219',
            key_file=None, deadline=time.monotonic()+.5, stop_event=stop,
            slot_id='synthetic-test', on_ready=ready.set, transport=transport)
        assert result['ready'] and ready.is_set() and transport.calls == 1
        assert result['requests'] == result['generation_requests'] == 1
        assert result['status'] == 'stopped_after_controller'
        peer.settimeout(.2)
        received = bytearray()
        while received.count(b'\n') < 2:
            received.extend(peer.recv(4096))
        messages = [json.loads(line) for line in received.splitlines()]
        assert messages == [{'id': 1, 'ok': True, 'body': {'synthetic_result': True}}, {'op': 'stop'}]


def test_private_scoring_waits_leave_official_container_source_and_limits_unchanged():
    from proworksim import software_benchmark_tcp_transport_v066 as tcp
    from proworksim import software_benchmark_tls_transport_v059 as tls
    private_tcp, private_tls = fixed.tcp_module(), fixed.tls_module()
    assert private_tcp.relay_many.__globals__['select'] is fixed.POLL_SELECT
    assert private_tls.relay_once.__globals__['select'] is fixed.POLL_SELECT
    assert private_tcp.build_container_source() == tcp.build_container_source()
    assert tcp.relay_many.__globals__['select'] is select
    assert tls.relay_once.__globals__['select'] is select


@pytest.mark.parametrize('stopping', [True, False])
def test_real_high_fd_scoring_relay_preserves_stop_and_rejects_premature_done(stopping):
    tcp = fixed.tcp_module()
    stop = threading.Event()
    if stopping:
        stop.set()
    authorizations, connections = [], []
    with high_socket_pair() as (stream, peer):
        peer.sendall(frame(1, tcp.packet(tcp.READY)+tcp.packet(tcp.DONE)))
        result = tcp.relay_many(stream, '93.184.216.34', instance_id='synthetic-scoring',
            resolved_ips=['93.184.216.34'], stop_event=stop,
            limits=tcp.Limits(wall_seconds=1), authorize=authorizations.append,
            connector=lambda *args: connections.append(args))
    assert authorizations == ['synthetic-scoring'] and connections == []
    assert result['ready'] and result['connection_attempts'] == 0
    if stopping:
        assert result['ok'] and result['status'] == 'completed'
    else:
        assert not result['ok'] and 'Premature DONE' in result['error']['message']


def test_scoring_actual_container_and_cleanup_bindings_are_private():
    from proworksim import software_benchmark_poll_scorer_v088 as scoring
    original_scorer = scoring.recovery.original_scorer
    score = scoring.scorer_callable()
    namespace = score.__globals__
    environment = namespace['environment']
    assert namespace['_score'].__globals__ is namespace
    assert namespace['cleanup'].__globals__['environment'] is environment
    assert namespace['Containers'].create.__globals__['environment'] is environment
    transport = environment.tls.EnvironmentContainer.start.__globals__['transport']
    assert transport.relay_many.__globals__['select'] is fixed.POLL_SELECT
    assert transport.build_container_source() == original_scorer.environment.tls.transport.build_container_source()
    assert environment.tls.run_official is scoring.recovery.lifecycle.run_official
    assert original_scorer.Containers.create.__globals__['environment'] is original_scorer.environment
    assert original_scorer.environment.tls.transport.relay_many.__globals__['select'] is select


def test_scoring_child_redirection_retains_original_guard_and_does_not_mutate_base(tmp_path):
    from proworksim import software_benchmark_poll_scorer_v088 as scoring
    from proworksim.software_benchmark_candidates_v054 import write_new
    ref = write_new(tmp_path/'request.json', {'instance_id': 'synthetic'})
    calls = []
    namespace = {'fixed_python': lambda args: ['original-wrapper', *args]}
    exec("def run_request(ref, stop_event=None):\n return fixed_python(['-m', 'proworksim.software_benchmark_scorer_v066', '--request', ref['path']])", namespace)
    base = SimpleNamespace(run_request=namespace['run_request'], fixed_python=namespace['fixed_python'])
    delegate = scoring.recovery.RecoveryGrading(base=base,
        guard=lambda *a, **kw: calls.append((a, kw)), original_reconciliations={})
    wrapped = scoring.bind_grading(delegate)
    assert wrapped.run_request(ref) == ['original-wrapper', '-m',
        'proworksim.software_benchmark_poll_scorer_v088', '--request', ref['path']]
    assert calls == [(('v068.run',), {'instance_id': 'synthetic'})]
    assert namespace['fixed_python'](['unmodified']) == ['original-wrapper', 'unmodified']
