"""Project test-receipt nodes and recurring, workspace-scoped failure incidents."""

from collections import defaultdict, deque
import re

from .software_anomaly_graph_v226 import TESTS, tested_nodes, version
from .storage import digest, json_bytes


def identity(value):
    return digest(json_bytes(value))


def failure_targets(result):
    failed, passed = tested_nodes(result)
    failed = {("test", target) for target in failed}
    overview = result.get("evidence_overview") or {}
    counts = result.get("counts") or {}
    if (
        result.get("passed") is False
        and not overview.get("nested_report_count")
        and not overview.get("error")
    ):
        for excerpt in (result.get("diagnostic_summary") or {}).get("excerpts", []):
            if excerpt.get("source") != "saved_visible_result.groups.output":
                continue
            text = excerpt["text"]
            if overview.get("framework") == "django" and (
                counts.get("errors") or counts.get("failed")
            ):
                # A traceback frame locates a test function, not an exception's root cause.
                frames = re.findall(
                    r'^  File "/testbed/([^"\n]+)", line \d+, in (test_\w+)\s*$', text, re.M
                )
                if frames:
                    path, function = frames[0]
                    failed.add(("test_function", path + "::" + function))
            if overview.get("framework") == "pytest" and counts.get("errors"):
                failed.update(
                    ("collection", p)
                    for p in re.findall(r"^_+ ERROR collecting (\S+\.py) _+$", text, re.M)
                )
    return sorted(failed), passed


class FailureProjectGraph:
    def __init__(self):
        self.nodes = {}
        self.reports = {}
        self.revision = 0
        self.streaks = defaultdict(lambda: deque(maxlen=3))

    def observe(self, ordinal, outcome, package):
        response = outcome.get("response") or {}
        tool = (outcome.get("decision") or {}).get("action")
        result = response.get("result") or {}
        actor = outcome.get("worker_id")
        command = response.get("command_id")
        source = version(result)
        if (
            tool not in TESTS
            or not actor
            or not command
            or command in self.reports
            or (result.get("report_event") or {}).get("operation_id", command) != command
            or not response.get("ok")
            or result.get("executed") is not True
            or result.get("command_executed") is False
            or not source
        ):
            return False
        selection = (result.get("selection_normalization") or {}).get("executed") or {}
        failed, passed = failure_targets(result)
        counts = result.get("counts") or {}
        if (
            not failed
            and result.get("passed") is False
            and selection
            and counts.get("tests_run")
            and (counts.get("failed") or counts.get("errors"))
            and not (result.get("evidence_overview") or {}).get("nested_report_count")
            and not (result.get("evidence_overview") or {}).get("error")
        ):
            failed = [("selection", identity(selection))]
        scope = [actor, package, tool, source[0]]
        receipt = dict(
            command_id=command,
            actor_id=actor,
            tool=tool,
            opportunity=ordinal,
            task_id=package,
            source_reference=result["source_reference"],
            files_sha256=result.get("files_sha256"),
            report_id=result.get("report_id"),
            selection=selection,
            counts=counts,
            passed=result.get("passed"),
            targets=failed,
        )
        self.reports[command] = receipt
        self.revision += 1
        streak = self.streaks[tuple(scope)]
        if not failed:
            streak.clear()
        else:
            streak.append(command)
        mixed = False
        if len(streak) == 3:
            case_sets = [set(self.reports[c]["targets"]) for c in streak]
            mixed = all(case_sets[i].isdisjoint(case_sets[j]) for i, j in ((0, 1), (0, 2), (1, 2)))
        for node in self.nodes.values():
            if node["scope"] != scope or node["state"] == "cleared":
                continue
            previous = self.reports[node["failures"][-1]]
            if (
                (node["target_kind"] == "mixed_targets" and result.get("passed") is True)
                or node["target"] in passed
                or (
                    result.get("passed") is True
                    and counts.get("tests_run", 0) > 0
                    and selection
                    and not any(counts.get(k) for k in ("skipped", "xfailed", "xpassed"))
                    and previous["selection"] == selection
                )
            ):
                node.update(
                    state="cleared", cleared_by=command, window=[], last_considered_content=None
                )
        for kind, target in [
            *failed,
            *([("mixed_targets", "consecutive public test failures")] if mixed else []),
        ]:
            key = identity([scope, kind, target])
            node = self.nodes.setdefault(
                key,
                dict(
                    id=key,
                    scope=scope,
                    package=package,
                    actor=actor,
                    target_kind=kind,
                    target=target,
                    state="observed",
                    failures=[],
                    window=[],
                    decisions=[],
                    last_considered_content=None,
                ),
            )
            if kind == "mixed_targets":
                for case in streak:
                    if case not in node["failures"]:
                        node["failures"].append(case)
                node.update(window=list(streak), state="needs_decision")
                continue
            node["failures"].append(command)
            node["window"].append(command)
            contents = [
                self.reports[c]["files_sha256"] or self.reports[c]["source_reference"]["version_id"]
                for c in node["window"]
            ]
            changed = len(set(contents)) >= 2
            repeated = len(contents) >= 3 and contents[-1] != node["last_considered_content"]
            if changed or repeated:
                node["state"] = "needs_decision"
            elif node["state"] == "cleared":
                node["state"] = "observed"
        return True

    def decision_evidence(self, incident):
        # Two different revisions, or three separate executions of the same revision.
        window = incident["window"]
        if incident["target_kind"] == "mixed_targets":
            return window[-3:]
        newest = self.reports[window[-1]]
        latest_content = newest["files_sha256"] or newest["source_reference"]["version_id"]
        other = next(
            (
                c
                for c in reversed(window[:-1])
                if (
                    self.reports[c]["files_sha256"]
                    or self.reports[c]["source_reference"]["version_id"]
                )
                != latest_content
            ),
            None,
        )
        return [other, window[-1]] if other else window[-3:]

    def decided(self, nodes, receipt):
        for node in nodes:
            self.streaks[tuple(node["scope"])].clear()
            current = self.reports[node["window"][-1]]
            node.update(
                state="reviewed",
                window=[],
                last_considered_content=current["files_sha256"]
                or current["source_reference"]["version_id"],
            )
            node["decisions"].append(receipt)
        self.revision += 1

    def snapshot(self):
        return dict(revision=self.revision, anomaly_nodes=self.nodes, test_receipts=self.reports)
