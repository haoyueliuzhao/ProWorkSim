"""Scoped online work outcomes from immutable episodes, never action counts.

Partial real outcomes can reward basic RL without V=true or method support.
Preparation is inherited state, not current actor activity. No evaluator result
is delivered to a worker as a tool answer or used to rewrite the episode.
"""

import copy
import json
from pathlib import Path

from .domains.decision_team import evaluate_check
from .episode import assess_historical_episode
from .evaluation import evaluate_submission
from .storage import Store, digest, read_json
from .templates.online_work import REWARD_VERSION, TERMS

READ_OPERATIONS = {"read_object", "read_alias", "read_version"}


def _ref(value):
    if not isinstance(value, dict):
        return None
    oid, vid = value.get("object_id", value.get("artifact_id")), value.get("version_id")
    return (oid, vid) if isinstance(oid, str) and isinstance(vid, str) else None


def _rows(table):
    return [dict(zip([c["name"] for c in table["columns"]], row)) for row in table["rows"]]


def _validate(spec):
    if not isinstance(spec, dict) or spec.get("version") != REWARD_VERSION:
        raise ValueError("A frozen online reward specification is required")
    task = spec.get("task")
    if task not in TERMS or [(t["term_id"], t["weight"]) for t in spec["terms"]] != [
        (name, weight) for name, weight, _ in TERMS[task]
    ]:
        raise ValueError("Unknown or changed scoped reward terms")
    if spec.get("preparation_credit") is not False:
        raise ValueError("Preparation is never current actor credit")
    return copy.deepcopy(spec)


class _Evidence:
    def __init__(self, root, spec, assessment):
        self.root, self.spec, self.assessment = root, spec, assessment
        self.manifest = read_json(root / "manifest.json")
        self.start = read_json(root / "start/control/state.json")
        self.state = read_json(root / "end/control/state.json")
        self.store = Store(root / "end")
        self.wid, self.pid = spec["work_id"], spec["project_id"]
        self.item = self.state["work_items"][self.wid]
        self.aliases = self.state["workspaces"][self.pid]
        self.events = read_json(root / self.manifest["experience"]["path"])["events"][
            self.manifest["experience"]["start"] : self.manifest["experience"]["end"]
        ]
        self.calls = [e for e in self.events if e["kind"] == "tool_call"]
        self.successful = []
        for e in self.calls:
            response = e["payload"].get("response", {})
            commit = self.state["operation_commits"].get(response.get("command_id"))
            if (
                commit is None
                or commit.get("bound_actor") != e.get("worker_id")
                or commit.get("public_result") != response
                or e.get("worker_id") not in spec["active_roles"]
            ):
                raise ValueError("Current actor event differs from its actual world receipt")
            if (
                e["payload"]["action"] in {"read_alias", "read_version"}
                and commit.get("receipt", {}).get("contract") != e["payload"]["action"]
            ):
                raise ValueError(
                    "Canonical read operation differs from its actual receipt contract"
                )
            # A replayed idempotent receipt from preparation is not a new
            # action or a new read by the current actor episode.
            if (
                response.get("ok")
                and response.get("command_id") not in self.start["operation_commits"]
            ):
                self.successful.append(e)
        self.reads = [e for e in self.successful if e["payload"]["action"] in READ_OPERATIONS]
        self.cache = {}

    def document(self, reference):
        if reference is None:
            raise ValueError("Missing exact reference")
        if reference not in self.cache:
            oid, vid = reference
            artifact = self.state["artifacts"][oid]
            raw = self.store.version_path(artifact, vid).read_bytes()
            if digest(raw) != artifact["versions"][vid]["sha256"]:
                raise ValueError("Changed immutable reward evidence")
            self.cache[reference] = json.loads(raw)
        return self.cache[reference]

    def read_before(self, actor, reference, before=float("inf")):
        return [
            e
            for e in self.reads
            if e["worker_id"] == actor
            and e["sequence"] < before
            and _ref(e["payload"]["response"]["result"].get("reference")) == reference
            and self.presented_to_consumer(e, before)
        ]

    def presented_to_consumer(self, evidence, before):
        """A saved read is not automatically in a later model's actual input."""
        if before == float("inf"):
            return True
        consumer = next((e for e in self.calls if e["sequence"] == before), None)
        if consumer is None:
            raise ValueError("Missing exact consuming action for evidence")
        role = consumer["worker_id"]
        call_id = consumer["payload"].get("model_call_id")
        policy = self.manifest.get("policies", {}).get(role, {})
        is_model = "ModelPolicy" in str(policy.get("implementation", "")) or any(
            e.get("worker_id") == role and e["kind"] == "model_call" for e in self.events
        )
        if not is_model and call_id is None:
            return True  # Explicit rule witnesses have actual direct returns.
        if call_id is None or not evidence["payload"].get("model_call_id"):
            raise ValueError("Model evidence lacks an actual call association")
        attempts = [
            e["payload"]
            for e in self.events
            if e.get("worker_id") == role
            and e["kind"] == "model_attempt"
            and e["payload"].get("call_id") == call_id
            and e["payload"].get("stage") == "finished"
            and e["payload"].get("status") == "success"
        ]
        messages = [
            e["payload"]["message"]
            for e in self.events
            if e.get("worker_id") == role
            and e["kind"] == "model_tool_result"
            and e["sequence"] < before
            and e["payload"].get("call_id") == evidence["payload"]["model_call_id"]
        ]
        if len(attempts) != 1 or not messages:
            raise ValueError("Model's actual consuming request or evidence return is unavailable")
        return any(message in attempts[0]["request"]["messages"] for message in messages)

    def applicable_basis(self, reference):
        if reference is None or reference[0] != self.aliases["basis"]:
            return False
        meta = _rows(self.document(reference)["tables"]["basis_meta"])
        return (
            len(meta) == 1
            and meta[0]["period"] == self.spec["period"]
            and meta[0]["edition"] == "approved"
        )

    def applicable_audit(self, reference):
        if reference is None or reference[0] != self.aliases["audit_basis"]:
            return False
        doc = self.document(reference)
        return doc.get("period") == self.spec["period"] and doc.get("edition") == "approved"

    def adopted_refs(self, submission=None):
        bindings = (
            self.state["adoptions"]
            if submission is None
            else submission.get("adoption_snapshot", {})
        )
        selected = {
            b["alias"]: (b["object_id"], b["version_id"])
            for b in bindings.values()
            if b.get("work_id") == self.wid
            and b.get("requirement_version") == self.item["requirement_version"]
        }
        return {alias: selected.get(alias) for alias in ("data", "basis")}

    def read_inputs(self, before=float("inf"), submission=None):
        refs = self.adopted_refs(submission)
        return bool(
            refs["data"]
            and refs["data"][0] == self.aliases["data"]
            and self.applicable_basis(refs["basis"])
            and all(self.read_before("implementer", value, before) for value in refs.values())
        )

    def check_document(self, data):
        spec = self.item["deliverable_contract"]["content_checks"][0]
        return evaluate_check(
            spec, data, lambda alias: self.document(_ref(data["sources"][alias]))
        )["passed"]

    def handoff(self):
        for e in self.successful:
            if e["worker_id"] != "provider" or e["payload"]["action"] != "handoff_information":
                continue
            hid = e["payload"]["response"]["result"].get("handoff_id")
            handoff = self.state["handoffs"].get(hid, {})
            reference = _ref(handoff.get("reference"))
            if (
                hid not in self.start.get("handoffs", {})
                and handoff.get("route_id") == "basis"
                and handoff.get("sender") == "provider"
                and handoff.get("recipients") == ["implementer"]
                and handoff.get("work_item_id") == self.wid
                and handoff.get("requirement_version") == self.item["requirement_version"]
                and handoff.get("response_status") == "delivered"
                and handoff.get("status") == "delivered"
                and self.applicable_basis(reference)
                and self.read_before("provider", reference, e["sequence"])
                and any(
                    event.get("event_id") == handoff.get("event_id")
                    and event.get("outcome") == "applied"
                    for event in self.state["event_history"]
                )
            ):
                return {
                    "handoff_id": hid,
                    "reference": list(reference),
                    "action_sequence": e["sequence"],
                }
        return None

    def correct_build(self):
        for e in self.successful:
            if e["worker_id"] != "implementer" or e["payload"]["action"] != "sql_build":
                continue
            response = e["payload"]["response"]["result"]
            reference = _ref(response.get("reference"))
            if (
                not reference
                or reference[0] != self.aliases["result"]
                or response.get("execution_status") != "success"
            ):
                continue
            version = self.state["artifacts"][reference[0]]["versions"][reference[1]]
            provenance = version.get("execution_provenance", {})
            doc = self.document(reference)
            if (
                provenance.get("kind") == "sql_build"
                and provenance.get("work_id") == self.wid
                and provenance.get("requirement_version") == self.item["requirement_version"]
                and provenance.get("status") == "success"
                and self.applicable_basis(_ref(doc.get("sources", {}).get("basis")))
                and all(
                    _ref(doc.get("sources", {}).get(alias)) == self.adopted_refs()[alias]
                    for alias in ("data", "basis")
                )
                and self.check_document(doc)
            ):
                return {"reference": list(reference), "action_sequence": e["sequence"]}
        return None

    def fixed_submission(self):
        submissions = self.item["submissions"]
        if not submissions:
            return None
        sub = submissions[-1]
        if (sub.get("review") or {}).get("decision") == "withdrawn":
            return None
        prior = {s["submission_id"] for s in self.start["work_items"][self.wid]["submissions"]}
        calls = [
            e
            for e in self.successful
            if e["worker_id"] == "implementer"
            and e["payload"]["action"] == "submit"
            and e["payload"]["response"]["result"].get("submission_id") == sub["submission_id"]
        ]
        if sub["submission_id"] in prior or not calls:
            return None
        outcome = evaluate_submission(self.store, self.state, self.item, sub)
        if outcome["status"] not in {"pass", "content_failure", "structure_failure", "unassessed"}:
            raise ValueError("Fixed submission could not be independently evaluated")
        if not outcome.get("passed"):
            return None
        if self.spec["task"] == "chain" and not self.read_inputs(calls[-1]["sequence"], sub):
            return None
        return {"submission_id": sub["submission_id"], "action_sequence": calls[-1]["sequence"]}

    def original_review_submission(self):
        if self.spec["task"] == "review":
            initial = self.start["work_items"][self.wid]["submissions"]
            if not initial or initial[-1].get("review") is not None:
                raise ValueError("Review scope requires an actual original pending submission")
            sid = initial[-1]["submission_id"]
            return next(s for s in self.item["submissions"] if s["submission_id"] == sid)
        return self.item["submissions"][-1] if self.item["submissions"] else None

    def review_reads(self, sub, before=float("inf")):
        if sub is None:
            return None
        inspect = [
            e
            for e in self.successful
            if e["worker_id"] == "reviewer"
            and e["payload"]["action"] == "inspect_submission"
            and e["sequence"] < before
            and e["payload"]["arguments"].get("submission_id") == sub["submission_id"]
            and self.presented_to_consumer(e, before)
        ]
        if not inspect or not all(
            self.read_before("reviewer", (oid, vid), before)
            for oid, vid in sub["artifact_versions"].items()
        ):
            return None
        refs = self.adopted_refs(sub)
        if refs["data"] is None or not self.read_before("reviewer", refs["data"], before):
            return None
        audits = [
            (e, _ref(e["payload"]["response"]["result"].get("reference")))
            for e in self.reads
            if e["worker_id"] == "reviewer" and e["sequence"] < before
        ]
        for event, audit_ref in audits:
            if self.applicable_audit(audit_ref) and self.presented_to_consumer(event, before):
                return {
                    "submission_id": sub["submission_id"],
                    "audit_reference": list(audit_ref),
                    "data_reference": list(refs["data"]),
                    "inspect_sequence": inspect[-1]["sequence"],
                    "audit_read_sequence": event["sequence"],
                }
        return None

    def first_review_judgment(self, sub):
        if sub is None:
            return float("inf")
        return min(
            (
                e["sequence"]
                for e in self.successful
                if e["worker_id"] == "reviewer"
                and e["payload"]["action"] in {"approve", "raise_issue"}
                and e["payload"]["arguments"].get("submission_id") == sub["submission_id"]
            ),
            default=float("inf"),
        )

    def wrong_location(self, sub, issue, reads):
        result_oid = self.aliases["result"]
        if _ref(issue.get("target")) != (result_oid, sub["artifact_versions"].get(result_oid)):
            return False
        locator = issue.get("locator")
        if (
            not isinstance(locator, list)
            or len(locator) not in {4, 5}
            or locator[:3] != ["tables", "metrics", "rows"]
            or type(locator[3]) is not int
        ):
            return False
        evidence_refs = {_ref(value) for value in issue.get("evidence", [])}
        if not {tuple(reads["audit_reference"]), tuple(reads["data_reference"])} <= evidence_refs:
            return False
        result = self.document((result_oid, sub["artifact_versions"][result_oid]))["tables"][
            "metrics"
        ]
        index = locator[3]
        if not 0 <= index < len(result["rows"]):
            return False
        actual = _rows(result)[index]
        data = self.document(tuple(reads["data_reference"]))["tables"]
        audit = self.document(tuple(reads["audit_reference"]))
        eligible = [
            r
            for r in _rows(data["transactions"])
            if r["customer_id"] == actual.get("customer_id")
            and r["period"] == audit["period"]
            and r["status"] in audit["allowed_statuses"]
        ]
        expected = {
            "customer_id": actual.get("customer_id"),
            "revenue_cents": sum(r["amount"] * audit["amount_factor"] for r in eligible),
            "order_count": len({r["order_id"] for r in eligible}),
        }
        mismatch = {name for name in expected if actual.get(name) != expected[name]}
        if len(locator) == 5:
            col = locator[4]
            if type(col) is not int or not 0 <= col < len(result["columns"]):
                return False
            mismatch &= {result["columns"][col]["name"]}
        return bool(mismatch)

    def review_decision(self):
        sub = self.original_review_submission()
        if sub is None:
            return None
        quality = evaluate_submission(self.store, self.state, self.item, sub)
        if quality["status"] not in {"pass", "content_failure", "structure_failure", "unassessed"}:
            raise ValueError("Review target could not be independently evaluated")
        approvals = [
            e
            for e in self.successful
            if e["worker_id"] == "reviewer"
            and e["payload"]["action"] == "approve"
            and e["payload"]["arguments"].get("submission_id") == sub["submission_id"]
        ]
        if quality.get("passed"):
            # Later reads/repeated approval cannot erase an earlier real
            # approval that lacked the declared evidence.
            if any(not self.review_reads(sub, e["sequence"]) for e in approvals):
                return None
            for e in approvals:
                reads = self.review_reads(sub, e["sequence"])
                if reads:
                    return {
                        **reads,
                        "decision": "supported_approval",
                        "action_sequence": e["sequence"],
                    }
            return None
        if self.spec["task"] != "review" or approvals:
            return None
        for e in self.successful:
            if e["worker_id"] != "reviewer" or e["payload"]["action"] != "raise_issue":
                continue
            issue_id = e["payload"]["response"]["result"].get("issue_id")
            issue = self.state["issues"].get(issue_id, {})
            reads = self.review_reads(sub, e["sequence"])
            if (
                reads
                and issue_id not in self.start.get("issues", {})
                and issue.get("submission_id") == sub["submission_id"]
                and issue.get("blocking") is True
                and issue.get("active_at_creation") is True
                and self.wrong_location(sub, issue, reads)
            ):
                return {
                    **reads,
                    "decision": "supported_located_issue",
                    "issue_id": issue_id,
                    "action_sequence": e["sequence"],
                }
        return None


def assess_online_reward(episode, spec):
    """Read only a closed episode and its predeclared scope; return nullable reward."""
    spec = _validate(spec)
    root = Path(episode)
    if root.name == "manifest.json":
        root = root.parent
    result = {
        "version": REWARD_VERSION,
        "reward_id": spec["reward_id"],
        "scope": spec["task"],
        "spec": spec,
        "eligible": False,
        "reward": None,
        "completed": False,
        "components": [],
        "exclusions": [],
        "work_components": {
            dimension: {
                "value": None,
                "evidence": {"reason": "Scoped historical evidence not yet established"},
            }
            for dimension in ("basis", "delivery")
        },
    }
    try:
        manifest = read_json(root / "manifest.json")
        result.update(
            episode_id=manifest.get("episode_id"),
            manifest_sha256=digest((root / "manifest.json").read_bytes()),
        )
        if (
            manifest.get("status") != "closed"
            or manifest.get("scenario", {}).get("variation", {}).get("online_reward") != spec
        ):
            raise ValueError("Reward must match the scope frozen before current actor actions")
        assessment = assess_historical_episode(root)
        if assessment.get("assessment_execution", {}).get("status") != "complete":
            raise ValueError("Historical evidence or independent evaluator unavailable")
        if any(
            event.get("status") in {"model_service_error", "environment_error"}
            or event.get("payload", {}).get("status") == "model_service_error"
            or event.get("kind")
            in {"interface_exception", "interface_error", "model_service_error"}
            for event in assessment.get("runtime_problems", {}).get("events", [])
        ):
            raise ValueError(
                "Unmeasured service/environment failure prevents trusted scoped return"
            )
        evidence = _Evidence(root, spec, assessment)
        declared = evidence.start["work_items"][spec["work_id"]]["requirements"].get("online_scope")
        if declared != spec:
            raise ValueError("World public scope differs from frozen reward declaration")
        facts = {}
        if spec["task"] == "handoff":
            reads = [
                e
                for e in evidence.reads
                if e["worker_id"] == "provider"
                and evidence.applicable_basis(
                    _ref(e["payload"]["response"]["result"].get("reference"))
                )
            ]
            facts["read_applicable_basis"] = (
                {"action_sequence": reads[0]["sequence"]} if reads else None
            )
        if spec["task"] == "implement":
            facts["read_exact_inputs"] = (
                {"read_in_current_episode": True} if evidence.read_inputs() else None
            )
            facts["correct_actual_build"] = evidence.correct_build()
        if spec["task"] in {"handoff", "chain"}:
            facts["deliver_applicable_basis"] = evidence.handoff()
        if spec["task"] in {"implement", "chain"}:
            facts["correct_fixed_submission"] = evidence.fixed_submission()
        if spec["task"] == "review":
            original = evidence.original_review_submission()
            facts["read_review_basis"] = evidence.review_reads(
                original, evidence.first_review_judgment(original)
            )
        if spec["task"] in {"review", "chain"}:
            facts["correct_review_decision"] = evidence.review_decision()
        # Scope-specific work validity is evaluated from exact action/evidence
        # predicates, not from the scalar return or full-team acceptance.
        task = spec["task"]
        if task == "handoff":
            basis_ok, delivery_ok = (
                bool(facts["read_applicable_basis"]),
                bool(facts["deliver_applicable_basis"]),
            )
        elif task == "implement":
            fixed = facts["correct_fixed_submission"]
            sub = evidence.item["submissions"][-1] if fixed else None
            basis_ok = evidence.read_inputs(
                fixed["action_sequence"] if fixed else float("inf"), sub
            )
            delivery_ok = bool(facts["correct_actual_build"] and fixed)
        elif task == "review":
            decision = facts["correct_review_decision"]
            original = evidence.original_review_submission()
            basis_ok = bool(
                evidence.review_reads(
                    original,
                    decision["action_sequence"]
                    if decision
                    else evidence.first_review_judgment(original),
                )
            )
            delivery_ok = bool(decision)
        else:
            basis_ok = bool(
                facts["deliver_applicable_basis"]
                and facts["correct_fixed_submission"]
                and facts["correct_review_decision"]
            )
            delivery_ok = bool(
                facts["correct_fixed_submission"] and facts["correct_review_decision"]
            )
        result["work_components"] = {
            dimension: {
                "value": value,
                "evidence": {
                    "task": task,
                    "work_id": spec["work_id"],
                    "predicate_facts": copy.deepcopy(facts),
                    "episode_manifest_sha256": result["manifest_sha256"],
                },
                "scope": "Declared short-work responsibility; independent of scalar reward and method support",
            }
            for dimension, value in [("basis", basis_ok), ("delivery", delivery_ok)]
        }
        # Chain approval alone must never imply its whole-work success.
        result["components"] = [
            {
                **term,
                "achieved": facts.get(term["term_id"]) is not None,
                "score": term["weight"] if facts.get(term["term_id"]) else 0.0,
                "evidence": facts.get(term["term_id"]),
            }
            for term in spec["terms"]
        ]
        result.update(
            eligible=True,
            reward=round(sum(c["score"] for c in result["components"]), 10),
            completed=all(c["achieved"] for c in result["components"]),
            episode_id=manifest["episode_id"],
            manifest_sha256=digest((root / "manifest.json").read_bytes()),
            preparation_credited=False,
            requires_full_team_validity=False,
            interpretation="Scoped finite environment outcomes; not method-support eligibility or a full-team success claim for short fragments.",
        )
    except (KeyError, OSError, TypeError, ValueError) as error:
        result["exclusions"].append({"type": type(error).__name__, "reason": str(error)})
    return result
