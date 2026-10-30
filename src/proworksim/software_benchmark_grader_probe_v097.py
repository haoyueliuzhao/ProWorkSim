"""Kernel boundary observation for legacy task interpreters; no task imports."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .software_benchmark_candidates_v054 import reference, write_new

VERSION = "v097-legacy-python-private-grader-probe-r1"
PREFIX = "PWS_GRADER_BOUNDARY_V097:"
NAMESPACES = ("net", "mnt", "pid", "ipc")
MAX_OUTPUT = 65536

# Python 2.7 syntax is intentional. -S suppresses unrelated site startup code;
# only stdlib and the current process's /proc records are needed for this probe.
PROBE_SOURCE = r'''
import os, json
affinity = getattr(os, 'sched_getaffinity', None)
if affinity is not None:
    cpus = sorted(affinity(0))
    mechanism = 'sched_getaffinity'
else:
    with open('/proc/self/status', 'r') as stream:
        rows = [line.split(':', 1)[1].strip() for line in stream if line.startswith('Cpus_allowed_list:')]
    if len(rows) != 1 or not rows[0]:
        raise ValueError('Missing unique kernel CPU affinity record')
    cpus = []
    for item in rows[0].split(','):
        bounds = item.split('-')
        if len(bounds) == 1:
            cpus.append(int(bounds[0]))
        elif len(bounds) == 2 and int(bounds[0]) <= int(bounds[1]):
            cpus.extend(range(int(bounds[0]), int(bounds[1]) + 1))
        else:
            raise ValueError('Malformed kernel CPU affinity record')
    cpus = sorted(set(cpus))
    mechanism = 'proc_self_status'
value = {'namespaces': dict((k, os.stat('/proc/self/ns/' + k).st_ino) for k in ('net', 'mnt', 'pid', 'ipc')), 'cpus': cpus, 'affinity_source': mechanism}
print('PWS_GRADER_BOUNDARY_V097:' + json.dumps(value, sort_keys=True))
'''


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate boundary JSON field")
        result[key] = value
    return result


def parse_probe(stdout: bytes):
    if len(stdout) > MAX_OUTPUT:
        raise ValueError("Boundary output exceeds its evidence limit")
    lines = stdout.decode("utf-8", "strict").splitlines()
    frames = [line[len(PREFIX):] for line in lines if line.startswith(PREFIX)]
    if len(frames) != 1:
        raise ValueError("Expected exactly one framed kernel boundary observation")
    value = json.loads(frames[0], object_pairs_hook=_unique_object)
    if (set(value) != {"namespaces", "cpus", "affinity_source"}
            or value["affinity_source"] not in {"sched_getaffinity", "proc_self_status"}
            or not isinstance(value["namespaces"], dict)
            or set(value["namespaces"]) != set(NAMESPACES)
            or any(type(v) is not int or v <= 0 for v in value["namespaces"].values())
            or not isinstance(value["cpus"], list) or not value["cpus"]
            or any(type(cpu) is not int or cpu < 0 for cpu in value["cpus"])
            or value["cpus"] != sorted(set(value["cpus"]))):
        raise ValueError("Kernel boundary observation has invalid types or values")
    return value


def observe(container, public_python: str, evidence_file: Path):
    """Keep the exact small raw reply even if parsing/exit status is invalid."""
    argv = [public_python, "-S", "-c", PROBE_SOURCE]
    evidence = {"version": VERSION, "argv": argv, "status": "technical_unknown"}
    try:
        result = container.exec_run(argv, demux=True)
        if not isinstance(result.output, tuple) or len(result.output) != 2:
            raise ValueError("Docker exec did not return separate stdout/stderr")
        stdout, stderr = (item or b"" for item in result.output)
        evidence["exit_code"] = result.exit_code
        for name, body in (("stdout", stdout), ("stderr", stderr)):
            evidence[name] = {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "utf8_prefix": body[:MAX_OUTPUT].decode("utf-8", "replace"),
                "truncated": len(body) > MAX_OUTPUT}
        if result.exit_code != 0 or len(stderr) > MAX_OUTPUT:
            raise ValueError("Boundary interpreter failed or exceeded its evidence limit")
        value = parse_probe(stdout)
        evidence.update(status="observed", observation=value)
    except Exception as error:
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        write_new(evidence_file, evidence)
        raise
    write_new(evidence_file, evidence)
    return value, reference(evidence_file)
