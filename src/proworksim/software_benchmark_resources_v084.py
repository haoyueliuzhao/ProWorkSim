"""Treat incomplete startup status as pending, not a whole-queue parse failure."""
from __future__ import annotations

import json
from pathlib import Path

from . import software_benchmark_resources_v076 as prior
from .software_benchmark_deepseek_runtime_v069 import private_function
from .software_benchmark_expansion_episode_v069 import clone_namespace

VERSION = 'v084-actual-binding-nonatomic-startup-status-tolerant-admission-r1'
MAX_STARTING_PAIRS = 8
CapacityProbe = prior.CapacityProbe


class PendingPairs(list):
    def __init__(self):
        super().__init__()
        self.observation_issues = []


def safe_pending_pairs(active, *, batch_root=prior.original.BATCH_ROOT, materialized=None):
    """Only a fully decoded trusted marker enters the materialized cache.

    The old writer creates its pathname before its bytes are complete. Missing,
    empty or malformed status is therefore unavailable evidence, not evidence
    that another episode or the whole host failed. The owning episode still
    performs its unchanged final initialization and bounded-lifetime checks.
    """
    cache = materialized if materialized is not None else set()
    waiting = PendingPairs()
    for claim in active:
        if claim.get('spec', {}).get('role') != 'actor':
            continue
        key, slot = claim.get('key'), claim.get('spec', {}).get('slot_id')
        match = prior.ACTOR_KEY.fullmatch(key or '')
        if match is None or not isinstance(slot, str):
            raise ValueError('Active actor has no trusted physical identity')
        identity = (key, slot)
        if identity in cache:
            continue
        path = Path(batch_root) / 'episodes' / match[1] / 'controller-ready.json'
        reason = None
        try:
            raw = path.read_bytes()
            ready = json.loads(raw)
        except FileNotFoundError:
            reason = 'not_yet_created'
        except (json.JSONDecodeError, UnicodeDecodeError):
            reason = 'incomplete_or_invalid_JSON_not_admitted'
        except OSError as error:
            reason = 'status_unavailable_' + type(error).__name__
        else:
            if (not isinstance(ready, dict)
                    or ready.get('trusted_SDK_imports_complete') is not True
                    or ready.get('version') not in {'v064-private-native-controller-r1',
                                                  'v064-private-project-controller-r1'}
                    or ready.get('model_calls') != 0):
                reason = 'unqualified_status_not_admitted'
        if reason is not None:
            waiting.append(key)
            waiting.observation_issues.append({'key': key, 'slot_id': slot,
                'path': str(path), 'reason': reason, 'treated_as_materialized': False,
                'global_stop_required': False})
            continue
        cache.add(identity)
    return waiting


_evaluate = private_function(prior.evaluate, VERSION=VERSION,
                            MAX_STARTING_PAIRS=MAX_STARTING_PAIRS)


def evaluate(active, physical, watchdog, *, pending):
    value = _evaluate(active, physical, watchdog, pending=pending)
    value['pending_status_observation_issues'] = getattr(pending, 'observation_issues', [])
    return value


def policy(guard, *, watchdog_guard, capacity_probe=None, authorization_ref=None):
    namespace = clone_namespace(prior, VERSION=VERSION,
        MAX_STARTING_PAIRS=MAX_STARTING_PAIRS, __file__=__file__, __name__=__name__)
    # clone_namespace clones module-local functions after installing overrides.
    # Install callable replacements only after cloning, so they cannot be lost.
    namespace.update(pending_pairs=safe_pending_pairs, evaluate=evaluate)

    def scoped_guard(operation, **identity):
        if operation != 'v076.run':
            raise PermissionError('Unexpected original allocation operation')
        return guard('v084.run', **identity)

    adapted = namespace['policy'](scoped_guard, watchdog_guard=watchdog_guard,
        capacity_probe=capacity_probe, authorization_ref=authorization_ref)
    actual = adapted.admission_snapshot.__globals__
    if actual.get("pending_pairs") is not safe_pending_pairs or actual.get("evaluate") is not evaluate:
        raise RuntimeError("The startup-status reader is absent from the actual admission binding")
    original_write = adapted._write_claim

    def write_claim(path, value):
        if (value.get('spec', {}).get('role') == 'actor'
                and ':QWEN_' not in value['spec'].get('slot_id', '')):
            raise PermissionError('This recovery may create only Qwen actors')
        return original_write(path, value)

    adapted.claim_resource.__globals__['_write_claim'] = write_claim
    adapted._write_claim = write_claim
    return adapted
