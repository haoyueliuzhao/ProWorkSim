"""Finite consumer-binding controls; no model/world/acceptance execution."""
import ast
import inspect

from proworksim import member_views
from proworksim import software_mapper_v049 as old_mapper
from proworksim import software_mapper_v049r1 as mapper
from proworksim import software_member_views_v049r1 as reader
from proworksim import software_training_v049 as old_export
from proworksim import software_training_v049r1 as export
from proworksim import team_validity
from proworksim.software_method_evidence_v035 import _Evidence
from proworksim.storage import digest, json_bytes


def test_mapper_rules_and_all_route_methods_remain_the_original_code():
    assert mapper.map_software_method.__code__ is old_mapper.map_software_method.__code__
    assert mapper.Evidence.__init__.__code__ is _Evidence.__init__.__code__
    assert mapper.Evidence.__init__.__globals__["member_view"] is reader.member_view
    assert mapper.Evidence._actual_inputs is old_mapper.Evidence._actual_inputs
    assert mapper.Evidence.delivery_chain is old_mapper.Evidence.delivery_chain
    assert mapper.mapping_spec is old_mapper.mapping_spec
    assert digest(json_bytes(mapper.mapping_spec())) == digest(json_bytes(old_mapper.mapping_spec()))
    assert _Evidence.__init__.__globals__["member_view"] is member_views.member_view


def test_window_binding_and_all_original_module_globals_are_isolated():
    assert export.bind_rollout.__code__ is old_export.bind_rollout.__code__
    assert export.bind_rollout.__globals__["member_view"] is reader.member_view
    assert export.expected_window.__code__ is old_export.expected_window.__code__
    assert export.declare_window.__code__ is old_export.declare_window.__code__
    assert export._support_globals is not old_export._support_globals
    assert old_export.bind_rollout.__globals__["member_view"] is member_views.member_view
    assert team_validity._record_permission_checks.__globals__["member_view"] is member_views.member_view
    assert export.source_training_admission is old_export.source_training_admission
    assert export.reward_record is old_export.reward_record
    assert export.software_work_evidence is old_export.software_work_evidence


def test_export_function_changes_only_the_mapper_module_import_and_bound_consumers():
    old = ast.parse(inspect.getsource(old_export.export_software_episode))
    new = ast.parse(inspect.getsource(export.export_software_episode))
    first = old.body[0].body[0]
    assert isinstance(first, ast.ImportFrom) and first.module == "software_mapper_v049"
    first.module = "software_mapper_v049r1"
    assert ast.dump(old, include_attributes=False) == ast.dump(new, include_attributes=False)
    assert export.export_software_episode.__globals__["member_view"] is reader.member_view
    assert export.export_software_episode.__globals__["assess_record_permission"] is export.assess_record_permission
    assert export.export_software_episode.__globals__["bind_rollout"] is export.bind_rollout


def test_support_binding_changes_one_import_and_keeps_original_direction_and_kernel():
    from proworksim import software_allocation_v049 as old
    from proworksim import software_allocation_v049r1 as revised

    proof = revised.adaptation_spec()
    assert proof["changed_relative_imports"] == 1
    assert proof["all_other_original_AST_nodes_retained"] is True
    assert proof["bounds"] == {"lower": .5, "upper": 2., "TV_limit": .2}
    assert revised.feasible_radius is old.feasible_radius
    assert revised.select_direction is old.select_direction
    assert revised.build_support_report.__globals__["build_support"] is old.build_support
    assert revised.build_support_report.__globals__["_inventory"] is old._inventory
    assert revised.build_support_report.__globals__["_sealed"] is old._sealed
    assert "software_training_v049r1" not in inspect.getsource(old.build_support_report)
