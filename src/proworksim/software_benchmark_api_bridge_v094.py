"""Explicitly scoped API-only model bridge for independent recovery identities.

Wire framing and response/accounting dispatch remain the frozen implementation.
Only authority injection and initialization error reporting change. No legacy
dispatch module is imported inside the running bridge.
"""
from __future__ import annotations

from functools import partial
import time

from . import software_benchmark_host_usage_v066 as original_host
from . import software_benchmark_model_fifo_v064 as wire
from .software_benchmark_exact_transport_v054 import LoopbackHTTP

VERSION = 'v094-explicit-scoped-API-model-bridge-r1'


def serve_model_channel(channel, *, endpoint, key_file, deadline, stop_event, slot_id,
                        scope_guard, on_ready=None, transport=None):
    """Serve a bound API broker; every initialization failure returns evidence."""
    result = {'version': wire.VERSION, 'bridge_revision': VERSION,
              'ready': False, 'requests': 0, 'failed_requests': 0,
              'count_requests': 0, 'generation_requests': 0, 'predispatch_admission_replies': 0,
              'model_key_sent_to_container': False, 'host_listener': False, 'automatic_retries': 0,
              'initialization_stage': 'scope_authorization'}
    try:
        if not callable(scope_guard):
            raise PermissionError('An explicit new-owner scope guard is required')
        scope_guard('v066.model.bridge', slot_id=slot_id)
        result['initialization_stage'] = 'broker_identity'
        if (transport is None or key_file is not None or transport.port != wire.DEEPSEEK_PORT
                or transport.timeout_seconds != 1800
                or LoopbackHTTP(endpoint).port != wire.DEEPSEEK_PORT):
            raise ValueError('This bridge requires the explicitly bound key-free DeepSeek broker')
        transport.validate_identity(slot_id)
        result['initialization_stage'] = 'ready_frame'
        ready = wire.decode_frame(channel.readline(deadline=min(deadline, time.monotonic()+20)))
        if ready != {'type': 'model_bridge_ready', 'version': wire.VERSION}:
            raise ValueError('Controller model FIFO bridge did not initialize')
        result.update(ready=True, initialization_stage='serving')
        if on_ready is not None:
            on_ready()
        while not stop_event.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError('Model bridge exceeded episode hard deadline')
            try:
                raw = channel.readline(deadline=min(deadline, time.monotonic()+1))
            except TimeoutError:
                continue
            except ConnectionResetError as error:
                stdout = getattr(channel, 'buffer', None)
                frames = getattr(getattr(channel, 'decoder', None), 'buffer', None)
                if (not isinstance(stdout, (bytes, bytearray)) or stdout
                        or not isinstance(frames, (bytes, bytearray)) or frames):
                    raise
                result.update(status='channel_closed', requires_controller_exit_classification=True,
                    idle_exec_reset={'type': type(error).__name__, 'message': str(error),
                                     'buffered_stdout_bytes': 0, 'buffered_frame_bytes': 0})
                return result
            if not raw:
                result.update(status='channel_closed', requires_controller_exit_classification=True)
                return result
            result['requests'] += 1
            if result['requests'] > wire.MAX_REQUESTS:
                raise ValueError('Model bridge request bound exceeded')
            request = wire.decode_frame(raw)
            count_only = request.get('path') in {'/tokenize', '/tokenize-prefix'}
            if count_only:
                result['count_requests'] += 1
                if result['count_requests'] > wire.MAX_COUNT_REQUESTS:
                    raise ValueError('Count-only model RPC limit exceeded')
            elif result['generation_requests'] >= wire.MAX_GENERATION_REQUESTS:
                raise ValueError('Actual model attempt RPC limit exceeded')
            response = wire.model_response(request, transport, result['requests'])
            unsent = response.get('provider_failure', {}).get('before_dispatch_proven') is True
            result['predispatch_admission_replies'] += not count_only and unsent
            result['generation_requests'] += not count_only and not unsent
            result['failed_requests'] += response['ok'] is False
            channel.write(wire.encoded_frame(response))
        channel.write(wire.encoded_frame({'op': 'stop'}))
        result['status'] = 'stopped_after_controller'
    except Exception as error:
        result.update(status='technical_unknown', error={'type': type(error).__name__, 'message': str(error)})
    return result


def bind_episode(delegate, *, scope_guard):
    """Bind the actual thread call site after the private IO/failure wrappers."""
    from . import software_benchmark_episode_v066 as original_episode

    namespace = delegate.run_episode.__globals__
    if (namespace is vars(original_episode) or delegate._run.__globals__ is not namespace
            or namespace.get('_run') is not delegate._run
            or namespace.get('serve_model_channel') is not original_host.serve_model_channel
            or not callable(scope_guard)):
        raise ValueError('Expected a fresh actual episode using the original host-usage bridge')
    bound = partial(serve_model_channel, scope_guard=scope_guard)
    namespace['serve_model_channel'] = bound
    delegate.__dict__['serve_model_channel'] = bound
    delegate.__dict__['api_bridge_revision'] = VERSION
    if delegate._run.__globals__['serve_model_channel'] is not bound:
        raise RuntimeError('Actual model-loop thread did not retain the new scoped bridge')
    return delegate
