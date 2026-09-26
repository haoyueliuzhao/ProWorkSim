"""Public-observation CPU witnesses under the actual round-robin deadline.

These policies verify feasible paths, including waits; they are never training
trajectories and have no access to the world state or evaluator in decide().
"""

import argparse
import copy
from decimal import Decimal
from pathlib import Path

from proworksim.audit import code_identity
from proworksim.episode import begin_episode, finish_episode
from proworksim.experience import ExperienceRecorder, capture_port
from proworksim.online_collection import run_fragment
from proworksim.retail_rewards import assess_retail_reward
from proworksim.staff_runtime import PolicyBoundaryError, StaffRuntime
from proworksim.storage import json_bytes
from proworksim.templates.retail_work import build_retail_case, registry, witness_code
from proworksim.work_interface import WorkInterface


def records(table):
    return [dict(zip([column["name"] for column in table["columns"]], row)) for row in table["rows"]]


class PublicWitnessPolicy:
    """A strategy with only the same tools, observation and memory as a worker."""

    def __init__(self, *, role, task, limit, communication="proactive", control=None):
        self.config = {"role": role, "task": task, "limit": limit,
                       "communication": communication, "control": control}

    def decide(self, context):
        memory = copy.deepcopy(context["memory"])
        memory.setdefault("cache", {})
        pending = memory.pop("pending", None)
        if pending:
            response = context["last_result"]
            if not response["ok"]:
                raise ValueError({"actual_rule_path_refusal": response})
            memory["cache"][pending] = response["result"]
        used = memory.get("decisions", 0)
        if used >= self.config["limit"]:
            raise PolicyBoundaryError("model_budget_exhausted", "Same finite decision limit as the model", memory=memory)
        memory["decisions"] = used + 1
        obs, role, task = context["observation"], self.config["role"], self.config["task"]
        cache, control = memory["cache"], self.config["control"]
        wid = "TEAM::build"

        def act(key, action, **arguments):
            memory["pending"] = key
            return {"kind": "act", "action": action, "arguments": arguments, "memory": memory}

        def wait(reason):
            return {"kind": "wait", "reason": reason, "memory": memory}

        def read(alias):
            return act("read:" + alias, "read_alias", alias=alias, work_id=wid)

        def done():
            return {"kind": "done", "reason": "Declared responsibility handled", "memory": memory}

        if control == "no_actions":
            return done()
        # Public routes, not role names, determine who can supply which source.
        for route in obs["information_routes"]:
            if route["provider"] != role or role in route["recipients"] or task not in {"pair", "chain"}:
                continue
            alias = route["object_alias"]
            if "sent:" + alias in cache:
                continue
            if "read:" + alias not in cache:
                return read(alias)
            if control == "read_only" and task == "handoff":
                return done()
            request = None
            if self.config["communication"] == "requested" and alias == "basis":
                if "messages" not in cache:
                    return act("messages", "read_messages")
                request = next((message for message in cache["messages"]
                                if isinstance(message.get("body"), dict)
                                and message["body"].get("route_id") == route["route_id"]), None)
                if request is None:
                    cache.pop("messages", None)
                    return wait("Awaiting the public recipient's request")
            args = {"route_id": route["route_id"], "work_id": wid, "handoff_key": "witness-" + alias,
                    "reference": cache["read:" + alias]["reference"],
                    "body": "Read the applicable approved source and provide that exact version."}
            if request is not None:
                args["request_id"] = request["message_id"]
            return act("sent:" + alias, "handoff_information", **args)
        if task == "handoff" or role == "provider":
            return done()
        if role == "implementer":
            if task in {"pair", "chain"} and self.config["communication"] == "requested" and "request" not in cache:
                return act("request", "request_information", route_id="basis", work_id=wid)
            for alias in ("data", "basis"):
                if "read:" + alias not in cache:
                    oid = obs["workspaces"]["TEAM"].get(alias)
                    if oid not in obs["objects"]:
                        return wait("Awaiting genuinely delivered evidence")
                    return read(alias)
                if wid + "::" + alias not in obs["adoptions"] and "adopt:" + alias not in cache:
                    return act("adopt:" + alias, "adopt", alias=alias,
                               **cache["read:" + alias]["reference"], policy="fixed", work_ids=[wid])
            if "written" not in cache:
                code = witness_code(defect="wrong_count" if control == "wrong_sql" else None)
                return act("written", "write_object", alias="code", data=code, work_id=wid,
                           dependencies=[cache["read:" + alias]["reference"] for alias in ("data", "basis")])
            if "built" not in cache:
                return act("built", "sql_build", work_id=wid, code_alias="code", output_alias="result", input_aliases=["data", "basis"])
            if "submitted" not in cache:
                return act("submitted", "submit", work_id=wid, artifacts=["code", "result"])
            return done()
        if role == "reviewer":
            # Useful evidence may be obtained while awaiting an actual submission.
            for alias in ("data", "audit_basis"):
                if "read:" + alias not in cache:
                    oid = obs["workspaces"]["TEAM"].get(alias)
                    if oid not in obs["objects"]:
                        return wait("Awaiting a real audit source delivery")
                    return read(alias)
            item = obs["work_items"][wid]
            sid = item.get("pending_submission_id") or item.get("latest_submission_id")
            if not sid:
                return wait("Awaiting a real fixed submission")
            if "inspect" not in cache:
                return act("inspect", "inspect_submission", work_id=wid, submission_id=sid)
            workspace = obs["workspaces"]["TEAM"]
            for alias in ("code", "result"):
                if "read:" + alias not in cache:
                    oid = workspace[alias]
                    return act("read:" + alias, "read_version", work_id=wid,
                               reference={"object_id": oid, "version_id": cache["inspect"]["artifact_versions"][oid]})
            if "judgment" in cache or control == "read_only":
                return done()
            audit = cache["read:audit_basis"]["data"]
            transactions = records(cache["read:data"]["data"]["tables"]["retail"])
            rows = records(cache["read:result"]["data"]["tables"]["metrics"])
            errors = []
            # This public-evidence witness computes separately from the domain checker.
            for index, row in enumerate(rows):
                eligible = [t for t in transactions if t["CustomerID"] == row["CustomerID"]
                            and audit["start_inclusive"] <= t["InvoiceDate"] < audit["end_exclusive"]
                            and Decimal(str(t["UnitPrice"])) > 0
                            and (audit["invoice_mode"] == "net_signed" or (not t["InvoiceNo"].upper().startswith("C") and t["Quantity"] > 0))]
                revenue = int(sum((Decimal(str(t["UnitPrice"])) * t["Quantity"] * 100 for t in eligible), Decimal(0)))
                count = len({t["InvoiceNo"] for t in eligible})
                for column, actual, expected in [(1, row["revenue_pence"], revenue), (2, row["invoice_count"], count)]:
                    if actual != expected:
                        errors.append((index, column))
            if not errors or control == "bad_approval":
                return act("judgment", "approve", work_id=wid, submission_id=sid)
            index, column = (0, 0) if control == "wrong_location" else errors[0]
            return act("judgment", "raise_issue", work_id=wid, submission_id=sid,
                       issue_key="public-evidence-disagreement", **cache["read:result"]["reference"],
                       locator=["tables", "metrics", "rows", index, column],
                       description="This actual result cell differs from the applicable independent business evidence.",
                       evidence=[cache["read:" + alias]["reference"] for alias in ("data", "audit_basis")])
        raise ValueError("Unsupported witness responsibility")


def run_case(case_id, output, *, communication="proactive", control=None, variant="v14"):
    output = Path(output)
    prepared = build_retail_case(case_id, output)
    captures, ports, policies = {}, {}, {}
    for role in prepared.active_roles:
        ports[role] = capture_port(WorkInterface(prepared.world.session(role, "TEAM"), role, variant=variant), captures.setdefault(role, []))
        policies[role] = PublicWitnessPolicy(role=role, task=prepared.case["task"],
                                           limit=prepared.case["role_decision_limits"][role],
                                           communication=communication, control=control)
    runtime = StaffRuntime(ports, policies, recorder=ExperienceRecorder())
    episode = output / "episode"
    begin_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), work_ids=["TEAM::build"],
                  scenario=prepared.scenario, policies=runtime.policy_identities)
    boundary = run_fragment(prepared, runtime)
    finish_episode(prepared.world, episode, experience=runtime.recorder.snapshot(), termination=boundary)
    reward = assess_retail_reward(episode, prepared.reward_spec)
    decisions = {role: runtime.roles[role]["memory"].get("decisions", 0) for role in runtime.labels}
    waits = {role: sum(event["kind"] == "policy_decision" and event.get("worker_id") == role
                      and event["payload"]["decision"]["kind"] == "wait" for event in runtime.recorder.events)
             for role in runtime.labels}
    report = {"case_id": case_id, "communication": communication, "control": control,
              "origin": "cpu_public_rule_witness_not_model", "source": code_identity(), "reward": reward,
              "boundary": boundary, "decisions_including_wait_done": decisions, "waits": waits,
              "role_limits": prepared.case["role_decision_limits"], "current_episode_excludes_prefix": True}
    (output / "capture.json").write_bytes(json_bytes(captures))
    (output / "runtime.json").write_bytes(json_bytes(runtime.snapshot()))
    (output / "reward.json").write_bytes(json_bytes(reward))
    (output / "report.json").write_bytes(json_bytes(report))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    cases = []
    for case in registry()["situations"]:
        modes = ["proactive", "requested"] if case["task"] in {"pair", "chain"} else ["proactive"]
        for mode in modes:
            row = run_case(case["case_id"], args.output / (case["case_id"] + "-" + mode), communication=mode)
            cases.append({"case_id": case["case_id"], "mode": mode, "reward": row["reward"]["reward"],
                          "decisions": row["decisions_including_wait_done"], "waits": row["waits"],
                          "limits": row["role_limits"], "passed": row["reward"]["reward"] == 1})
    controls = []
    for case_id, control, expected in [
        ("uci-development-f0-implement", "wrong_sql", 0.2),
        ("uci-development-f1-review", "bad_approval", 0.25),
        ("uci-development-f1-review", "wrong_location", 0.25),
        ("uci-development-f0-review", "no_actions", 0),
        ("uci-development-f0-pair", "wrong_sql", 0.2),
        ("uci-development-f0-chain", "wrong_sql", 0.2),
    ]:
        row = run_case(case_id, args.output / (case_id + "-" + control), control=control)
        controls.append({"case_id": case_id, "control": control, "reward": row["reward"]["reward"],
                         "expected": expected, "passed": row["reward"]["reward"] == expected})
    report = {"version": "retail-work-feasibility-v0.15", "model_execution": False,
              "cases": cases, "negative_controls": controls,
              "passed": all(row["passed"] for row in cases + controls),
              "scope": "CPU public-action witnesses through actual run_fragment. Establishes a feasible bounded route, not model ability or learning benefit."}
    (args.output / "report.json").write_bytes(json_bytes(report))
    print({"passed": report["passed"], "cases": len(cases), "controls": len(controls)})


if __name__ == "__main__":
    main()
