"""Run finite program workers against the already loaded example world.

The adapter binds public sessions once. Workers receive only tools/observe/call;
all source identities are discovered from public observations. This smoke demo
loads no hidden truth and does not measure professional or model capability.
"""

import argparse
import json
from pathlib import Path

from proworksim.workers.reconciliation import ReconciliationWorker
from proworksim.workers.research_review import PublicReportWorker
from proworksim.world_core import WorldCore


def public_port(session):
    class Port:
        __slots__ = ()

        def tools(self):
            return session.tools()

        def observe(self):
            return session.observe()

        def call(self, action, **arguments):
            return session.call(action, **arguments)

    return Port()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("world", type=Path)
    parser.add_argument("--ports", type=Path, default=Path(__file__).with_name("ports.json"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Use a new transcript output path")
    if (
        args.world.resolve() == args.output.resolve()
        or args.world.resolve() in args.output.resolve().parents
    ):
        raise ValueError("Transcript must be outside the world directory")
    world = WorldCore(args.world)
    bindings = json.loads(args.ports.read_text())
    ports = {
        label: public_port(world.session(value["actor"], value["project"]))
        for label, value in bindings.items()
    }
    outcomes = {}
    if "finance_worker" in ports:
        worker = ReconciliationWorker(ports["finance_worker"])
        outcomes["finance"] = {"outcome": worker.run(), "transcript": worker.transcript}
    if "report_author" in ports:
        author = PublicReportWorker(ports["report_author"])
        observation = author.observe()
        work_id, work = next(
            (wid, item)
            for wid, item in observation["work_items"].items()
            if any(
                c["kind"] == "research_report"
                for c in item["deliverable_contract"]["content_checks"]
            )
        )
        spec = next(
            c
            for c in work["deliverable_contract"]["content_checks"]
            if c["kind"] == "research_report"
        )
        for source in spec["sources"]:
            alias = source["alias"]
            object_id = observation["workspaces"][work["project_id"]][alias]
            # This example package explicitly fixes the initial source version.
            version = work["requirements"]["input_version"]
            author.call(
                "adopt",
                alias=alias,
                object_id=object_id,
                version_id=version,
                policy="fixed",
                work_ids=[work_id],
            )
        data, dependencies = author.prepare(work_id)
        submission = author.deliver(work_id, data, dependencies)
        reviewer = PublicReportWorker(ports["report_reviewer"])
        findings = reviewer.review(work_id, submission["submission_id"])
        approval = None
        if not findings:
            approval = reviewer.call(
                "approve", work_id=work_id, submission_id=submission["submission_id"]
            )
        outcomes["report"] = {
            "work_id": work_id,
            "submission": submission,
            "findings": findings,
            "approval": approval,
            "author_transcript": author.transcript,
            "reviewer_transcript": reviewer.transcript,
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(outcomes, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "templates": list(outcomes)}))


if __name__ == "__main__":
    main()
