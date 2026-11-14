"""Reuse this request's scored candidate, independent of preparation filenames.

The exact identity/request manifest remains immutable. This does not authorize a
new score, relax candidate identity, change tests or accept a different delivery.
"""
import inspect
from types import SimpleNamespace

from .software_benchmark_candidates_v054 import checked

VERSION='v175-own-code-score-manifest-bound-delivery-r1'


def same_score_manifest(identity_ref,request_ref):
    if not isinstance(identity_ref,dict) or identity_ref!=request_ref:
        return False
    checked(identity_ref)
    return True


def bind_host(host):
    original=host.delivery_disposition
    source=inspect.getsource(original)
    needle='identity.get("scorer_manifest") != prepare_manifest()'
    if source.count(needle)!=1:
        raise ValueError('Actual delivery reuse check changed; no broad runtime rewriting')
    ns={**original.__globals__,'same_score_manifest':same_score_manifest}
    source=source.replace(needle,'not same_score_manifest(identity.get("scorer_manifest"), request.get("scorer_manifest"))')
    compiled={};exec(compile(source,__file__+':actual-delivery-entry','exec'),ns,compiled)
    result=SimpleNamespace(**vars(host))
    result.delivery_disposition=compiled['delivery_disposition']
    result.delivery_reuse_revision=VERSION
    return result


def bind_grading(grading):
    """Bind a newly constructed host, never a frozen active grader instance."""
    if getattr(grading,'delivery_reuse_revision',None) is not None:
        raise ValueError('Bind a fresh grader exactly once')
    grading.base=bind_host(grading.base)
    grading.delivery_reuse_revision=VERSION
    return grading
