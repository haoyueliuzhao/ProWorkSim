from pathlib import Path
p=Path('/tmp/v054-interleave-session-r1/src/proworksim/software_benchmark_resident_pool_v054.py');s=p.read_text();s=s.replace('POLICY_VERSION = "v054-resident-pool-policy-v1"','POLICY_VERSION = "v054-resident-pool-policy-v1"\nINTERLEAVED_POLICY_VERSION = "v054-resident-pool-policy-v2-interleaved"')
needle='''    policy = read_ref(policy_ref)
    if (policy.get("version") != POLICY_VERSION'''
repl='''    policy = read_ref(policy_ref)
    interleaved = policy.get("version") == INTERLEAVED_POLICY_VERSION
    if interleaved and (policy.get("inherit_modes") != ["REF"]
            or policy.get("MP_session_protocol") != "mp-interleave-v1"
            or policy.get("maximum_MP_sessions_per_resident") != 2
            or policy.get("maximum_REF_sessions_per_resident") != 1):
        raise ValueError("Unrecognized fixed two-session MATCH/PROJECT pool policy")
    if (policy.get("version") not in {POLICY_VERSION, INTERLEAVED_POLICY_VERSION}'''
assert needle in s;s=s.replace(needle,repl,1)
s=s.replace('''or policy.get("maximum_preparation_calls_per_new_resident") != 2''','''or policy.get("maximum_preparation_calls_per_new_resident") != (6 if interleaved else 2)''',1)
s=s.replace('''    read_ref(ready["identity"])
    control = read_ref(admission["check_receipt"])
    policy = read_ref(policy_ref)
    if admission.get("kind") == "inherited_live_resident":''','''    live_identity = read_ref(ready["identity"])
    capacity = declared_session_capacity(declaration, ready=ready, identity=live_identity)
    control = read_ref(admission["check_receipt"])
    policy = read_ref(policy_ref)
    interleaved = policy.get("version") == INTERLEAVED_POLICY_VERSION
    if (capacity == 2 and (not interleaved or admission.get("kind") != "new_interleaved_model_device")):
        raise ValueError("Two-session owner requires its new independently qualified registration")
    if admission.get("kind") == "inherited_live_resident":
        if event["mode"] not in policy.get("inherit_modes", ["REF", "MATCH_PROJECT"]):
            raise ValueError("This pool revision does not inherit that live resident mode")''')
needle='''    elif admission.get("kind") == "new_same_model_device":'''
insert='''    elif admission.get("kind") == "new_interleaved_model_device":
        spec = read_ref(event["source_spec"])
        identity = control.get("resident_identity", {})
        binding = identity.get("resource_binding", {})
        if (not interleaved or capacity != 2 or event["mode"] != "MATCH_PROJECT"
                or spec.get("version") != "v054-match-resident-spec-v3"
                or spec.get("pool_policy") != policy_ref
                or spec.get("resident_id") != event["resident_id"]
                or admission.get("interleaving_check_receipt") != admission["check_receipt"]
                or control.get("version") != "v054-mp-interleave-control-r1"
                or control.get("status") != "passed"
                or control.get("session_protocol") != "mp-interleave-v1"
                or control.get("maximum_sessions") != 2
                or control.get("declaration") != event["declaration"]
                or control.get("authorization") != spec.get("preparation_permit")
                or control.get("actual_model_generation_requests") != 6
                or control.get("completed_sessions") != 4
                or control.get("unsettled_requests") != 0
                or control.get("formal_slots_claimed") != 0
                or control.get("model_loads") != 1
                or any(control.get(key) is not True for key in (
                    "same_resident_PID_and_model", "isolated_sessions", "per_request_FIFO_serialization",
                    "all_three_outputs_equal", "all_three_token_traces_equal", "all_three_rng_transitions_equal"))
                or control.get("weights_reloaded_between_sessions") is not False
                or binding.get("gpu_uuid") != event["gpu_uuid"]
                or binding.get("gpu_index") != event["gpu_index"]
                or identity != live_identity):
            raise ValueError("Interleaved owner lacks its actual six-request independent-session qualification")
        inherited = read_ref(policy["match_template_declaration"])
        baseline = read_ref(inherited["source_spec"])
        if (spec["contract"] != baseline["contract"]
                or spec["capacity_receipt"] != baseline["capacity_receipt"]
                or spec["model_manifest"] != baseline["model_manifest"]):
            raise ValueError("Interleaving changed original numerical/model/capacity identity")
    elif admission.get("kind") == "new_same_model_device":
        if interleaved or capacity != 1:
            raise ValueError("Sequential preparation cannot qualify a two-session pool revision")'''
assert needle in s;s=s.replace(needle,insert,1)
p.write_text(s)
p=Path('/tmp/v054-interleave-session-r1/src/proworksim/software_benchmark_resident_session_v054.py');s=p.read_text();s=s.replace('VERSION = "v054-resident-session-v2-interleave"','VERSION = "v054-resident-session-v1"')
s=s.replace('''if (deployment.get('version') != 'v054-match-resident-spec-v2' ''','''if (deployment.get('version') not in {'v054-match-resident-spec-v2', 'v054-match-resident-spec-v3'} ''') if False else s
s=s.replace('''if (deployment.get('version') != 'v054-match-resident-spec-v2'\n''','''if (deployment.get('version') not in {'v054-match-resident-spec-v2', 'v054-match-resident-spec-v3'}\n''')
s=s.replace('''            self.session = {"session_slot": session_slot, "maximum_sessions": capacity,
                            "session_protocol": declaration.get("session_protocol"), "version": VERSION,''','''            session_contract = ({"session_slot": session_slot, "maximum_sessions": 2,
                                 "session_protocol": INTERLEAVE_PROTOCOL} if capacity == 2 else {})
            self.session = {**session_contract, "version": VERSION,''')
p.write_text(s)
