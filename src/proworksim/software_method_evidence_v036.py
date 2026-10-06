"""Read-only v036 production-unit relations over real, separately bound inputs.

The v035 archive reader remains the authority for immutable World versions,
commit receipts, native selected inputs and original member targets. This module
changes only the finite route representation. It never runs an actor or grader.
"""
from __future__ import annotations

import ast
import builtins
import copy
from pathlib import Path
import symtable

from .software_mapper_v036 import mapping_spec
from .software_method_evidence_v035 import (
    _Evidence as _ArchiveEvidence,
    _contract_definition_fingerprints,
    _file,
    _ref,
    _sha,
    _world_ref,
)
from .storage import digest, read_json
from .team_rollout import optimizer_scope_allows_update, validate_window

VERSION = "software-method-evidence-v0.36"
_DYNAMIC_LOOKUPS = {"eval", "exec", "globals", "locals", "getattr", "setattr", "__import__"}


def _normalized_node(node):
    value = copy.deepcopy(node)
    for part in ast.walk(value):
        if isinstance(part, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if (part.body and isinstance(part.body[0], ast.Expr)
                    and isinstance(part.body[0].value, ast.Constant)
                    and isinstance(part.body[0].value.value, str)):
                part.body.pop(0)
    return ast.dump(value, include_attributes=False)


def _module_structure(text):
    """Static names only; duplicate/dynamic bindings are deliberately unknown."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, TypeError, ValueError, RecursionError):
        return None
    bindings, definitions, ambiguous = {}, {}, set()
    for node in tree.body:
        entries = {}
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            entries[node.name] = {"kind": "definition", "sha256": digest(_normalized_node(node).encode())}
            definitions[node.name] = node
        elif isinstance(node, ast.Import):
            entries = {alias.asname or alias.name.split(".")[0]:
                       {"kind": "import", "module": alias.name, "name": None}
                       for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            entries = {alias.asname or alias.name:
                       {"kind": "import", "module": node.module, "name": alias.name, "level": node.level}
                       for alias in node.names}
            if "*" in entries:
                ambiguous.add("*")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if all(isinstance(target, ast.Name) for target in targets):
                try:
                    ast.literal_eval(node.value)
                except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
                    ambiguous.update(target.id for target in targets)
                else:
                    entries = {target.id: {"kind": "literal", "sha256": digest(_normalized_node(node).encode())}
                               for target in targets}
            else:
                ambiguous.update(part.id for part in ast.walk(node)
                                 if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store))
        elif not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                  and isinstance(node.value.value, str)):
            ambiguous.update(part.id for part in ast.walk(node)
                             if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store))
        for name, value in entries.items():
            if name in bindings:
                ambiguous.add(name)
            bindings[name] = value
    return {"tree": tree, "bindings": bindings, "definitions": definitions, "ambiguous": ambiguous}


def _conflict_markers(text):
    return [i for i, line in enumerate(text.splitlines(), 1)
            if line.startswith(("<<<<<<<", "=======", ">>>>>>>"))]


def _presentation_ref(presentation):
    keys = ("member_id", "call_id", "input_sequence", "message_index", "message_sha256",
            "selected_request_sha256", "action_sequence", "action", "tool_call_id")
    return {key: copy.deepcopy(presentation[key]) for key in keys if key in presentation}


def _global_names(node):
    # Python's lexical symbol tables distinguish function imports, comprehensions
    # and nested scopes from module globals. An added redundant module import
    # cannot change a same-function local import's binding.
    try:
        table = symtable.symtable(ast.unparse(ast.Module(body=[node], type_ignores=[])), "<public-unit>", "exec")
    except (SyntaxError, ValueError, TypeError, RecursionError):
        return {"__unresolved_lexical_scope__"}
    names, pending = set(), [table]
    while pending:
        current = pending.pop()
        names.update(symbol.get_name() for symbol in current.get_symbols()
                     if symbol.is_global() and symbol.is_referenced())
        pending.extend(current.get_children())
    return names


def _local_imports(node):
    output = []
    for part in ast.walk(node):
        if isinstance(part, ast.Import):
            output.extend((alias.asname or alias.name.split(".")[0],
                           {"kind": "import", "module": alias.name, "name": None}) for alias in part.names)
        elif isinstance(part, ast.ImportFrom):
            output.extend((alias.asname or alias.name,
                           {"kind": "import", "module": part.module, "name": alias.name, "level": part.level})
                          for alias in part.names)
    return output


def _production_import_targets(binding, local_name, node, symbols):
    module_path = (binding.get("module") or "").replace(".", "/") + ".py"
    if binding.get("kind") != "import" or module_path not in symbols:
        return None, set()
    targets = ({binding["name"]} if binding.get("name") else
               {part.attr for part in ast.walk(node) if isinstance(part, ast.Attribute)
                and isinstance(part.value, ast.Name) and part.value.id == local_name})
    return module_path, targets


def _static_closure_issues(files, path, symbol, symbols):
    """Follow finite local helper/import bindings, including transitive helpers."""
    pending, visited, issues, structures = [(path, symbol)], set(), [], {}
    while pending:
        current_path, current_symbol = pending.pop()
        if (current_path, current_symbol) in visited:
            continue
        visited.add((current_path, current_symbol))
        if current_path not in structures:
            structures[current_path] = _module_structure(files[current_path])
        structure = structures[current_path]
        if not structure or current_symbol not in structure["definitions"]:
            issues.append("unresolved_transitive_definition:" + current_path + ":" + current_symbol)
            continue
        node = structure["definitions"][current_symbol]
        if "*" in structure["ambiguous"]:
            issues.append("transitive_star_import:" + current_path)
        for name in sorted(_global_names(node)):
            if name in _DYNAMIC_LOOKUPS or name in structure["ambiguous"]:
                issues.append("dynamic_or_ambiguous_transitive_binding:" + current_path + ":" + name)
                continue
            binding = structure["bindings"].get(name)
            if binding is None:
                if not hasattr(builtins, name):
                    issues.append("unbound_transitive_name:" + current_path + ":" + name)
                continue
            if binding["kind"] == "definition":
                pending.append((current_path, name))
            dependency_path, targets = _production_import_targets(binding, name, node, symbols)
            if dependency_path:
                if not targets:
                    issues.append("unresolved_transitive_module_use:" + dependency_path)
                for target in sorted(targets):
                    if target not in symbols[dependency_path]:
                        issues.append("undeclared_transitive_production_unit:" + dependency_path + ":" + target)
                    else:
                        pending.append((dependency_path, target))
        for name, binding in _local_imports(node):
            dependency_path, targets = _production_import_targets(binding, name, node, symbols)
            if dependency_path:
                if not targets:
                    issues.append("unresolved_local_production_module_use:" + dependency_path)
                for target in sorted(targets):
                    if target not in symbols[dependency_path]:
                        issues.append("undeclared_local_production_unit:" + dependency_path + ":" + target)
                    else:
                        pending.append((dependency_path, target))
    return sorted(set(issues))


def _unit_dependencies(path, symbol, source, final, symbols, ancestry):
    """Check static binding closure, not semantic equivalence of a call graph."""
    incoming = _module_structure(source["files"][path])
    delivered = _module_structure(final["files"][path])
    result = {"explained": False, "bindings": [], "cross_production_units": [], "issues": [],
              "scope": "Syntactic binding and version-change evidence; not dependency semantic equivalence or causal necessity."}
    if not incoming or not delivered or symbol not in incoming["definitions"]:
        result["issues"].append("unrecognized_public_definition")
        return result
    result["issues"].extend("incoming:" + item for item in _static_closure_issues(source["files"], path, symbol, symbols))
    result["issues"].extend("final:" + item for item in _static_closure_issues(final["files"], path, symbol, symbols))
    if "*" in incoming["ambiguous"] or "*" in delivered["ambiguous"]:
        result["issues"].append("star_import_binding_unknown")
    pending = [(name, symbol) for name in sorted(_global_names(incoming["definitions"][symbol]))]
    visited, imports = set(), []
    local_import_units = {symbol}
    while pending:
        name, referring_symbol = pending.pop()
        if name in visited:
            continue
        visited.add(name)
        node = incoming["definitions"][referring_symbol]
        before, after = incoming["bindings"].get(name), delivered["bindings"].get(name)
        if name in incoming["ambiguous"] or name in delivered["ambiguous"]:
            result["issues"].append("ambiguous_module_binding:" + name)
            continue
        if before is None and after is None and hasattr(builtins, name):
            continue
        if before is None or after is None or before != after:
            result["issues"].append("missing_or_changed_module_binding:" + name)
            continue
        result["bindings"].append({"name": name, "incoming": before, "final": after})
        if before["kind"] != "import":
            if before["kind"] == "definition":
                pending.extend((dependency, name) for dependency in sorted(_global_names(incoming["definitions"][name])))
                local_import_units.add(name)
            continue
        imports.append((name, before, node))
    for unit in sorted(local_import_units):
        node = incoming["definitions"][unit]
        current = delivered["definitions"].get(unit)
        local_incoming = _local_imports(node)
        local_final = _local_imports(current) if current is not None else None
        if local_incoming != local_final:
            result["issues"].append("changed_local_import_binding:" + unit)
        else:
            for name, binding in local_incoming:
                result["bindings"].append({"name": name, "lexical_unit": unit,
                                           "incoming": binding, "final": binding})
                imports.append((name, binding, node))
    for name, before, node in imports:
        module_path, targets = _production_import_targets(before, name, node, symbols)
        if module_path is None:
            continue
        if not targets:
            result["issues"].append("unresolved_production_module_use:" + module_path)
        source_defs = _contract_definition_fingerprints(source["files"][module_path], symbols[module_path])
        final_defs = _contract_definition_fingerprints(final["files"][module_path], symbols[module_path])
        for target in sorted(targets):
            if not source_defs or not final_defs or target not in source_defs or target not in final_defs:
                result["issues"].append("unresolved_production_symbol:" + module_path + ":" + target)
                continue
            changed = source_defs[target] != final_defs[target]
            transitions = [event["world_sequence"] for event in ancestry if event.get("path") == module_path
                           or event["kind"] == "integrate"]
            if changed and not transitions:
                result["issues"].append("unexplained_production_dependency_change:" + module_path + ":" + target)
            result["cross_production_units"].append({"path": module_path, "symbol": target,
                "incoming_sha256": source_defs[target], "final_sha256": final_defs[target],
                "structurally_changed": changed, "verified_transition_sequences": transitions,
                "semantic_equivalence_claimed": False})
    result["explained"] = not result["issues"]
    return result


class _Evidence(_ArchiveEvidence):
    def _input_sequence(self, action):
        call_id = action["payload"].get("model_call_id")
        matches = [call for call in self.calls if call["call_id"] == call_id]
        return matches[0]["sequence"] if len(matches) == 1 else None

    def _receipts(self, action, event, patch, *, before):
        if before is None:
            return []
        return [p for p in self.visible(action, before=before + 1)
                if isinstance(p.get("visible_result"), dict)
                and p["visible_result"].get("source_reference") == event["source_reference"]
                and patch["patch_id"] in p["visible_result"].get("included_patch_ids", [])
                and p["visible_result"].get("status") == event.get("status")
                and sorted(p["visible_result"].get("conflicts", [])) == sorted(event.get("conflicts", []))]

    def _source_fragments(self, actor, patch, path, symbol, source, previous, references):
        parsed = _module_structure(source["files"][path])
        if not parsed or symbol not in parsed["definitions"]:
            return []
        node = parsed["definitions"][symbol]
        before_lines = {line.strip() for line in previous["files"][path].splitlines()}
        lines = source["files"][path].splitlines()
        candidates = []
        for part in ast.walk(node):
            if not isinstance(part, ast.stmt) or isinstance(part, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if isinstance(part, ast.Expr) and isinstance(part.value, ast.Constant) and isinstance(part.value.value, str):
                continue
            line = lines[part.lineno - 1].strip()
            if line and line not in before_lines and not line.startswith("#"):
                candidates.append({"incoming_line": part.lineno, "literal_line": line,
                                   "statement_sha256": digest(_normalized_node(part).encode())})
        output = []
        allowed = references | {_ref(patch["source_reference"])}
        for p in self.presentations:
            value = p.get("visible_result") or {}
            if (p["member_id"] != actor or p["action"] != "read_file" or value.get("path") != path
                    or _ref(value.get("source_reference")) not in allowed or not isinstance(value.get("text"), str)):
                continue
            shown = {line.strip() for line in value["text"].splitlines()}
            witnesses = [line for line in candidates if line["literal_line"] in shown]
            if witnesses:
                output.append({**_presentation_ref(p), "path": path, "symbol": symbol,
                    "read_source_reference": copy.deepcopy(value["source_reference"]),
                    "incoming_literal_witnesses": witnesses,
                    "scope": "Actual literal production text in a bound input; not understanding or causal adoption."})
        return output

    def _peer_relation(self, inherited, event, tail, final, chain):
        patch = self.facts["patches"][event["patch_id"]]
        actor = chain["delivery"]["actor_id"]
        action = self.world_action(event)
        source, baseline = self.bundle(patch["source_reference"]), self.bundle(patch["base_reference"])
        previous = self.bundle(event["previous_reference"])
        trees = [self.bundle(e["source_reference"]) for e in tail]
        symbols = chain["contract_symbols"]
        test_event = next(e for e in self.world if e["sequence"] == chain["current_version_test"]["world_sequence"])
        test_input = self._input_sequence(self.world_action(test_event))
        metadata = self.metadata_seen(actor, patch, test_input + 1) if test_input is not None else []
        receipts = self._receipts(action, event, patch, before=test_input)
        result = copy.deepcopy(inherited)
        result.update(route_state="unexplained", explanation_complete=False,
                      qualifying_fixed_product_consumption=False, retained_production_units=[],
                      production_unit_comparisons=[], discarded_unit_resets=[], information_timing_failures=[],
                      dependency_issues=[], source_text_presentations=[], source_text_presented=False,
                      historical_v035_whole_file_witness=copy.deepcopy(inherited.get("retained_production_files", [])),
                      process_attributes={"direct_merge": False, "conflict_resolved": False,
                                          "partial_rewrite": False, "discarded_import": False,
                                          "nonproductive_import": False, "source_text_presented": False},
                      import_receipt_presented=bool(receipts), import_receipt_presentations=receipts,
                      fixed_patch_metadata_presented=bool(metadata), metadata_presentations=metadata,
                      scope="v036 production-unit route. World materialization, receipt, metadata and source fragments remain separate facts.")
        known = ((event.get("status") == "merged" and not event.get("conflicts"))
                 or (event.get("status") == "conflict_markers_written" and bool(event.get("conflicts"))))
        if not known or not metadata or not receipts:
            result["dependency_issues"].append("unknown_import_status_or_missing_actual_metadata_receipt")
            return result
        candidates = []
        unit_states = {}
        for path, names in symbols.items():
            snapshots = {
                "patch_starter": _contract_definition_fingerprints(baseline["files"][path], names),
                "incoming": _contract_definition_fingerprints(source["files"][path], names),
                "recipient_before": _contract_definition_fingerprints(previous["files"][path], names),
                "final": _contract_definition_fingerprints(final["files"][path], names),
            }
            if any(value is None for value in snapshots.values()):
                result["dependency_issues"].append("unrecognized_production_definition:" + path)
                continue
            descendant = [_contract_definition_fingerprints(tree["files"][path], names) for tree in trees]
            for symbol in names:
                fingerprints = {name: value[symbol] for name, value in snapshots.items()}
                changed_base = fingerprints["incoming"] != fingerprints["patch_starter"]
                changed_recipient = fingerprints["incoming"] != fingerprints["recipient_before"]
                row = {"path": path, "symbol": symbol, "definition_sha256": fingerprints,
                       "nontrivial_vs_patch_starter": changed_base,
                       "structurally_new_vs_recipient_before": changed_recipient,
                       "incoming_file_differs_from_recipient_before": source["files"][path] != previous["files"][path],
                       "final_unit_equal_incoming": fingerprints["final"] == fingerprints["incoming"],
                       "final_file_equal_incoming": final["files"][path] == source["files"][path],
                       "candidate_productive_unit": changed_base and changed_recipient,
                       "descendant_unit_sha256": [value.get(symbol) if value else None for value in descendant]}
                result["production_unit_comparisons"].append(row)
                if changed_base and changed_recipient:
                    candidates.append(row)
                    unit_states[(path, symbol)] = row["descendant_unit_sha256"]
        if result["dependency_issues"]:
            return result
        if not candidates:
            result.update(route_state="nonproductive", explanation_complete=True)
            result["process_attributes"]["nonproductive_import"] = True
            return result
        references = {_ref(e["source_reference"]) for e in tail}
        for row in candidates:
            path, symbol = row["path"], row["symbol"]
            wanted = row["definition_sha256"]["incoming"]
            states = unit_states[(path, symbol)]
            fragments = self._source_fragments(actor, patch, path, symbol, source, previous, references)
            result["source_text_presentations"].extend(fragments)
            if states[-1] != wanted:
                continue
            dependency = _unit_dependencies(path, symbol, source, final, symbols, chain["ancestors"])
            if not dependency["explained"]:
                result["dependency_issues"].extend(path + ":" + symbol + ":" + issue for issue in dependency["issues"])
                continue
            points = [i for i, state in enumerate(states) if state == wanted and all(v == wanted for v in states[i:])
                      and (i == 0 or tail[i]["kind"] == "edit" and tail[i].get("path") == path and states[i - 1] != wanted)]
            for i in points:
                producing = tail[i]
                producing_action = self.world_action(producing)
                input_sequence = self._input_sequence(producing_action)
                if input_sequence is None:
                    continue
                seen_meta = [p for p in metadata if p["input_sequence"] <= input_sequence]
                seen_receipt = receipts if i == 0 else [p for p in receipts if p["input_sequence"] <= input_sequence]
                relevant = [p for p in fragments if p["input_sequence"] <= input_sequence]
                diagnostic = [p for p in seen_receipt if path in p["visible_result"].get("conflicts", [])]
                # Direct materialization is legal without a source reread. A
                # restoration after parseable replacement needs new source text.
                if i == 0:
                    information_ok = bool(seen_meta and seen_receipt and path not in event.get("conflicts", []))
                    mode = "direct_merge"
                else:
                    later_replacement = [j for j in range(1, i) if states[j] is not None and states[j] != wanted
                                         and tail[j]["kind"] in {"edit", "integrate"}]
                    if later_replacement:
                        floor = self.world_action(tail[later_replacement[-1]])["sequence"]
                        relevant = [p for p in relevant if p["input_sequence"] > floor]
                        information_ok = bool(seen_meta and seen_receipt and relevant)
                    else:
                        information_ok = bool(seen_meta and seen_receipt and (diagnostic or relevant))
                    mode = "conflict_resolved" if diagnostic else "source_visible_restoration"
                if not information_ok:
                    result["information_timing_failures"].append({"path": path, "symbol": symbol,
                        "candidate_producing_action_sequence": producing_action["sequence"],
                        "candidate_input_sequence": input_sequence, "mode": mode,
                        "metadata_seen_before": bool(seen_meta), "receipt_seen_before": bool(seen_receipt),
                        "diagnostic_seen_before": bool(diagnostic), "source_seen_before": bool(relevant)})
                    continue
                result["retained_production_units"].append({"path": path, "symbol": symbol,
                    "incoming_public_unit_sha256": wanted, "final_public_unit_sha256": states[-1],
                    "nontrivial_vs_patch_starter": True, "structurally_new_vs_recipient_before": True,
                    "mode": mode, "producing_event": _world_ref(producing, producing_action),
                    "producing_input_sequence": input_sequence, "continuous_retained_versions": len(states) - i,
                    "retained_version_references": [copy.deepcopy(e["source_reference"]) for e in tail[i:]],
                    "metadata_before_production": copy.deepcopy(seen_meta),
                    "receipt_before_recovery_or_validation": [_presentation_ref(p) for p in seen_receipt],
                    "conflict_diagnosis_before_recovery": [_presentation_ref(p) for p in diagnostic],
                    "source_fragments_before_recovery": relevant, "dependency_explanation": dependency,
                    "final_file_equal_incoming": row["final_file_equal_incoming"],
                    "semantic_equivalence_or_causal_adoption_claimed": False})
                result["process_attributes"]["direct_merge"] |= mode == "direct_merge"
                result["process_attributes"]["conflict_resolved"] |= mode == "conflict_resolved"
                break
        result["source_text_presented"] = bool(result["source_text_presentations"])
        result["process_attributes"]["source_text_presented"] = result["source_text_presented"]
        if result["retained_production_units"] and not result["dependency_issues"]:
            # Other units may change, but each nonretained productive path must
            # have a real, receipt-following transition on this same ancestry.
            unexplained_rewrites = []
            for row in candidates:
                if row["final_unit_equal_incoming"]:
                    continue
                edits = [e for e in tail[1:] if e["kind"] == "edit" and e.get("path") == row["path"]]
                if not any(any(p["input_sequence"] <= (self._input_sequence(self.world_action(e)) or -1)
                               for p in receipts) for e in edits):
                    unexplained_rewrites.append(row["path"] + ":" + row["symbol"])
            if not unexplained_rewrites:
                result.update(route_state="consumed", explanation_complete=True,
                              qualifying_fixed_product_consumption=True)
                result["process_attributes"]["partial_rewrite"] = any(not r["final_file_equal_incoming"] for r in candidates)
                return result
            result["dependency_issues"].extend("unexplained_other_unit_rewrite:" + item for item in unexplained_rewrites)
        # Explained discard is narrower than arbitrary rewriting: witness an
        # actual reset to pre-import/starter public units after receipt, with no
        # later reappearance. A subsequent import can then supply positive work.
        for row in candidates:
            states = unit_states[(row["path"], row["symbol"])]
            wanted = row["definition_sha256"]["incoming"]
            reset_values = {row["definition_sha256"]["recipient_before"], row["definition_sha256"]["patch_starter"]}
            for i, e in enumerate(tail[1:], 1):
                if (e["kind"] != "edit" or e.get("path") != row["path"] or states[i] not in reset_values
                        or any(value == wanted for value in states[i:])):
                    continue
                seq = self._input_sequence(self.world_action(e))
                if seq is not None and any(p["input_sequence"] <= seq for p in receipts) and any(p["input_sequence"] <= seq for p in metadata):
                    result["discarded_unit_resets"].append({"path": row["path"], "symbol": row["symbol"],
                        "reset_event": _world_ref(e, self.world_action(e)), "reset_input_sequence": seq,
                        "reset_definition_sha256": states[i], "incoming_never_reappears_after_reset": True})
                    break
        if (not result["retained_production_units"] and not result["dependency_issues"]
                and len(result["discarded_unit_resets"]) == len(candidates)):
            result.update(route_state="discarded", explanation_complete=True)
            result["process_attributes"]["discarded_import"] = True
        elif not result["dependency_issues"]:
            result["dependency_issues"].append("no_frozen_retention_or_explained_discard_relation")
        return result

    def delivery_chain(self):
        chain = super().delivery_chain()
        chain.update(final_production_units_recognized=False, final_conflict_free=False,
                     unexplained_critical_dependencies=[], process_attributes={})
        if not chain["verified"]:
            return chain
        final = self.bundle(chain["delivery"]["source_reference"])
        symbols = chain["contract_symbols"]
        final_definitions = {path: _contract_definition_fingerprints(final["files"][path], names)
                             for path, names in symbols.items()}
        chain["final_production_units_recognized"] = all(value is not None for value in final_definitions.values())
        chain["final_conflict_markers"] = {path: lines for path in chain["production_paths"]
                                           if (lines := _conflict_markers(final["files"][path]))}
        chain["final_conflict_free"] = not chain["final_conflict_markers"]
        by_sequence = {e["sequence"]: e for e in self.world}
        ancestors = [by_sequence[a["world_sequence"]] for a in chain["ancestors"]]
        positions = {e["sequence"]: i for i, e in enumerate(ancestors)}
        peers = []
        for inherited in chain["peer_integrations"]:
            event = by_sequence[inherited["integration"]["world_sequence"]]
            peer = self._peer_relation(inherited, event, ancestors[positions[event["sequence"]]:], final, chain)
            peers.append(peer)
            if not peer["explanation_complete"]:
                chain["unexplained_critical_dependencies"].append({"patch_id": peer["patch_id"],
                    "reason": "unexplained_final_chain_import", "issues": peer["dependency_issues"]})
        chain["peer_integrations"] = peers
        ids = {p["patch_id"] for p in peers}
        for acquisition in chain["peer_fixed_content_acquisitions"]:
            if acquisition["patch_id"] not in ids:
                chain["unexplained_critical_dependencies"].append({"patch_id": acquisition["patch_id"],
                    "reason": "peer_fixed_source_acquired_without_final_chain_import", "read": acquisition["read"]})
        for patch_id in chain["unresolved_peer_dependencies"]:
            chain["unexplained_critical_dependencies"].append({"patch_id": patch_id, "reason": "unresolved_included_patch"})
        names = mapping_spec()["orthogonal_attributes"]
        chain["process_attributes"] = {name: any(p["process_attributes"].get(name) for p in peers) for name in names}
        chain["production_relation_scope"] = "Frozen public-unit structure plus actual temporal work/input/validation edges. No full semantic or causal equivalence inference."
        return chain


def build_software_evidence(slot_dir, *, rollout=None, assessment=None, expected_window=None):
    """Read an archive or a newly exported rollout; never mutate its targets."""
    folder = Path(slot_dir).resolve()
    if rollout is None:
        rollout = read_json(folder / "entry.json")["rollout"]
    if assessment is None:
        assessment = read_json(folder / "assessment.json")
    window = validate_window(rollout["window"])
    if expected_window is not None and window != expected_window:
        raise ValueError("Do not combine different exact xi, Gamma, team policy or collection windows")
    archive = _Evidence(folder, rollout, assessment)
    chain = archive.delivery_chain()
    verified = {c["call_id"] for c in archive.calls}
    members = {}
    for member, view in archive.views.items():
        own = [d for d in view["decisions"] if d.get("actor_trainable") is True]
        targets = [{"call_id": d["call_id"], "input_ids_sha256": _sha(d["tokens"]["input_ids"]),
                    "output_ids_sha256": _sha(d["tokens"]["output_ids"]),
                    "behavior_logprobs_sha256": _sha(d["tokens"]["behavior_logprobs"]),
                    "labels_sha256": _sha(d["labels"]), "loss_mask_sha256": _sha(d["loss_mask"])} for d in own]
        members[member] = {"member_id": member, "origin": view["origin"],
                           "own_action_count": view["own_action_count"], "own_action_tokens": view["own_action_tokens"],
                           "complete_actor_trajectory": view["complete_actor_trajectory"],
                           "actual_input_bindings_complete": all(d["call_id"] in verified for d in own),
                           "own_targets_sha256": _sha(targets), "own_target_records": targets,
                           "method_does_not_change_actor_targets": True}
    organization = []
    for event in archive.world:
        if event["kind"] in {"task_created", "task_revised", "claim", "delegate", "task_returned", "work_message",
                              "dependency_declared", "dependency_removed", "patch_fixed", "handoff", "integrate", "submit"}:
            action = archive.world_action(event)
            organization.append({**_world_ref(event, action),
                "facts": {k: copy.deepcopy(v) for k, v in event.items() if k not in {
                    "operation_id", "action_id", "sequence", "kind", "actor_id", "logical_time"}},
                "real_response_presentations": archive.visible(action),
                "on_delivered_version_ancestry": any(a["world_sequence"] == event["sequence"] for a in chain["ancestors"])})
    test_information = []
    for event in archive.world:
        if event["kind"] != "test":
            continue
        action = archive.world_action(event)
        returned = action["payload"]["response"].get("result", {})
        shown = archive.visible(action)
        test_information.append({"world_test": _world_ref(event, action),
            "backend_full_result_sha256": _sha(event), "public_return_sha256": _sha(action["payload"]["response"]),
            "source_reference": event["source_reference"], "executed": event.get("executed"),
            "backend_passed": event.get("passed"),
            "public_return_group_passes": {name: group.get("passed") for name, group in returned.get("groups", {}).items()},
            "actual_public_feedback_presentations": shown,
            "backend_full_test_trace_not_promoted_to_actor_input": True,
            "scope": "Overall test status is separate from each public/member group. Only exact selected public returns establish visibility."})
    spec_sha = _sha(mapping_spec())
    result = {"version": VERSION, "mapper_spec_sha256": spec_sha,
              "rollout_id": rollout["rollout_id"], "rollout_sha256": _sha(rollout),
              "manifest_sha256": rollout["manifest_sha256"], "window": window,
              "case_binding": {key: copy.deepcopy(archive.case.get(key)) for key in [
                  "case_id", "purpose", "usage", "first_member", "active_roles", "scheduling_protocol", "team_limits", "editable_paths"]},
              "source_contract_sha256": _sha(archive.case["source_contract"]),
              "source_purpose_allows_support": optimizer_scope_allows_update(rollout),
              "collection_mapper_binding_matches": rollout.get("online_scope", {}).get("method_mapper_spec_sha256") == spec_sha,
              "original_complete_validity": rollout["work_validity"]["value"],
              "original_assessment": {k: assessment.get(k) for k in ["R", "status", "submitted", "content_correct",
                                         "required_process_satisfied", "process_observation_complete"]},
              "actual_visibility_complete": not archive.issues, "visibility_issues": archive.issues,
              "actual_calls": archive.calls, "members": members,
              "organization_and_fixed_products": organization, "delivery_chain": chain,
              "test_information_boundary": test_information,
              "immutable_version_proofs": list(archive.bundle_proofs.values()),
              "archive_refs": {"manifest": _file(archive.episode / "manifest.json"),
                               "original_start_state": _file(archive.episode / "start/control/state.json"),
                               "original_end_state": _file(archive.episode / "end/control/state.json"),
                               "experience": _file(archive.episode / archive.manifest["experience"]["path"])},
              "model_calls": 0, "gpu_used": False, "new_test_or_acceptance_executions": 0,
              "scope": "Read-only v036 finite route/visibility evidence. Old windows are shadow only. No understanding, authorship, semantic equivalence, causal value or optimizer-admission inference."}
    result["evidence_sha256"] = _sha(result)
    return result
