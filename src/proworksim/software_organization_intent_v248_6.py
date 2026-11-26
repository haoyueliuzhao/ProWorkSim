"""P2 OSA tool interface. The frozen public menu supplies executable organization fields."""

from copy import deepcopy
import json

from jsonschema import Draft202012Validator

from . import software_organization_patch_v247 as controller


PROMPT = """You are the independent organization strategist. Read only the supplied public project evidence, open obligations, team graph and remaining shared resources. Identify the engineering issue first, then explain the uncovered or duplicated work that the existing team cannot handle, or why keeping it works. Distinguish A1 repeated verified failure, A2 unusable upstream product, A3 integration conflict, A4 verification gap and A5 sustained delivery stall from STABLE or UNKNOWN. An incomplete task or test failure alone does not justify reorganization. Compare keeping the current team with the available candidates, including initialization, transfer of unfinished work, verification, handoff and coordination cost. Fixed-size teams can change duties; dynamic teams can also change membership if offered. Choose one candidate ID for CHANGE, or none for KEEP or ABSTAIN. Explain your judgment, cite visible evidence and estimate coordination input and output separately. For CHANGE specify how the listed product will be used, verified and judged to have failed, the first action, subsequent actions and preconditions. For KEEP or ABSTAIN omit the change plan. Name a concrete reevaluation trigger; for ABSTAIN identify missing evidence. All members share five million tokens. A promised product or review still requires real work. Return one activate_organization tool call. Put fields directly at the top level and finish the entire arguments object. The controller binds graph versions, ordered operations, member identities, product ownership and reserved turns from your choice."""


def obj(**fields):
    return dict(type="object", properties=fields, required=list(fields), additionalProperties=False)


def wire(state):
    request = controller.wire(state)
    tool = request["tools"][0]["function"]
    old = tool["parameters"]["properties"]
    expected = old["expected_contribution"]["properties"]
    plan = old["execution_plan"]["properties"]
    schema = obj(
        assessment=old["assessment"],
        decision=old["decision"],
        coordination_cost=old["resource_plan"]["properties"]["coordination_cost"],
        reevaluation=old["reevaluation"],
    )
    schema["properties"]["change_plan"] = obj(
        **{name: expected[name] for name in ("intended_use", "verification", "failure_condition")},
        first_action=plan["immediate_action"]["properties"]["action"],
        subsequent_actions=plan["subsequent_actions"],
        preconditions=plan["preconditions"],
    )
    schema["properties"]["assessment"]["properties"]["evidence_refs"]["minItems"] = 1
    tool.update(
        description="Select one public candidate or keep/defer, with evidence.", parameters=schema
    )
    request["messages"][0]["content"] = PROMPT
    return request


def unique_object(entries):
    result = {}
    for key, value in entries:
        if key in result:
            raise ValueError(f"Duplicate proposal field: {key}")
        result[key] = value
    return result


def unpack(arguments):
    if isinstance(arguments, str):
        arguments = json.loads(arguments, object_pairs_hook=unique_object)
    if isinstance(arguments, dict) and set(arguments) == {"request"}:
        arguments = arguments["request"]
        if isinstance(arguments, str):
            arguments = json.loads(arguments, object_pairs_hook=unique_object)
    return arguments


def compile_intent(state, arguments):
    intent = unpack(arguments)
    Draft202012Validator(wire(state)["tools"][0]["function"]["parameters"]).validate(intent)
    decision = intent["decision"]
    changing = decision["action"] == "CHANGE"
    if changing != ("change_plan" in intent) or changing != (decision["candidate_id"] != "none"):
        raise ValueError("Only CHANGE selects a candidate and supplies a change plan")

    graph = state["organization_graph"]
    candidate = state["candidates"].get(decision["candidate_id"], {})
    ops = deepcopy(candidate.get("operations", []))
    size = sum(status == "live" for status in graph["members"].values())
    membership_modes = dict(
        JOIN="ADD_MEMBER", RETIRE="RETIRE_MEMBER", PAUSE="PAUSE_MEMBER", RESUME="RESUME_MEMBER"
    )
    lifecycle = [op for op in ops if op["dimension"] == "D0"]
    joins = [op["member"] for op in lifecycle if op["operation"] in ("JOIN", "RESUME")]
    exits = [op["member"] for op in lifecycle if op["operation"] in ("RETIRE", "PAUSE")]
    work = intent.get("change_plan", {})
    contribution = {
        name: candidate.get(name, "none") for name in ("producer", "consumer", "artifact")
    }
    for name in ("intended_use", "verification", "failure_condition"):
        contribution[name] = work.get(name, "none")
    proposal = dict(
        decision=decision,
        assessment=intent["assessment"],
        reevaluation=intent["reevaluation"],
        membership_decision=dict(
            action=membership_modes[lifecycle[0]["operation"]] if lifecycle else "KEEP_SIZE",
            current_active_members=size,
            proposed_active_members=size + len(joins) - len(exits),
            members_to_activate=joins,
            members_to_retire=exits,
        ),
        organization_patch=dict(
            base_graph_version=graph["version"],
            base_hash=state["base_hash"],
            target_graph_version=graph["version"] + len(ops),
            operations=ops,
        ),
        expected_contribution=contribution,
        execution_plan=dict(
            immediate_action=dict(
                actor=contribution["producer"],
                action=work.get("first_action", "none"),
                expected_artifact=contribution["artifact"],
            ),
            subsequent_actions=work.get("subsequent_actions", []),
            preconditions=work.get("preconditions", []),
        ),
        resource_plan=dict(
            team_token_limit=5000000,
            reserved_worker_actions=[op["member"] for op in ops if op["operation"] == "TURN"],
            coordination_cost=intent["coordination_cost"],
        ),
    )
    controller.decide(state, proposal)
    return proposal


def apply(world, runtime, state, arguments):
    return controller.apply(world, runtime, state, compile_intent(state, arguments))


public_state = controller.public_state
snapshot = controller.snapshot
