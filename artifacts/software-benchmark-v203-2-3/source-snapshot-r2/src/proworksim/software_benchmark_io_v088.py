"""High-descriptor readiness for private host transports, without a wire change.

Only fresh per-coordinator episode/provider dictionaries are adapted. The
frozen source modules and already-running coordinators are never modified.
"""
from __future__ import annotations

import errno
import math
import operator
import os
import select
import time
from types import ModuleType, SimpleNamespace

from . import software_benchmark_docker_actor_v066 as original_provider
from . import software_benchmark_episode_v066 as original_episode
from . import software_benchmark_model_fifo_v064 as original_fifo
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v088-private-high-FD-poll-transport-r1'


def _fd(item):
    value = operator.index(item if isinstance(item, int) else item.fileno())
    if value < 0:
        raise ValueError('file descriptor cannot be a negative integer')
    return value


def poll_select(readers, writers, exceptional, timeout=None):
    """select-shaped readiness without FD_SETSIZE; preserve input order/objects.

    poll's HUP/ERR are readable/writable conditions, so the original recv/read
    code still classifies EOF, resets and partial frames. Invalid FDs fail
    closed instead of becoming a readiness success. Nothing here reads, writes,
    closes or renumbers any descriptor, nor changes its blocking mode.
    """
    groups = [list(readers), list(writers), list(exceptional)]
    descriptors = [[_fd(item) for item in group] for group in groups]
    if timeout is not None:
        timeout = float(timeout)
        if math.isnan(timeout) or timeout < 0:
            raise ValueError('timeout must be nonnegative and finite, or None')
        if not math.isfinite(timeout):
            raise OverflowError('timeout is too large')
    deadline = None if timeout is None else time.monotonic()+timeout
    masks = {}
    for values, event in zip(descriptors, (select.POLLIN, select.POLLOUT, select.POLLPRI), strict=True):
        for value in values:
            masks[value] = masks.get(value, 0) | event
    waiter = select.poll()
    for value, events in masks.items():
        waiter.register(value, events)
    conditions = (select.POLLIN | select.POLLHUP | select.POLLERR,
                  select.POLLOUT | select.POLLHUP | select.POLLERR, select.POLLPRI)
    while True:
        remaining = None if deadline is None else max(0.0, deadline-time.monotonic())
        # Round up, then recheck the absolute deadline if the OS reports no
        # event. Do not turn sub-millisecond positive deadlines into a busy spin.
        milliseconds = None if remaining is None else min(2_147_483_647, math.ceil(remaining*1000))
        try:
            ready = waiter.poll(milliseconds)
        except InterruptedError:
            if deadline is not None and time.monotonic() >= deadline:
                return [], [], []
            continue
        observed = dict(ready)
        if any(events & select.POLLNVAL for events in observed.values()):
            raise OSError(errno.EBADF, os.strerror(errno.EBADF))
        selected = tuple([item for item, descriptor in zip(group, values, strict=True)
                          if observed.get(descriptor, 0) & condition]
                         for group, values, condition in zip(groups, descriptors, conditions, strict=True))
        if any(selected) or deadline is not None and time.monotonic() >= deadline:
            return selected
        # poll reports terminal HUP/ERR even when only POLLPRI was requested.
        # Those are not select exceptional readiness. Remove the terminal
        # observation for this wait and keep the original deadline; otherwise
        # repeated HUP would either return early or create a busy loop.
        for descriptor, events in observed.items():
            if (masks.get(descriptor) == select.POLLPRI
                    and events & (select.POLLHUP | select.POLLERR)):
                waiter.unregister(descriptor)
                del masks[descriptor]


POLL_SELECT = SimpleNamespace(select=poll_select)


class DockerStdioChannel(original_provider.DockerStdioChannel):
    # Framing, bounds, monotonic deadlines, EOF/reset handling, writes and close
    # methods remain the original implementation; only readiness changes.
    readline = private_function(original_provider.DockerStdioChannel.readline, select=POLL_SELECT)


def fifo_module():
    """Private FIFO adapter for host callers/tests; no container bundle edit."""
    namespace = clone_namespace(original_fifo, select=POLL_SELECT)

    class LineReader(original_fifo.LineReader):
        read = private_function(original_fifo.LineReader.read, select=POLL_SELECT)

    class FifoModelTransport(original_fifo.FifoModelTransport):
        __init__ = private_function(original_fifo.FifoModelTransport.__init__, LineReader=LineReader)
        post = private_function(original_fifo.FifoModelTransport.post,
                                write_frame=namespace['write_frame'])

    namespace.update(LineReader=LineReader, FifoModelTransport=FifoModelTransport)
    value = ModuleType(__name__+'.private_fifo')
    value.__dict__.update(namespace)
    return value


def bind_episode(delegate):
    """Adapt both actual host channel creation sites in a fresh private episode.

    Call after the parent/resource provider factory and before dispatch. The
    provider attach() and episode's direct model-channel construction must both
    use the new class; replacing just the public module attribute is inadequate.
    """
    namespace = delegate.run_episode.__globals__
    if namespace is vars(original_episode):
        raise PermissionError('Never mutate the frozen original episode namespace')
    pair = namespace['OwnedActorPair']
    provider_namespace = pair.attach.__globals__
    if pair is original_provider.OwnedActorPair or provider_namespace is vars(original_provider):
        raise PermissionError('Require a privately constructed provider class')
    if namespace['_run'].__globals__ is not namespace:
        raise ValueError('The actual episode execution function has another namespace')
    for value in (namespace, provider_namespace):
        if value.get('DockerStdioChannel') not in (original_provider.DockerStdioChannel, DockerStdioChannel):
            raise ValueError('Unexpected channel implementation at the actual call site')
    namespace['DockerStdioChannel'] = DockerStdioChannel
    provider_namespace['DockerStdioChannel'] = DockerStdioChannel
    delegate.__dict__['DockerStdioChannel'] = DockerStdioChannel
    return delegate


def tcp_module():
    """Optional private host scoring relay; frozen container source unchanged."""
    from . import software_benchmark_tcp_transport_v066 as original
    value = ModuleType(__name__+'.private_tcp')
    value.__dict__.update(clone_namespace(original, select=POLL_SELECT))
    return value


def tls_module():
    """Optional private old single-session scoring relay, with the same limits."""
    from . import software_benchmark_tls_transport_v059 as original
    value = ModuleType(__name__+'.private_tls')
    value.__dict__.update(clone_namespace(original, select=POLL_SELECT))
    return value
