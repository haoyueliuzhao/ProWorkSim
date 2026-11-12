"""Operator pause/resume of new generation admission without cancelling work.

The current owner stays alive while draining. Existing model calls, episodes,
scoring and usage capture finish through their unchanged paths. A separately
sealed plan must declare this interface; it cannot retrofit frozen old owners.
"""
from __future__ import annotations

import copy
import fcntl
import json
import os
from pathlib import Path
import threading
import time

from .software_benchmark_candidates_v054 import checked, reference
from .storage import atomic_write, json_bytes, digest

VERSION = 'v120-generation-admission-drain-r1'
ROOT = Path(__file__).resolve().parents[2]


def declaration(batch_root):
    return {'version': VERSION,
        'control_file': str(Path(batch_root)/'operator-controls/dispatch-admission.json'),
        'default_mode': 'run', 'affects_existing_generation': False, 'affects_scoring': False}


def _binding(plan_ref):
    path = checked(plan_ref)
    plan = json.loads(path.read_bytes())
    batch = Path(plan['root']).resolve()
    if (os.getuid() == 0 or not batch.is_relative_to((ROOT/'runs').resolve())
            or not path.resolve().is_relative_to(batch) or path.stat().st_uid != os.getuid()
            or plan.get('dispatch_admission') != declaration(Path(plan['root']))):
        raise PermissionError('This owned sealed plan does not declare admission drain control')
    return {'batch_root': str(batch), 'plan': copy.deepcopy(plan_ref), 'actor_uid': os.getuid()}, Path(plan['dispatch_admission']['control_file'])


def _parse(raw, binding):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('Duplicate operator-control field')
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=unique)
    expected_keys = {'version', 'batch_root', 'plan', 'actor_uid', 'sequence', 'mode', 'reason',
                     'created_unix', 'no_inflight_cancellation'}
    if (not isinstance(value, dict) or set(value) != expected_keys or value['version'] != VERSION
            or any(value.get(key) != item for key, item in binding.items())
            or type(value['sequence']) is not int or value['sequence'] < 1
            or value['mode'] not in {'run', 'drain'} or value['no_inflight_cancellation'] is not True
            or not isinstance(value['reason'], str) or not 0 < len(value['reason']) <= 500
            or type(value['created_unix']) not in {int, float}):
        raise ValueError('Operator control does not match this exact plan and admission-only policy')
    return value


def write_control(plan_ref, *, mode, reason):
    """Atomic owned-file change only; no signal, model, Docker or service call."""
    binding, path = _binding(plan_ref)
    if mode not in {'run', 'drain'} or not isinstance(reason, str) or not 0 < len(reason) <= 500:
        raise ValueError('Choose run/drain and a nonempty reason up to 500 characters')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink() or not path.parent.resolve().is_relative_to(Path(binding['batch_root'])):
        raise PermissionError('Control path must remain inside its owned batch')
    with (path.parent/'dispatch-admission.lock').open('a+b') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        before = _parse(path.read_bytes(), binding) if path.exists() else None
        value = {**binding, 'version': VERSION, 'sequence': 1 if before is None else before['sequence']+1,
            'mode': mode, 'reason': reason, 'created_unix': time.time(), 'no_inflight_cancellation': True}
        raw = json_bytes(value)
        # Retain each operator instruction separately before switching the
        # current control pointer; neither file is a runtime-source mutation.
        receipt = path.parent/f"dispatch-admission-{value['sequence']:06d}.json"
        with receipt.open('xb') as stream:
            stream.write(raw)
        atomic_write(path, raw)
    return {'control': reference(path), 'instruction': reference(receipt),
            'mode': mode, 'new_dispatch_only': True, 'service_or_API_operations': 0}


class DispatchAdmissionController:
    def __init__(self, plan_ref):
        self.binding, self.path = _binding(plan_ref)
        self._lock = threading.Lock()
        self.sequence, self.fingerprint = 0, None
        self.current = {'mode': 'run', 'sequence': 0, 'reason': 'No operator instruction received',
                        'control_error': None, 'no_inflight_cancellation': True}

    def read(self):
        with self._lock:
            return self._read_locked()

    def _read_locked(self):
        try:
            if not self.path.exists():
                if self.sequence:
                    raise ValueError('A previously observed operator control is missing')
                return copy.deepcopy(self.current)
            if self.path.is_symlink() or self.path.stat().st_uid != os.getuid():
                raise ValueError('Operator control ownership changed')
            raw = self.path.read_bytes()
            value = _parse(raw, self.binding)
            fingerprint = digest(raw)
            if value['sequence'] < self.sequence or (value['sequence'] == self.sequence and fingerprint != self.fingerprint):
                raise ValueError('Operator instruction was rolled back or edited in place')
            self.sequence, self.fingerprint = value['sequence'], fingerprint
            self.current = {**value, 'control_error': None}
        except Exception as error:
            # Do not translate a malformed admission file into a global stop:
            # that would cancel the in-flight work this control protects.
            self.current = {'mode': 'drain', 'sequence': self.sequence,
                'reason': 'Operator control requires review; only new dispatch is paused',
                'control_error': {'type': type(error).__name__, 'message': str(error)},
                'no_inflight_cancellation': True}
        return copy.deepcopy(self.current)

    def limit(self, available):
        if type(available) is not int or available < 0:
            raise ValueError('Underlying admission capacity must remain a nonnegative integer')
        return 0 if self.read()['mode'] == 'drain' else available

    def annotate(self, progress):
        value = self.read()
        no_work = all(progress.get(key, 0) == 0 for key in
                      ('active_generation', 'active_grading', 'pending_scores', 'pending_controls'))
        no_work = no_work and not any(progress.get('async_grading_stages', {}).values())
        state = 'paused_drained' if value['mode'] == 'drain' and no_work else 'draining' if value['mode'] == 'drain' else 'running'
        return {**progress, 'dispatch_admission': {**value, 'state': state,
            'owner_remains_alive': True, 'scoring_allowed': True, 'existing_generation_cancelled': False}}
