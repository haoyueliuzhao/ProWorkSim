"""Full-task generation entry for a new batch using the receipt-scoped OSA prompt."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_full_osa_v245_3 as previous
from proworksim.software_fixed_organization_clone_v131 import clone_function
from proworksim.software_osa_prompt_v245_4 import Execution, include_review_contract, wire


def evidence(outcome):
    return include_review_contract(previous.evidence(outcome), outcome["response"]["result"])


decision = clone_function(
    previous.decision, {**previous.decision.__globals__, "evidence": evidence, "wire": wire}
)


def generate(task, out, *, ledger_path, namespace):
    """Use an already admitted batch's ledger and slot namespace."""
    generate_episode = clone_function(
        previous.generate,
        {
            **previous.generate.__globals__,
            "decision": decision,
            "Execution": Execution,
            "NS": namespace,
            "AUTH": ledger_path,
        },
    )
    return generate_episode(task, out)


if __name__ == "__main__":
    import argparse
    from proworksim.storage import read_json

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--namespace", required=True)
    args = parser.parse_args()
    bank = read_json(previous.BANK)["rows"]
    task = next((r for r in bank if r["index"] == args.index), None)
    if task is None:
        parser.error(f"Task index {args.index} is absent from the bank")
    generate(task, args.output, ledger_path=args.ledger, namespace=args.namespace)
