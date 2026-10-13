"""Fixed M12 v050 support, pretraining gate and one original I direction."""
from __future__ import annotations

import ast
import copy
import inspect
import math
from pathlib import Path

from . import software_allocation_v049 as original
from .software_learning_v050 import MEMBERS, SLOT_IDS, VERSION as LEARNING_VERSION
from .software_member_views_v050 import bind_private_function, member_view
from .storage import digest, json_bytes

VERSION = "software-finite-direction-v0.50"
MAPPER, CATEGORIES, ROOTS = original.MAPPER, original.CATEGORIES, original.ROOTS
LOWER, UPPER, TV_LIMIT = original.LOWER, original.UPPER, original.TV_LIMIT
_sealed, _check_seal = original._sealed, original._check_seal
feasible_radius = original.feasible_radius


def _inventory(entries, declaration, admission, design):
    scheduled = design["training_slots"]
    if (len(scheduled) != 24 or [row["slot_id"] for row in scheduled] != list(SLOT_IDS)
            or [row["root"] for row in scheduled] != ["LA"] * 12 + ["LB"] * 12
            or [row["sampling_seed"] for row in scheduled] != list(range(202610130501, 202610130525))
            or any(row["members"] != list(MEMBERS) or row["purpose"] != "policy_training" for row in scheduled)
            or [row["slot_id"] for row in entries] != list(SLOT_IDS)
            or [row["slot_id"] for row in declaration["slots"]] != list(SLOT_IDS)
            or [row["slot_id"] for row in admission["slots"]] != list(SLOT_IDS)
            or admission["slot_count"] != 24 or admission["window_id"] != declaration["window_id"]
            or admission["actor_identity"] != declaration["actor_identity"]
            or digest(json_bytes(design)) != declaration["gamma_identity"].get("design_sha256")
            or declaration["min_class_count"] != 2 or design["mapper"]["category_order"] != list(CATEGORIES)
            or design["direction"]["weight_lower"] != LOWER or design["direction"]["weight_upper"] != UPPER
            or design["direction"]["total_variation_from_b_max"] != TV_LIMIT):
        raise ValueError("Support must preserve the frozen new 24-slot/M12/48 design and original admission")
    for slot in declaration["slots"]:
        if slot["active_members"] != list(MEMBERS) or slot["mapping_spec_id"] != MAPPER:
            raise ValueError("Only the declared O1 members and unchanged Mapper enter support")
    for start in (0, 12):
        group = declaration["slots"][start:start + 12]
        if len({row["xi_id"] for row in group}) != 1:
            raise ValueError("Every root retains twelve same-situation repeats")
    if declaration["slots"][0]["xi_id"] == declaration["slots"][12]["xi_id"]:
        raise ValueError("Independent roots cannot be merged for support")
    actual = [entry["rollout"]["rollout_id"] for entry in entries if entry.get("rollout") is not None]
    if len(set(actual)) != len(actual):
        raise ValueError("One joint episode cannot fill multiple raw support slots")
    keys = [(row["slot_id"], row["member_id"], row["call_id"]) for row in admission["decisions"]]
    if len(keys) != len(set(keys)):
        raise ValueError("Original admitted decisions cannot be duplicated")
    if any(row["slot_id"] not in SLOT_IDS or row["member_id"] not in MEMBERS
           or type(row["actor_denominator"]) is not int or row["actor_denominator"] <= 0
           or row["actor_denominator"] % 48 != 0
           or type(row["critic_denominator"]) is not int or row["critic_denominator"] <= 0
           or row["critic_denominator"] % 48 != 0 for row in admission["decisions"]):
        raise ValueError("Admitted rows must retain the fixed 48T/48K measure")
    byslot = {entry["slot_id"]: entry for entry in entries}
    grouped = {}
    for row in admission["decisions"]:
        grouped.setdefault((row["slot_id"], row["member_id"]), []).append(row)
    for (sid, member), rows in grouped.items():
        view = member_view(byslot[sid]["rollout"], member)
        required = [row for row in view["decisions"] if row["actor_required"]]
        if ([row["call_id"] for row in rows] != [row["call_id"] for row in required]
                or any(row["actor_denominator"] != 48 * view["own_action_tokens"]
                       or row["critic_denominator"] != 48 * len(required) for row in rows)):
            raise ValueError("An admitted original member trajectory retains all ordered decisions and exact 48T/48K")
    return {row["slot_id"]: row for row in scheduled}


def _support_adapter():
    source = inspect.getsource(original.build_support_report)
    tree = ast.parse(source)
    changed = {"import": 0, "slot_count": 0, "denominator": 0, "measure_text": 0, "docstring": 0}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "software_training_v049" and node.level == 1:
            node.module = "software_training_v050"
            changed["import"] += 1
        elif isinstance(node, ast.Constant):
            if type(node.value) is int and node.value == 8:
                node.value = 24
                changed["slot_count"] += 1
            elif type(node.value) is int and node.value == 16:
                node.value = 48
                changed["denominator"] += 1
            elif isinstance(node.value, str) and "1/(8*2)" in node.value:
                node.value = node.value.replace("1/(8*2)", "1/(24*2)").replace("M=4 and v=n/4", "M=12 and v=n/12")
                changed["measure_text"] += 1
            elif isinstance(node.value, str) and node.value.startswith("Keep original M=4 blocks"):
                node.value = node.value.replace("M=4", "M=12")
                changed["docstring"] += 1
    if changed != dict.fromkeys(changed, 1):
        raise ValueError("Adapt exactly the original support inventory/measure metadata and source import")
    namespace = {**vars(original), **globals()}
    exec(compile(tree, "<v050-original-support-M12-global48>", "exec"), namespace)
    return namespace["build_support_report"], {
        "original_source_sha256": digest(source.encode()),
        "original_module_sha256": digest(Path(original.__file__).read_bytes()),
        "explicit_AST_changes": changed,
        "adapted_AST_sha256": digest(ast.dump(tree, include_attributes=False).encode()),
        "support_kernel_changed": False, "mapper_changed": False,
        "base_member_mass": "1/48", "per_root_repeats": 12,
        "old_module_globals_modified": False,
    }


build_support_report, _adaptation = _support_adapter()
_validate_gradients = bind_private_function(original._validate_gradients, {"LEARNING_VERSION": LEARNING_VERSION})


def _direction_adapter():
    source = inspect.getsource(original.select_direction)
    tree = ast.parse(source)
    targets = [node for node in ast.walk(tree) if isinstance(node, ast.Constant)
               and isinstance(node.value, str) and "1/(8*2*member_output_tokens)" in node.value]
    if len(targets) != 1:
        raise ValueError("Adapt exactly the original direction gradient-unit description")
    targets[0].value = targets[0].value.replace("1/(8*2*member_output_tokens)", "1/(24*2*member_output_tokens)")
    namespace = {**vars(original), **globals()}
    exec(compile(tree, "<v050-original-one-direction-global48-description>", "exec"), namespace)
    return namespace["select_direction"]


select_direction = _direction_adapter()


def pretraining_support_gate(support):
    """A fixed supply gate before B; no gradients or development values enter."""
    _check_seal(support)
    if (support.get("version") != VERSION or support.get("original_slot_count") != 24
            or support.get("global_member_denominator_factor") != 48
            or support.get("root_order") != list(ROOTS) or support.get("member_order") != list(MEMBERS)
            or support.get("learner_report_sha256") is not None):
        raise ValueError("The v050 pretraining gate consumes only the sealed pre-B CPU support")
    if any(not row["rollout_available"] or row["status"] != "closed"
           for row in support["original_slots"]):
        raise ValueError("Complete the fixed 24 collections or preserve an integrity stop; do not call missing supply no support")
    checked, qualified = [], []
    for root in ROOTS:
        for member in MEMBERS:
            block = support["roots"][root]["blocks"][member]
            if block["M"] != 12:
                raise ValueError("Twelve fixed original repeats define each support block")
            possible = []
            if len(block["b"]) >= 2:
                for category in CATEGORIES:
                    if category in block["b"]:
                        rho, _ = feasible_radius(block["b"], category)
                        if math.isfinite(rho) and rho > 0:
                            possible.append({"category": category, "rho": rho})
            row = {"root": root, "member_id": member,
                "candidate_counts_before_support": copy.deepcopy(block["candidate_counts_before_support"]),
                "qualified_counts": copy.deepcopy(block["n_by_class"]),
                "b": copy.deepcopy(block["b"]), "v": block["v"],
                "I_degrees_of_freedom": block["composition_degrees_of_freedom"],
                "two_sided_candidates": possible, "qualified_multiclass_block": bool(possible)}
            checked.append(row)
            if possible:
                qualified.append({"root": root, "member_id": member})
    run = bool(qualified)
    return _sealed({"version": "v050-pretraining-support-gate-v1",
        "support_artifact_sha256": digest(json_bytes(support)),
        "design_sha256": support["design_sha256"], "declaration_sha256": support["declaration_sha256"],
        "run_B50": run, "status": "reliable_multiclass_support_B50_admitted" if run else "fixed_supply_closed_no_reliable_I_support",
        "qualified_blocks_in_frozen_order": qualified, "blocks": checked,
        "development_branches": ["S_star", "B"] if run else [],
        "Q_branches_require_post_B_nonzero_actual_direction": run,
        "new_actor_forwards": 0, "new_backwards": 0, "new_optimizer_steps": 0,
        "development_results_read": False, "additional_samples": 0,
        "scope": "Finite direction study supply gate only. No reliable multiclass support closes this window without B or development; residual base material remains recorded with unit weight and its original 48 measure."})


def adaptation_spec():
    return copy.deepcopy(_adaptation)
