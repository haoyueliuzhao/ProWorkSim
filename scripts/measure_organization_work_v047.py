"""v047 work facts, exact candidate applications and all-member cost boundaries.

Evidence binds original inputs, opportunities and resource views to the new
capacity receipt. It does not extend symbols, syntax or semantic use criteria.
The old declared-symbol and semantic analysis is imported with its coverage
limits; whole-file adoption and architecture accounting are separate new facts.
No mutable module globals, files, histories, or ledgers are patched.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

from proworksim.storage import digest, json_bytes
from scripts import measure_organization_budget_v047 as budget_proof
from scripts import measure_organization_work_v045 as previous
from scripts.software_organization_reporting_v047 import submission_costs
from scripts.measure_organization_work_v045 import (
    STAGES, aggregate, base, current_information_work,
    current_program_work, information_relations, one, program_relations,
    require, source, stage,
)

VERSION = "organization-work-use-v0.47"
OPPORTUNITY_VERSION = "organization_work_opportunity_v047"




class Evidence(previous.Evidence):
    def _inputs(self):
        self.capacity_binding = budget_proof.read_capacity_binding(self.folder, result=self.result, budget=self.budget)
        attempts = self.evidence.get("original_attempts", [])
        originals = {row["call_id"]: row for row in attempts}
        require(len(originals) == len(attempts), "duplicate_original_attempt")
        records = self.budget["records"]
        for directory in sorted((self.folder / "raw-transport").glob("request-*")):
            call_id = None
            try:
                turn = base.read(directory / "runner-turn.json")
                call_id, member = turn["association"]["call_id"], turn["member_id"]
                require(call_id not in self.calls, "duplicate_actual_call_id")
                record = records[call_id]
                if record.get("attempt_started") is False and record.get("status") in {
                        "decision_consumed", "admission_rejected", "cancelled_before_dispatch"}:
                    # Preparation is not actual consumption. The saved refusal
                    # is independently checked by opportunity and stop readers.
                    continue
                original = originals[call_id]
                require(record["member"] == member == original["worker_id"] == turn["association"]["worker_id"],
                        "actual_call_member_mismatch")
                require(record.get("attempt_started") is True and record.get("status") == "settled"
                        and original.get("status") == "success" and original.get("original_output_present") is True,
                        "actual_call_not_settled_original_output")
                selected_path = directory / "selected-request.json"
                selected, preparation, projection, response = (base.read(directory / name) for name in
                    ("selected-request.json", "budget-preparation.json", "projection.json", "response.json"))
                budget_proof.validate_preparation_capacity(preparation, self.capacity_binding)
                body, charge = response["body"], record["charge"]
                trace, usage = body["token_trace"], body["usage"]
                require(response.get("http_status") == 200 and digest(json_bytes(body)) == original["response_body_sha256"]
                        == charge["response_body_sha256"] and body["id"] == original["response_id"] == charge["response_id"],
                        "original_native_output_identity_mismatch")
                require(preparation == record["reservation"]["preparation"]
                        and preparation["preparation_sha256"] == digest(json_bytes({k: v for k, v in preparation.items()
                                                                                 if k != "preparation_sha256"})),
                        "unbound_original_preparation")
                require(digest(selected_path.read_bytes()) == preparation["selected_request_sha256"]
                        == projection["selected_request_sha256"], "selected_input_bytes_changed")
                require(digest(json_bytes(trace["input_ids"])) == preparation["input_ids_sha256"]
                        == projection["input_ids_sha256"] == original["input_ids_sha256"]
                        and digest(json_bytes(trace["output_ids"])) == original["output_ids_sha256"],
                        "original_input_or_output_token_trace_mismatch")
                require(body["actor_identity"] == preparation["actor_identity"] == self.result["actor_identity"]
                        and body["online_window_id"] == preparation["window_id"] == "organization-v047:" + self.result["slot_id"],
                        "actual_actor_or_window_mismatch")
                require(usage == original["usage"] == charge["reported_usage"]
                        and usage["prompt_tokens"] == len(trace["input_ids"]) == preparation["prompt_tokens"]
                        and usage["completion_tokens"] == len(trace["output_ids"])
                        and usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"] == charge["charged_tokens"],
                        "actual_usage_or_charge_mismatch")
                require(preparation["reserved_output_tokens"] == selected["max_tokens"] == 2048
                        and preparation["context_limit"] == 18432 and preparation["fits"] is True
                        and preparation["prompt_tokens"] + 2048 <= 18432, "actual_request_context_contract_mismatch")
                starts = [e for e in self.by_kind["model_call"] if isinstance(e.get("payload"), dict)
                          and e["payload"].get("call_id") == call_id and e["payload"].get("stage") == "started"]
                start = one(starts, "missing_or_ambiguous_original_call_start")
                require(start["worker_id"] == member and start["sequence"] < original["experience_sequence"],
                        "actual_call_start_order_or_member_mismatch")
                call = {"call_id": call_id, "member": member, "path": str(selected_path),
                    "experience_sequence": original["experience_sequence"], "start_sequence": start["sequence"],
                    "opportunity_id": start["payload"].get("opportunity_id"),
                    "selected_request_sha256": preparation["selected_request_sha256"],
                    "input_ids_sha256": preparation["input_ids_sha256"], "preparation": preparation,
                    "source": source(selected_path), "response_source": source(directory / "response.json")}
                self.calls[call_id], self.message_cache[call_id], self.native[call_id] = call, selected["messages"], body
            except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
                self.gap(str(error), call_id=call_id, raw_request=str(directory))
        expected = {call for call, record in records.items() if record.get("attempt_started") is True}
        if expected != set(self.calls) or expected != set(originals):
            self.gap("not_all_original_attempts_bound", expected=sorted(expected), bound=sorted(self.calls),
                     original_attempts=sorted(originals))

    def _opportunities(self):
        grouped = defaultdict(dict)
        self.unstarted_opportunities = []
        for event in self.by_kind[OPPORTUNITY_VERSION]:
            payload = event.get("payload", {})
            key, phase = payload.get("opportunity_id"), payload.get("phase")
            if not key or phase not in {"before", "after"} or phase in grouped[key]:
                self.gap("malformed_or_duplicate_opportunity_receipt", experience_sequence=event["sequence"])
                continue
            grouped[key][phase] = event
        for key, pair in grouped.items():
            try:
                before, after = pair["before"], pair["after"]
                bp, ap = before["payload"], after["payload"]
                member = bp["member_id"]
                require(before["sequence"] < after["sequence"] and member == ap["member_id"]
                        and bp["opportunity_ordinal"] == ap["opportunity_ordinal"], "opportunity_scope_mismatch")
                calls = [e for e in self.by_kind["model_call"] if isinstance(e.get("payload"), dict)
                         and e["payload"].get("stage") == "started" and e["payload"].get("opportunity_id") == key]
                for snapshot in (bp, ap):
                    budget_proof.validate_stage_snapshot(snapshot["stage_budget"], snapshot["team_budget"],
                        condition=self.result["condition"], token_budget=self.result["team_token_budget"])
                if not calls:
                    require(bp["team_budget"] == ap["team_budget"]
                            and bp["world_event_sequence"] == ap["world_event_sequence"]
                            and ap.get("outcome_status") == "stage_budget_exhausted"
                            and bp["stage_budget"]["remaining_decisions"] == 0,
                            "unstarted_opportunity_lacks_same_ledger_phase_decision_boundary")
                    self.unstarted_opportunities.append({"opportunity_id": key, "member": member,
                        "before_sequence": before["sequence"], "after_sequence": after["sequence"],
                        "stage_id": bp["stage_budget"]["stage_id"], "attempt_started": False,
                        "charged_tokens": 0, "decision_consumed": False,
                        "reason": "already_exhausted_stage_decision_allowance"})
                    continue
                start = one(calls, "opportunity_not_exactly_one_call_start")
                require(start["worker_id"] == member and before["sequence"] < start["sequence"] < after["sequence"],
                        "opportunity_does_not_contain_same_member_call")
                call_id = start["payload"]["call_id"]
                record = self.budget["records"][call_id]
                resolved = budget_proof.resolve_preparation(call_id, start=start, before=before, after=after,
                    result=self.result, budget=self.budget, evidence=self.evidence, events=self.experience,
                    capacity_binding=self.capacity_binding)
                prep = resolved["preparation"]
                require(type(bp["team_budget"]["available_tokens"]) is int, "missing_original_opportunity_pool")
                self.opportunities.append({"opportunity_id": key, "ordinal": bp["opportunity_ordinal"],
                    "member": member, "call_id": call_id, "before_sequence": before["sequence"],
                    "after_sequence": after["sequence"], "call_start_sequence": start["sequence"],
                    "world_event_sequence_before": bp["world_event_sequence"], "availability": bp["availability"],
                    "team_budget_before": bp["team_budget"], "preparation": prep,
                    "stage_budget_before": bp["stage_budget"], "stage_budget_after": ap["stage_budget"],
                    "actual_generation_started": record.get("attempt_started") is True,
                    "terminal_status": ap.get("outcome_status"),
                    "preparation_source": resolved["source"],
                    "member_fixed_budget_attribution": resolved["member_fixed_budget_attribution"],
                    "source": self.experience_point(before), "after_source": self.experience_point(after)})
            except (KeyError, IndexError, TypeError, ValueError) as error:
                self.gap(str(error), opportunity_id=key)
        self.opportunities.sort(key=lambda row: row["before_sequence"])
        if {row["call_id"] for row in self.opportunities} != set(self.budget["records"]):
            self.gap("incomplete_original_opportunity_resource_receipts")

    def resource(self, call_or_opportunity):
        call_id = call_or_opportunity["call_id"]
        found = [row for row in self.opportunities if row["call_id"] == call_id]
        if len(found) != 1:
            return {"status": "measurement_pending", "call_id": call_id, "reason": "missing_unique_opportunity_receipt"}
        row = found[0]
        prep, pool = row["preparation"], row["team_budget_before"]
        try:
            prompt, reserved, limit = (prep[key] for key in ("prompt_tokens", "reserved_output_tokens", "context_limit"))
            require(all(type(v) is int for v in (prompt, reserved, limit)) and reserved == 2048 and limit == 18432,
                    "incomplete_original_preparation_counts")
            later = [r for r in self.opportunities if r["member"] == row["member"]
                     and r["before_sequence"] > row["after_sequence"]]
            return {"status": "recorded", "call_id": call_id, "member": row["member"],
                "opportunity_id": row["opportunity_id"], "opportunity_ordinal": row["ordinal"],
                "actual_generation_started": row["actual_generation_started"],
                **({"preparation_source": row["preparation_source"],
                    "member_fixed_budget_attribution": row["member_fixed_budget_attribution"]}
                   if row["member_fixed_budget_attribution"] is not None else {}),
                "prompt_tokens": prompt, "reserved_output_tokens": reserved, "context_limit": limit,
                "hard_headroom_tokens": limit - prompt - reserved,
                "team_available_tokens_before_opportunity": pool["available_tokens"],
                "remaining_decisions_before_opportunity": pool.get("remaining_decisions"),
                "remaining_attempts_before_opportunity": pool.get("remaining_attempts"),
                "later_member_opportunities": len(later),
                "later_member_actual_generations": sum(r["actual_generation_started"] for r in later),
                "later_member_call_ids": [r["call_id"] for r in later], "source": row["source"],
                "scope": "Original before-opportunity pool and sealed selected-request preparation; no final-balance substitution or new encoding."}
        except (KeyError, TypeError, ValueError) as error:
            return {"status": "measurement_pending", "call_id": call_id, "reason": str(error)}


def exact_candidate_applications(data):
    """Whole-file exact adoption, separate from the inherited symbol tracker."""
    rows, gaps = [], []
    patches = data.software.get("patches", {})
    for event in data.events:
        if event.get("kind") != "candidate_adopted":
            continue
        try:
            call = data.bound(event)
            require(call is not None, "candidate_application_missing_original_native_action")
            patch = patches[event["patch_id"]]
            before, before_path, before_error = data.versions.get(event["previous_reference"])
            incoming, incoming_path, incoming_error = data.versions.get(event["input_reference"])
            after, after_path, after_error = data.versions.get(event["source_reference"])
            require(not any((before_error, incoming_error, after_error)), "candidate_application_missing_exact_version")
            incoming_hash, after_hash = digest(json_bytes(incoming)), digest(json_bytes(after))
            require(event["input_reference"] == patch["source_reference"]
                    and incoming_hash == after_hash == patch["files_sha256"]
                    == event["files_sha256"] == event["selected_candidate_files_sha256"]
                    and event.get("exact_files_match") is True and event.get("native_model_action") is True,
                    "candidate_application_whole_file_identity_mismatch")
            member = event["actor_id"]
            retirement = data.registry[member].get("retirement_sequence")
            require(retirement is None or retirement > event["sequence"], "candidate_applied_after_recipient_retirement")
            changed = sorted(path for path in set(before) | set(after) if before.get(path) != after.get(path))
            tests = []
            submissions = []
            for later in data.events:
                if later.get("actor_id") != member or later["sequence"] <= event["sequence"] or data.bound(later) is None:
                    continue
                if later.get("kind") not in {"test", "submit"}:
                    continue
                files, _, error = data.versions.get(later.get("source_reference"))
                if error or files != incoming:
                    continue
                item = {"world_sequence": later["sequence"], "call_id": data.bound(later)["call_id"],
                        "source_reference": later["source_reference"], "files_sha256": incoming_hash}
                (tests if later["kind"] == "test" else submissions).append(item)
            tested_submissions = [submission for submission in submissions if any(
                test["world_sequence"] < submission["world_sequence"] for test in tests)]
            final_delivery = (data.software.get("deliveries") or [None])[-1]
            final_match = bool(tested_submissions and final_delivery and any(
                submission["source_reference"] == final_delivery.get("source_reference") for submission in tested_submissions))
            rows.append({"status": "verified_exact_file_application", "native_call_id": call["call_id"],
                "world_sequence": event["sequence"], "stage_id": event.get("stage_id"),
                "recipient": member, "source_member": patch["author"], "patch_id": patch["patch_id"],
                "cross_member": member != patch["author"], "changed_paths": changed,
                "nonidentity_file_application": bool(changed), "files_sha256": incoming_hash,
                "input_reference": event["input_reference"], "previous_reference": event["previous_reference"],
                "source_reference": event["source_reference"], "own_exact_candidate_tests_after_application": tests,
                "own_exact_candidate_submissions_after_application": submissions,
                "tested_submission_is_final_locked_delivery": final_match,
                "sources": {"event": data.point(event), "before": source(before_path),
                            "incoming": source(incoming_path), "after": source(after_path)},
                "scope": "A real native exact-file adoption, not three-way merge, semantic comprehension or causal benefit. Source-author retirement does not revoke the fixed readable artifact."})
        except (KeyError, TypeError, ValueError, OSError) as error:
            gaps.append({"world_sequence": event.get("sequence"), "reason": str(error)})
    return rows, gaps


def episode_accounting_and_applications(data):
    """Join already-loaded actual traces once; never re-run candidates or tests."""
    calls = []
    by_member = {member: {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                 for member in data.registry}
    for call in sorted(data.calls.values(), key=lambda row: row["experience_sequence"]):
        usage = data.native[call["call_id"]]["usage"]
        calls.append({"call_id": call["call_id"], "member": call["member"],
                      "experience_sequence": call["experience_sequence"], "usage": usage})
        own = by_member[call["member"]]
        own["calls"] += 1
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            own[key] += usage[key]
    totals = {key: sum(row[key] for row in by_member.values())
              for key in ("calls", "prompt_tokens", "completion_tokens", "total_tokens")}
    attempted = {key for key, row in data.budget["records"].items() if row.get("attempt_started") is True}
    usage_complete = set(data.calls) == attempted and data.result.get("usage", {}).get("uncertain_usage_attempts") == 0
    costs = {"status": "complete" if usage_complete else "incomplete",
             "known_actual_usage": totals, "complete_actual_tokens": totals["total_tokens"] if usage_complete else None,
             "budget_charged_tokens": data.budget["charged_tokens"], "by_member": by_member,
             "scope": "Original actual input/output traces summed over all members and all calls, including failed work and activity after submission. Reservations are not actual consumption; no nested native time is added to worker occupancy."}
    submissions, cutpoint_gaps = [], []
    for event in data.events:
        if event.get("kind") != "submit":
            continue
        call = data.bound(event)
        if call is None:
            cutpoint_gaps.append({"world_sequence": event["sequence"], "reason": "submission_native_binding_missing"})
            continue
        fixed_patch_ids = sorted(patch["patch_id"] for patch in data.software.get("patches", {}).values()
                                 if patch.get("source_reference") == event.get("source_reference"))
        submissions.append({"sequence": event["sequence"], "call_id": call["call_id"],
                            "member": event["actor_id"], "source_reference": event.get("source_reference"),
                            "files_sha256": event.get("files_sha256"), "delivery_id": event.get("delivery_id"),
                            "fixed_patch_ids": fixed_patch_ids, "actual_native_binding_verified": True})
    try:
        cutpoints = submission_costs(calls, submissions, episode_usage_complete=usage_complete)
        locked = data.result.get("deadline_receipt", {}).get("locked_submission")
        require((not submissions and locked is None) or bool(submissions and locked
                and locked.get("source_reference") == submissions[-1]["source_reference"]
                and locked.get("delivery_id") == submissions[-1]["delivery_id"]
                and locked.get("files_sha256") == submissions[-1]["files_sha256"]),
                "submission_cost_final_cutpoint_differs_from_locked_last_candidate")
        cutpoints["final_lock_binding_verified"] = True
    except (KeyError, TypeError, ValueError) as error:
        cutpoints = None
        cutpoint_gaps.append({"reason": str(error)})
    try:
        stages = budget_proof.validate_stage_accounting(data.result, data.result["team_budget"])
    except (KeyError, TypeError, ValueError) as error:
        stages = {"status": "measurement_pending", "reason": str(error)}
    applications, application_gaps = exact_candidate_applications(data)
    model_tests = [event for event in data.events if event.get("kind") == "test" and data.bound(event) is not None]
    return {"cost_accounting": costs, "submission_costs": cutpoints,
        "submission_cost_gaps": cutpoint_gaps, "stage_accounting": stages,
        "population_measurements": {"cumulative_born_members": len(data.registry),
            "actual_call_members": [member for member, usage in by_member.items() if usage["calls"] > 0],
            "actual_call_participant_count": sum(usage["calls"] > 0 for usage in by_member.values()),
            "original_lifecycle": data.result.get("member_lifecycle"),
            "birth_retirement_events": [data.point(event) for event in data.events
                                         if event.get("kind") in {"member_spawned", "member_retired"}],
            "per_member_actual_cost": by_member,
            "scope": "Logical member usage, independent of resident-worker count; free-organization runs that use only one member remain in their assigned capacity treatment."},
        "exact_candidate_applications": applications, "candidate_application_gaps": application_gaps,
        "exact_candidate_application_scope": "Independent whole-file native application evidence, separate from the unchanged historical declared-symbol tracker and its coverage limits.",
        "unstarted_stage_opportunities": data.unstarted_opportunities,
        "environment_initial_diagnostics": data.software.get("initial_diagnostics", {}),
        "environment_preparation_cost": data.result.get("environment_preparation_cost"),
        "current_member_test_executions": [{"event": data.point(event), "stage_id": event.get("stage_id"),
                                            "call_id": data.bound(event)["call_id"]} for event in model_tests],
        "test_scope": "Initial diagnostics are environment preparation. Current tests belong to their exact member/event/version; predecessor tests do not substitute for a final submitter's own current-version execution."}


def measure_episode(episode_dir):
    folder = Path(episode_dir).resolve()
    header = {"version": VERSION, "episode": str(folder), "read_only": True,
        "new_model_calls": 0, "new_tokenizer_calls": 0, "new_world_actions": 0,
        "new_test_or_acceptance_executions": 0, "training_support": False,
        "contribution_eligible": False, "independent_confirmation_eligible": False,
        "has_evidenced_cross_member_chain": None, "has_evidenced_cross_member_use": None,
        "has_use_linked_to_final_fixed_delivery": None, "program_work_chains": [],
        "information_work_chains": [], "measurement_gaps": [], "totals": {}}
    try:
        data = Evidence(folder)
    except (OSError, KeyError, IndexError, TypeError, ValueError) as error:
        return {**header, "status": "measurement_pending", "measurement_gaps": [{"reason": str(error)}]}
    result, case = data.result, data.software.get("case", {})
    initial_members = result.get("member_lifecycle", {}).get("initial_members", [])
    condition = result.get("condition", case.get("condition"))
    if not data.registry or not initial_members:
        data.gap("missing_original_member_registry_or_initial_members")
    if condition == "S1" and (len(data.registry) != 1 or len(initial_members) != 1):
        data.gap("s1_contains_hidden_partner_or_birth")
    program, non_work = current_program_work(data)
    program_rows = program_relations(data, program)
    information, reexecutions = current_information_work(data)
    info_rows, initial_forwarding, info_pending = information_relations(data, information, reexecutions)
    rows = program_rows + info_rows
    for row in rows:
        if row["stages"]["produced"]["value"] is not True:
            for key in ("used", "fixed_delivery"):
                if row["stages"][key]["value"] is True:
                    row["stages"][key] = stage(None, "measurement_pending", reason="current_work_production_not_proved")
    program_chains = [row for row in program_rows if row["stages"]["used"]["value"] is True]
    info_chains = [row for row in info_rows if row["stages"]["used"]["value"] is True]
    unresolved = [row for row in rows if any(row["stages"][key]["value"] is None for key in STAGES[:4])]
    use = aggregate(rows, "used")
    if use is False and (data.gaps or unresolved or info_pending):
        use = None
    fixed = aggregate(rows, "fixed_delivery")
    if fixed is False and (data.gaps or use is None):
        fixed = None
    no_partner = len(data.registry) == 1 and condition == "S1"
    if no_partner and not data.gaps:
        use = fixed = False
    member_work = {}
    for member, registry in data.registry.items():
        own = [event for event in data.events if event.get("actor_id") == member and data.bound(event)]
        member_work[member] = {"origin": registry.get("origin", "initial_configuration"),
            "actual_output_calls": len(data.by_member(member)), "actual_event_counts": dict(Counter(e["kind"] for e in own)),
            "current_program_work": sum(work["source_member"] == member and work["stage"]["value"] is True for work in program),
            "current_information_work": sum(work["source_member"] == member for work in information),
            "initial_material_reexecutions": sum(work["source_member"] == member for work in reexecutions)}
    extended = episode_accounting_and_applications(data)
    return {**header, "status": "measurement_pending" if data.gaps else "measured", "slot_id": result.get("slot_id"),
        **extended,
        "purpose": result.get("purpose"), "condition": condition, "recorded_R": result.get("R"),
        "recorded_submitted": result.get("submitted"), "has_evidenced_cross_member_chain": use,
        "has_evidenced_cross_member_use": use, "has_use_linked_to_final_fixed_delivery": fixed,
        "cross_member_applicability": "not_applicable_no_partner" if no_partner else "applicable",
        "member_work": member_work, "current_program_work": program, "nonstructural_or_initial_program_edits": non_work,
        "current_information_work": information, "initial_material_reexecutions": reexecutions,
        "initial_material_forwarding": initial_forwarding, "five_stage_relations": rows,
        "program_work_chains": program_chains, "information_work_chains": info_chains,
        "pending_program_relations": [row for row in unresolved if row["work_kind"] == "program"],
        "pending_semantic_relations": info_pending + [row for row in unresolved if row["work_kind"] == "information"],
        "measurement_gaps": data.gaps, "final_delivery": base.final_evidence(result, data.events, data.state_path),
        "totals": {"observed_members": len(data.registry), "initial_members": len(initial_members),
            "current_program_artifacts": sum(work["stage"]["value"] is True for work in program),
            "current_information_artifacts": len(information), "evidenced_program_work_chains": len(program_chains),
            "evidenced_information_work_chains": len(info_chains),
            "chains_closed_to_final_fixed_delivery": sum(row["stages"]["fixed_delivery"]["value"] is True for row in rows),
            "initial_material_forwardings": len(initial_forwarding), "initial_material_reexecutions": len(reexecutions),
            "pending_program_relations": sum(row["work_kind"] == "program" for row in unresolved),
            "information_candidates_needing_manual_review": len(info_pending) + sum(row["work_kind"] == "information" for row in unresolved),
            "model_requested_births": sum(event.get("kind") == "member_spawned" and data.bound(event) is not None for event in data.events)},
        "first_stage_opportunities": [{"work_id": row["work_id"], "recipient": row.get("recipient"),
            "first_eligible_sharing": row["first_eligible_share_opportunity"],
            "first_actual_acquisition": row["stages"]["acquired"].get("resource"),
            "first_verified_use": row["stages"]["used"].get("resource")} for row in rows],
        "sources": {"result": source(data.result_path), "world": data.world_source,
            "experience": data.experience_source, "organization_evidence": source(data.evidence_path),
            "team_budget": source(data.budget_path)},
        "criterion": "Five stages are separate. True use requires original current-work provenance and actual verifiable partner consumption; false requires complete evidence, null preserves missing/semantic evidence. Reading, accessibility, similar code and multiple members are not use. R and delivery success never select eligible use evidence.",
        "information_scope": "Current report creation, authorized exact text transmission and actual input acquisition are mechanical. Free-text advice or acquisition followed by work remains pending until an independent source inspection establishes a specific use; no semantic verdict is fabricated."}


