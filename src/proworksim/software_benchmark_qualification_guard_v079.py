"""Permit independent API work only from unchanged, terminal grading evidence."""
from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path

from .software_benchmark_candidates_v054 import checked


@lru_cache(maxsize=1024)
def qualification_passed(task, encoded_ref, fingerprint):
    ref = json.loads(encoded_ref)
    value = json.loads(checked(ref).read_bytes())
    if value.get('instance_id') != task or value.get('passed') is not True:
        raise ValueError('Original environment qualification is not a trusted pass')
    return True


def require_unchanged_terminal(expected, snapshot):
    actual = snapshot.get('qualifications')
    if not isinstance(actual, dict) or not expected:
        raise ValueError('No complete terminal qualification snapshot')
    for task, entry in expected.items():
        if actual.get(task) != entry or entry.get('status') not in {'qualified', 'not_qualified'}:
            raise ValueError('Qwen qualification identity changed or remains unfinished')
        if entry['status'] == 'qualified':
            ref = entry.get('qualification')
            if not isinstance(ref, dict) or not isinstance(ref.get('path'), str):
                raise ValueError('Qualified environment has no exact evidence reference')
            stat = Path(ref['path']).stat()
            qualification_passed(task, json.dumps(ref, sort_keys=True),
                (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns))
        elif not isinstance(entry.get('reason'), str) or not entry['reason']:
            raise ValueError('An inadmissible environment lacks its original reason')
    return {'terminal_qualifications': len(expected), 'Qwen_failure_is_not_API_failure': True,
            'API_source_money_resource_and_cleanup_guards_unchanged': True}
