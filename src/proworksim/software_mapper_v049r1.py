"""Read-only v049 Mapper consumer binding for the closed-record identity repair.

The mapping specification and all production-route methods are unchanged. Only
its inherited archive constructor consumes the stricter v049r1 MemberView.
"""
from __future__ import annotations

import copy
from types import FunctionType

from . import software_mapper_v049 as original
from . import software_method_evidence_v035 as archive_module
from .software_member_views_v049r1 import member_view

VERSION = "software-mapper-record-binding-v0.49r1"
MAPPER = original.MAPPER
mapping_spec = original.mapping_spec


def _bound(function, overrides):
    namespace = dict(function.__globals__)
    namespace.update(overrides)
    bound = FunctionType(function.__code__, namespace, function.__name__,
                         function.__defaults__, function.__closure__)
    bound.__kwdefaults__ = copy.deepcopy(function.__kwdefaults__)
    return bound


class Evidence(original.Evidence):
    __init__ = _bound(archive_module._Evidence.__init__, {"member_view": member_view})


# Unchanged category/visibility/source/version logic, original mapping_spec hash.
map_software_method = _bound(original.map_software_method, {"Evidence": Evidence})
