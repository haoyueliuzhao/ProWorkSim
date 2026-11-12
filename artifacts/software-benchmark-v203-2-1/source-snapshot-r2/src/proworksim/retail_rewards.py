"""UCI work outcomes from immutable evidence and independent Decimal content checks.

The event settlement engine is shared; the business domain and frozen terminal
contract are retail-specific. Original UCI fields are never relabeled toy fields.
"""
import copy
from pathlib import Path

from .domains.retail_work import evaluate_check, expected_metrics
from .episode import assess_historical_episode
from .online_rewards import _Evidence, _ref, _rows, _reward_ledger
from .storage import digest, read_json
from .templates.retail_work import REWARD_VERSION, TERMS


def _validate(spec):
    if not isinstance(spec, dict) or spec.get('version') != REWARD_VERSION:
        raise ValueError('Frozen retail reward specification required')
    if spec.get('task') not in TERMS or [(t['term_id'], t['weight']) for t in spec['terms']] != [(n, w) for n, w, _ in TERMS[spec['task']]]:
        raise ValueError('Changed retail reward terms')
    if spec.get('preparation_credit') is not False:
        raise ValueError('Preparation is not current actor work')
    return copy.deepcopy(spec)


class RetailEvidence(_Evidence):
    def check_document(self, data):
        check = self.item['deliverable_contract']['content_checks'][0]
        return evaluate_check(check, data, lambda alias: self.document(_ref(data['sources'][alias])))['passed']

    def fixed_submission(self):
        fixed = super().fixed_submission()
        if fixed and self.spec['task'] == 'pair':
            sub = self.item['submissions'][-1]
            if not self.read_inputs(fixed['action_sequence'], sub):
                return None
        return fixed

    def wrong_location(self, sub, issue, reads):
        result_oid = self.aliases['result']
        if _ref(issue.get('target')) != (result_oid, sub['artifact_versions'].get(result_oid)):
            return False
        locator = issue.get('locator')
        if not isinstance(locator, list) or len(locator) not in {4, 5} or locator[:3] != ['tables', 'metrics', 'rows'] or type(locator[3]) is not int:
            return False
        if not {tuple(reads['audit_reference']), tuple(reads['data_reference'])} <= {_ref(v) for v in issue.get('evidence', [])}:
            return False
        result = self.document((result_oid, sub['artifact_versions'][result_oid]))['tables']['metrics']
        index = locator[3]
        if not 0 <= index < len(result['rows']):
            return False
        actual = _rows(result)[index]
        data = self.document(tuple(reads['data_reference']))['tables']
        audit = self.document(tuple(reads['audit_reference']))
        expected = expected_metrics(_rows(data['retail']), [{'CustomerID': actual.get('CustomerID')}], audit)[0]
        mismatch = {name for name in expected if actual.get(name) != expected[name]}
        if len(locator) == 5:
            col = locator[4]
            if type(col) is not int or not 0 <= col < len(result['columns']):
                return False
            mismatch &= {result['columns'][col]['name']}
        return bool(mismatch)


def assess_retail_reward(episode, spec):
    """Read only a closed episode and its predeclared scope; return nullable reward."""
    spec = _validate(spec)
    root = Path(episode)
    if root.name == "manifest.json":
        root = root.parent
    result = {
        "version": spec["version"],
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
        evidence = RetailEvidence(root, spec, assessment)
        declared = evidence.start["work_items"][spec["work_id"]]["requirements"].get("online_scope")
        if declared != spec:
            raise ValueError("World public scope differs from frozen reward declaration")
        facts = {}
        if spec["task"] == "handoff":
            reads = [
                e
                for e in evidence.reads
                if e["worker_id"] == evidence.basis_provider
                and evidence.applicable_basis(
                    _ref(e["payload"]["response"]["result"].get("reference"))
                )
            ]
            facts["read_applicable_basis"] = (
                {"action_sequence": reads[0]["sequence"]} if reads else None
            )
        if spec["task"] in {"implement", "pair"}:
            facts["read_exact_inputs"] = (
                {"read_in_current_episode": True} if evidence.read_inputs() else None
            )
            facts["correct_actual_build"] = evidence.correct_build()
        if spec["task"] in {"pair", "chain"}:
            facts["deliver_applicable_basis"] = evidence.handoff()
        if spec["task"] in {"implement", "pair", "chain"}:
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
        elif task in {"implement", "pair"}:
            fixed = facts["correct_fixed_submission"]
            sub = evidence.item["submissions"][-1] if fixed else None
            basis_ok = evidence.read_inputs(
                fixed["action_sequence"] if fixed else float("inf"), sub
            )
            delivery_ok = bool(facts["correct_actual_build"] and fixed)
            if task == "pair":
                basis_ok = basis_ok and bool(facts["deliver_applicable_basis"])
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
        if spec["version"] == REWARD_VERSION:
            result["ledger"] = _reward_ledger(evidence, result)
    except (KeyError, OSError, TypeError, ValueError) as error:
        result["exclusions"].append({"type": type(error).__name__, "reason": str(error)})
        result.update(eligible=False, reward=None, completed=False)
        result.pop("ledger", None)
    return result
