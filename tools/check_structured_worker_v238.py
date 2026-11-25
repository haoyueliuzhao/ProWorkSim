"""Native SDK integration control: a scripted, schema-validated proposal produces the promised handoff."""

import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_disposition_v232_5 as fixture
from run_obligation_scope_v237_1 import validate
from proworksim.software_structured_policy_v237 import options, change_plan
from proworksim.software_handoff_evidence_v232_6 import EvidenceFollowupExecution
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.storage import atomic_write, json_bytes


class Control(EvidenceFollowupExecution):
    def activate(self, node, observer, frozen, choice):
        key = choice["option"]
        op = frozen["options"][key]
        pkg = op["task"]
        work = frozen["graph"]["work"][pkg]
        row = dict(
            graph=frozen["graph"],
            targets=[pkg],
            work_status={pkg: {"completed": False, "authors": []}},
            options=frozen["options"],
            available_tokens=self.runtime.team_budget.snapshot()["available_tokens"],
            evidence={"E1": {"operation": "read_file"}},
        )
        if key not in options(row):
            return {"activated": False, "reason": "underfunded"}
        dims = change_plan(row, key)[1]
        d = {
            "assessment": {
                "situation": "UNKNOWN",
                "status": "uncertain",
                "stage": "diagnosis",
                "evidence": ["E1"],
            },
            "work": {
                "package": pkg,
                "obligations": ["diagnose_failure"],
                "later_checks": ["verify_integrated_version"],
            },
            "keep": {
                "owner": work["owner"],
                "verifier": work["reviewer"] or "none",
                "next_step": "investigate_failure",
                "product": "new_evidence",
                "verification": "inspect_evidence",
                "feasible": True,
                "progress": [],
                "blockers": ["E1"],
                "risk": "repeat_failure",
                "worker_turns": 2,
                "token_estimate": "unknown",
            },
            "alternative": {
                "option": key,
                "graph_dimensions": dims,
                "assignee": op["assignee"],
                "additional_product": "independent_diagnosis",
                "consumer": work["owner"],
                "handoff": "one",
                "verification": "inspect_evidence",
                "cost": "medium",
                "risk": "coordination",
            },
            "decision": {
                "result": "CHANGE",
                "basis": ["E1"],
                "next_step": "investigate_failure",
                "reconsider_on": "new_test_result",
                "missing_evidence": "none",
            },
        }
        body = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "function": {
                                    "name": "activate_organization",
                                    "arguments": json.dumps(d),
                                }
                            }
                        ]
                    }
                }
            ]
        }
        _, target = validate(row, body)
        record = super().activate(node, observer, frozen, {**choice, "option": target["option"]})
        assert record["after"] == target["graph"]
        return record


def main():
    os.environ.update(
        LITELLM_LOCAL_MODEL_COST_MAP="True",
        OPENHANDS_SUPPRESS_BANNER="1",
        HF_HUB_OFFLINE="1",
        PYTHON_DOTENV_DISABLED="1",
    )
    with tempfile.TemporaryDirectory(prefix="pws-structured-sdk-") as tmp:
        root = Path(tmp)
        os.environ["OH_PERSISTENCE_DIR"] = str(root / "sdk-settings")
        result = clone_function(
            fixture.exercise, {**fixture.exercise.__globals__, "DispositionExecution": Control}
        )(root, "adopt")
        assert result["sender_choices"] == ["DIAG"] and result["recipient"]["choice"] == "ADOPT"
        result.update(
            source="deterministic fixture, no real model choices",
            native_graph_matches_structured_target=True,
            task_score=None,
            official_task_pairs=0,
        )
        dest = (
            fixture.ROOT
            / "artifacts/software-benchmark-v238/structured-execution-r1/sdk-control.json"
        )
        dest.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(dest, json_bytes(result))


if __name__ == "__main__":
    main()
