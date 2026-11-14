"""Finite program authors/reviewers with only tools/observe/call ports.

No domain evaluator, WorldCore state, filesystem, hidden expected answer or direct
mutation is available to these strategies. The harness may separately measure
against literal truths. Rejections retain actual returns and are not all called
implementation errors.
"""

import copy
import json
import math


class ToolRejected(RuntimeError):
    def __init__(self, action, response):
        self.action, self.response = action, copy.deepcopy(response)
        super().__init__(f"Tool rejected {action}: {response}")


def _field(data, path):
    for key in path:
        data = data[key]
    return data


def _fact(claim, source):
    value = _field(source, claim["value_path"])
    if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
        raise ValueError("Unsupported source numeric value")
    period = _field(source, claim["period_path"])
    trend = "unknown" if value is None else "unassessed"
    if value is not None and "previous_path" in claim:
        prior = _field(source, claim["previous_path"])
        trend = (
            "unknown"
            if prior is None
            else "up"
            if value > prior
            else "down"
            if value < prior
            else "flat"
        )
    return {
        "claim_id": claim["claim_id"],
        "value": value,
        "period": period,
        "trend": trend,
        "source_alias": claim["source_alias"],
        "source_path": claim["value_path"],
        "status": "unresolved" if value is None else "supported",
    }


def _sentence(claim, fact, style):
    value = "unknown" if fact["value"] is None else str(fact["value"])
    citation = fact["source_alias"] + ":" + ".".join(fact["source_path"])
    if style == "prose":
        return f"{claim['label']} in {fact['period']}: {value}; trend {fact['trend']}; source {citation}."
    if style == "compact":
        return f"{fact['period']}: {claim['label']} = {value} ({fact['trend']}) [{citation}]."
    raise ValueError("Unsupported public sentence style")


class PublicReportWorker:
    def __init__(self, port):
        self._port = port
        self.transcript = []
        self.transcript.append({"kind": "tools", "result": copy.deepcopy(port.tools())})

    def observe(self):
        result = self._port.observe()
        self.transcript.append({"kind": "observe", "result": copy.deepcopy(result)})
        return result

    def call(self, action, **arguments):
        result = self._port.call(action, **arguments)
        self.transcript.append(
            {
                "kind": "call",
                "action": action,
                "arguments": copy.deepcopy(arguments),
                "result": copy.deepcopy(result),
            }
        )
        if not result.get("ok"):
            raise ToolRejected(action, result)
        return result["result"]

    def spec(self, work_id):
        work = self.observe()["work_items"][work_id]
        specs = [
            s
            for s in work["deliverable_contract"]["content_checks"]
            if s["kind"] == "research_report"
        ]
        if len(specs) != 1:
            raise ValueError("Strategy supports exactly one public finite report contract")
        return specs[0]

    def source_data(self, work_id, spec, snapshot=None):
        observation = self.observe()
        refs, sources = {}, {}
        for item in spec["sources"]:
            alias = item["alias"]
            binding = (snapshot or observation["adoptions"])[work_id + "::" + alias]
            oid = binding.get("object_id")
            vid = binding.get("adopted_version", binding.get("version_id"))
            result = self.call("read_object", object_id=oid, version_id=vid, work_id=work_id)
            refs[alias] = {
                "object_id": result["reference"]["artifact_id"],
                "version_id": result["reference"]["version_id"],
            }
            sources[alias] = result["data"]
        return refs, sources

    def prepare(
        self, work_id, *, report_alias="report", style="prose", fix_claims=None, defects=None
    ):
        """Read actual inputs; local repair preserves every unselected section."""
        spec = self.spec(work_id)
        refs, sources = self.source_data(work_id, spec)
        prior = self.call("read_object", alias=report_alias, work_id=work_id)["data"]
        result = copy.deepcopy(prior)
        report = _field(result, spec["path"])
        sections = report["sections"]
        positions = {section["section_id"]: index for index, section in enumerate(sections)}
        for claim in spec["claims"]:
            if fix_claims is not None and claim["claim_id"] not in fix_claims:
                continue
            fact = _fact(claim, sources[claim["source_alias"]])
            section = {
                "section_id": claim["section_id"],
                "body": _sentence(claim, fact, style),
                "claims": [fact],
            }
            # Explicit experimental policy error injection, never evaluator feedback.
            defect = (defects or {}).get(claim["claim_id"])
            if defect == "body_number":
                section["body"] = section["body"].replace(": " + str(fact["value"]) + ";", ": 999;")
            elif defect == "body_period":
                section["body"] = section["body"].replace(fact["period"], "1999FY")
            elif defect == "body_source":
                section["body"] = section["body"].replace(
                    fact["source_alias"] + ":", "wrong-source:"
                )
            elif defect == "body_trend":
                section["body"] = section["body"].replace("trend " + fact["trend"], "trend flat")
            if section["section_id"] in positions:
                sections[positions[section["section_id"]]] = section
            else:
                sections.append(section)
        result["sources"] = refs
        return result, list(refs.values())

    def deliver(self, work_id, data, dependencies, *, report_alias="report", split=False):
        if split:
            self.call(
                "write_object",
                alias=report_alias,
                data={"report": data["report"]},
                dependencies=dependencies,
                work_id=work_id,
            )
            obs = self.observe()
            pid = obs["work_items"][work_id]["project_id"]
            exists = "citations" in obs["workspaces"][pid]
            args = {
                "alias": "citations",
                "data": {"sources": data["sources"]},
                "dependencies": dependencies,
                "work_id": work_id,
            }
            if not exists:
                args.update(filename="citations.json", kind="json", deliverable_role="report")
            self.call("write_object" if exists else "create_object", **args)
            aliases = [report_alias, "citations"]
        else:
            self.call(
                "write_object",
                alias=report_alias,
                data=data,
                dependencies=dependencies,
                work_id=work_id,
            )
            aliases = [report_alias]
        return self.call("submit", work_id=work_id, artifacts=aliases)

    def read_submission(self, work_id, submission_id):
        submission = self.call("inspect_submission", work_id=work_id, submission_id=submission_id)
        documents, refs = {}, {}
        for oid, vid in submission["artifact_versions"].items():
            read = self.call("read_object", object_id=oid, version_id=vid, work_id=work_id)
            for key, value in read["data"].items():
                if key in documents and documents[key] != value:
                    raise ValueError("Ambiguous submitted top-level fields")
                documents[key] = value
                refs[key] = {"object_id": oid, "version_id": vid}
        return submission, documents, refs

    def review(self, work_id, submission_id):
        """Independent token inspection of the two public grammars, no evaluator."""
        spec = self.spec(work_id)
        submission, document, refs = self.read_submission(work_id, submission_id)
        source_refs, sources = self.source_data(work_id, spec, submission["adoption_snapshot"])
        sections = {row["section_id"]: row for row in _field(document, spec["path"])["sections"]}
        findings = []
        for claim in spec["claims"]:
            fact = _fact(claim, sources[claim["source_alias"]])
            section = sections.get(claim["section_id"], {})
            body = section.get("body", "")
            source_text = fact["source_alias"] + ":" + ".".join(fact["source_path"])
            number_text = ""
            if "; trend " in body:
                tokens = body.removesuffix(".").split("; ")
                prefix = claim["label"] + " in " + fact["period"] + ": "
                body_ok = (
                    len(tokens) == 3
                    and tokens[0].startswith(prefix)
                    and tokens[1:] == ["trend " + fact["trend"], "source " + source_text]
                    and body.endswith(".")
                )
                number_text = tokens[0][len(prefix) :] if body_ok else ""
            else:
                prefix, marker, suffix = body.partition(" = ")
                number_text, trend_marker, tail = suffix.partition(" (")
                body_ok = (
                    marker == " = "
                    and prefix == fact["period"] + ": " + claim["label"]
                    and trend_marker == " ("
                    and tail == fact["trend"] + ") [" + source_text + "]."
                )
            try:
                parsed_number = None if number_text == "unknown" else json.loads(number_text)
                number_ok = (
                    parsed_number is None
                    if fact["value"] is None
                    else type(parsed_number) in (int, float)
                    and math.isfinite(parsed_number)
                    and parsed_number == fact["value"]
                )
            except (ValueError, TypeError):
                number_ok = False
            metadata = section.get("claims")
            metadata_ok = metadata == [fact] and (
                metadata[0]["value"] is None
                if fact["value"] is None
                else type(metadata[0]["value"]) in (int, float)
            )
            if not body_ok or not number_ok or not metadata_ok:
                findings.append(
                    {
                        "claim_id": claim["claim_id"],
                        "section_id": claim["section_id"],
                        "description": "Actual report body/metadata disagrees with the read source at "
                        + source_text,
                        "locator": [
                            *spec["path"],
                            "sections",
                            next(
                                (
                                    i
                                    for i, r in enumerate(
                                        _field(document, spec["path"])["sections"]
                                    )
                                    if r["section_id"] == claim["section_id"]
                                ),
                                0,
                            ),
                            "body",
                        ],
                        **refs[spec["path"][0]],
                        "evidence": [
                            {**source_refs[claim["source_alias"]], "locator": claim["value_path"]}
                        ],
                        "fact": fact,
                    }
                )
        return findings

    def raise_findings(self, work_id, submission_id, findings):
        issues = []
        for finding in findings:
            issues.append(
                self.call(
                    "raise_issue",
                    work_id=work_id,
                    submission_id=submission_id,
                    issue_key="review-" + submission_id + "-" + finding["claim_id"],
                    object_id=finding["object_id"],
                    version_id=finding["version_id"],
                    locator=finding["locator"],
                    description=finding["description"],
                    evidence=finding["evidence"],
                    blocking=True,
                )
            )
        return issues
