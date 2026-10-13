"""Unchanged two-route Mapper using only the strict v050 record reader."""
from . import software_mapper_v049 as original
from .software_method_evidence_v035 import _Evidence
from .software_member_views_v050 import bind_private_function, member_view

MAPPER = original.MAPPER
mapping_spec = original.mapping_spec


class Evidence(original.Evidence):
    __init__ = bind_private_function(_Evidence.__init__, {"member_view": member_view})


map_software_method = bind_private_function(original.map_software_method, {"Evidence": Evidence})
