"""Version-bound composite organization decisions for the managed software world."""

from copy import deepcopy
import hashlib
import json

from jsonschema import Draft202012Validator
from .software_graph_execution_v230 import CALL_BOUND
from .software_membership_v247 import POOL, PROJECT

DIMENSIONS = {
    "JOIN": "D0",
    "RETIRE": "D0",
    "PAUSE": "D0",
    "RESUME": "D0",
    "ROLE": "D1",
    "OWNER": "D2",
    "SPLIT": "D2",
    "MERGE": "D2",
    "LINK": "D3",
    "DEPEND": "D4",
    "VERIFY": "D5",
    "INTEGRATE": "D6",
    "TURN": "D7",
}
PROMPT = """You are the independent organization strategist. Evaluate the public project facts and unmet obligations, then ask what the current arrangement cannot cover. Compare the incumbent with executable composite patches. Consider uncovered and duplicated work, the cost of initializing or retiring a member, handoff, verification, and the remaining shared budget. A problem classification does not prescribe a change. A member can join only with a responsibility, recipient and actual turn. Retirement must migrate unfinished obligations and preserve authorship. Copy the chosen candidate's ordered operations and graph version. State the expected product, its producer, consumer, intended use, verification and failure condition. KEEP preserves the current graph. ABSTAIN names missing evidence. Both use an empty patch. Membership is fixed in O-FIXED. Never use a worker's private conversation or hidden scores. Return exactly one activate_organization call."""


def sha(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def snapshot(w):
    c = w.control()
    return dict(
        version=c["version"],
        members={
            m: ("paused" if m in c["paused"] else r["status"])
            for m, r in w._software()["registry"].items()
        },
        roles=deepcopy(c["roles"]),
        priority=list(c["priority"]),
        collaboration=sorted(w.dynamic()["collaboration"]),
        work={
            t: dict(
                owner=w._task(t)["owner"],
                dependencies=list(w._task(t)["depends_on"]),
                reviewer=v["reviewer"],
                authors=list(v["authors"]),
                scope=list(v["scope"]),
                children=list(v["children"]),
                completed=w._completion_current(t),
            )
            for t, v in w.dynamic()["work"].items()
        },
    )


def op(kind, **values):
    return dict(dimension=DIMENSIONS[kind], operation=kind, **values)


def candidate(operations, producer, consumer, artifact):
    return dict(operations=operations, producer=producer, consumer=consumer, artifact=artifact)


def menu(g, arm):
    result = {}
    active = [m for m, s in g["members"].items() if s == "live"]
    leaves = {t: v for t, v in g["work"].items() if not v["children"] and not v["completed"]}

    def offer(ops, producer, consumer, artifact):
        result[sha(ops)[:16]] = candidate(ops, producer, consumer, artifact)

    for t, v in leaves.items():
        owner = v["owner"]
        for peer in active:
            if peer == owner:
                continue

            def bind(kind, role, artifact):
                ops = [
                    op(kind, member=peer, task=t, role=role),
                    op("LINK", member=peer, peer=owner, task=t),
                    op("TURN", member=peer),
                ]
                offer(ops, peer, owner, artifact)

            if [t, peer, "diagnose"] not in g["roles"].values():
                bind("ROLE", "diagnose", "reproducible diagnosis")
            if not v["reviewer"] and peer not in v["authors"]:
                bind("VERIFY", "verify", "version-bound verdict")
            if not v["authors"] and peer != v["reviewer"]:
                bind("OWNER", "implement", "fixed patch")
            if v["dependencies"]:
                upstream = v["dependencies"][0]
                producer = g["work"][upstream]["owner"]
                if producer == peer:
                    offer(
                        [
                            op("ROLE", member=peer, task=upstream, role="handoff"),
                            op("LINK", member=peer, peer=owner, task=upstream),
                            op("TURN", member=peer),
                        ],
                        peer,
                        owner,
                        "upstream handoff",
                    )
        if arm == "O-DYNAMIC" and len(active) == 2 and POOL[2] not in g["members"]:
            m = POOL[2]
            offer(
                [
                    op("JOIN", member=m),
                    op("ROLE", member=m, task=t, role="diagnose"),
                    op("LINK", member=m, peer=owner, task=t),
                    op("TURN", member=m),
                ],
                m,
                owner,
                "independent diagnosis",
            )
            if not v["authors"] and not v["reviewer"]:
                offer(
                    [
                        op("JOIN", member=m),
                        op("OWNER", member=m, task=t, role="implement"),
                        op("LINK", member=m, peer=owner, task=t),
                        op("TURN", member=m),
                    ],
                    m,
                    owner,
                    "fixed patch",
                )
    if arm == "O-DYNAMIC" and len(active) == 3:
        for m in active[1:]:
            heir = active[0]
            ops = []
            for t, v in g["work"].items():
                if v["owner"] == m:
                    ops.append(op("OWNER", member=heir, task=t, role="succeed"))
                if v["reviewer"] == m:
                    reviewers = [
                        a
                        for a in active
                        if a != m
                        and a not in v["authors"]
                        and a not in {v["owner"], heir if v["owner"] == m else None}
                    ]
                    if not reviewers:
                        break
                    ops.append(op("VERIFY", member=reviewers[0], task=t, role="verify"))
            else:
                ops.extend([op("RETIRE", member=m, successor=heir), op("TURN", member=heir)])
                offer(ops, heir, heir, "remaining responsibility handoff")
                if not any(v["owner"] == m or v["reviewer"] == m for v in g["work"].values()):
                    offer(
                        [op("PAUSE", member=m), op("TURN", member=heir)],
                        heir,
                        heir,
                        "remaining work",
                    )
    for m, status in g["members"].items():
        if status == "paused" and arm == "O-DYNAMIC":
            for t, v in leaves.items():
                offer(
                    [
                        op("RESUME", member=m),
                        op("ROLE", member=m, task=t, role="diagnose"),
                        op("LINK", member=m, peer=v["owner"], task=t),
                        op("TURN", member=m),
                    ],
                    m,
                    v["owner"],
                    "independent diagnosis",
                )
    for t, v in leaves.items():
        owner = v["owner"]
        if not v["authors"] and len(v["scope"]) >= 2 and len(g["work"]) < 10:
            children = [
                dict(
                    task_id=t + "_a",
                    description="Responsibility for " + v["scope"][0],
                    scope=v["scope"][:1],
                ),
                dict(
                    task_id=t + "_b",
                    description="Responsibility for remaining public scope",
                    scope=v["scope"][1:],
                ),
            ]
            if not any(x["task_id"] in g["work"] for x in children):
                peer = next(m for m in active if m != owner)
                offer(
                    [
                        op("SPLIT", member=owner, task=t, children=children),
                        op("OWNER", member=peer, task=children[1]["task_id"], role="implement"),
                        op("LINK", member=peer, peer=owner, task=children[1]["task_id"]),
                        op("TURN", member=peer),
                    ],
                    peer,
                    owner,
                    "fixed patch",
                )
        if v["dependencies"]:
            u = v["dependencies"][0]
            producer = g["work"][u]["owner"]
            if producer != owner:
                offer(
                    [
                        op("DEPEND", member=owner, task=t, upstream=u),
                        op("LINK", member=producer, peer=owner, task=u),
                        op("TURN", member=producer),
                    ],
                    producer,
                    owner,
                    "versioned upstream artifact",
                )
    for t, v in g["work"].items():
        if v["children"]:
            offer(
                [op("MERGE", member=v["owner"], task=t)],
                v["owner"],
                v["owner"],
                "consolidated work package",
            )
    return result


def material(facts):
    if isinstance(facts, dict):
        return {
            k: material(v)
            for k, v in facts.items()
            if k not in {"command", "command_id", "receipts", "sequence", "opportunity"}
        }
    if isinstance(facts, list):
        return [material(v) for v in facts]
    return facts


def public_state(w, rt, evidence, arm):
    w.state = w.store.load()
    g = snapshot(w)
    budget = rt.team_budget.snapshot()
    info = dict(
        project_graph=evidence,
        obligation_graph={
            t: {"owner": v["owner"], "dependencies": v["dependencies"], "reviewer": v["reviewer"]}
            for t, v in g["work"].items()
            if not v["completed"] and not v["children"]
        },
        organization_graph=g,
        resources={
            k: budget[k] for k in ("available_tokens", "remaining_attempts", "remaining_decisions")
        },
        condition=arm,
        dimensions=DIMENSIONS,
    )
    info["base_hash"] = sha(g)
    info["decision_key"] = sha(
        [
            arm,
            material(evidence),
            info["obligation_graph"],
            {k: v for k, v in g.items() if k not in {"version", "priority"}},
        ]
    )
    info["candidates"] = {k: c for k, c in menu(g, arm).items() if allowed(w, rt, arm, c)}
    for t, v in g["work"].items():
        if any(r.get("conflicts") and r.get("task") == t for r in evidence.values()):
            owner = v["owner"]
            peer = next(m for m, s in g["members"].items() if s == "live" and m != owner)
            ops = [
                op("INTEGRATE", member=owner, task=t, role="integrate"),
                op("VERIFY", member=peer, task=t, role="verify"),
                op("TURN", member=owner),
            ]
            c = candidate(ops, owner, peer, "integrated candidate")
            if allowed(w, rt, arm, c):
                info["candidates"][sha(ops)[:16]] = c
    for c in info["candidates"].values():
        c["base_version"] = g["version"]
        c["target_version"] = g["version"] + len(c["operations"])
        c["reserved_worker_actions"] = [
            x["member"] for x in c["operations"] if x["operation"] == "TURN"
        ]
    return info


def validate(w, rt, arm, c):
    g = snapshot(w)
    live = {m for m, s in g["members"].items() if s == "live"}
    work = g["work"]
    budget = rt.team_budget.snapshot()
    if w.protocol()["terminal"] or budget["held_tokens"]:
        raise ValueError("Closed or in flight")
    if arm == "K" and c["operations"]:
        raise ValueError("Fixed organization")
    turns = 0
    for x in c["operations"]:
        kind = x["operation"]
        m = x.get("member")
        t = x.get("task")
        if x["dimension"] != DIMENSIONS[kind]:
            raise ValueError("Dimension mismatch")
        if kind in {"JOIN", "RETIRE", "PAUSE", "RESUME"} and arm != "O-DYNAMIC":
            raise ValueError("Fixed-size arm")
        if kind == "JOIN":
            if m != POOL[2] or m in g["members"] or m in live:
                raise ValueError("No new eligible identity")
            live.add(m)
            g["members"][m] = "live"
        elif kind == "RESUME":
            if g["members"].get(m) != "paused":
                raise ValueError("Not paused")
            live.add(m)
        elif m not in live:
            raise ValueError("Inactive actor")
        if kind in {"RETIRE", "PAUSE"}:
            # An unsent private version may be the only copy of useful work.
            own, ver, bundle = w._bundle(m)
            _, _, base = w._bundle(m, baseline=True)
            published = any(
                p["author"] == m
                and p["source_reference"] == {"object_id": own["artifact_id"], "version_id": ver}
                for p in w._software()["patches"].values()
            )
            if not published and any(
                bundle.get(k) != base.get(k) for k in ("files", "entry_metadata")
            ):
                raise ValueError("Unpublished private changes")
            if m in w.control()["priority"]:
                raise ValueError("Outstanding action reservation")
            if (
                m == POOL[0]
                or len(live) <= 2
                or any(v["owner"] == m or v["reviewer"] == m for v in work.values())
            ):
                raise ValueError("Stranded owner or reviewer")
            if any(
                m
                in (
                    v.get("from_member"),
                    v.get("to_member"),
                    v.get("recipient"),
                    v.get("owner"),
                    v.get("sender"),
                )
                for v in w._software().get("transfer_offers", {}).values()
                if v.get("status") == "pending"
            ):
                raise ValueError("Pending transfer")
            if kind == "RETIRE" and (x["successor"] not in live or m == x["successor"]):
                raise ValueError("Invalid successor")
            live.remove(m)
        if t and t not in work:
            raise ValueError("Unknown package")
        if kind == "SPLIT":
            children = x["children"]
            scopes = [s for a in children for s in a["scope"]]
            if (
                work[t]["owner"] != m
                or work[t]["authors"]
                or work[t]["completed"]
                or work[t]["children"]
                or len(children) < 2
                or len(set(scopes)) != len(scopes)
                or set(scopes) != set(work[t]["scope"])
                or any(
                    a["task_id"] in work or a["task_id"] in w.control().get("archived_packages", {})
                    for a in children
                )
            ):
                raise ValueError("Invalid scope partition")
            work[t]["children"] = [a["task_id"] for a in children]
            for a in children:
                work[a["task_id"]] = dict(
                    owner=m,
                    reviewer=None,
                    dependencies=[],
                    children=[],
                    scope=a["scope"],
                    authors=[],
                    completed=False,
                )
        if kind == "MERGE":
            siblings = work[t]["children"]
            if len(siblings) < 2 or any(
                work[a]["owner"] != m
                or work[a]["completed"]
                or work[a]["children"]
                or work[a]["authors"]
                or work[a]["reviewer"]
                or work[a]["dependencies"]
                or a in w.dynamic()["active_work"].values()
                or any(a in b["dependencies"] for b in work.values())
                for a in siblings
            ):
                raise ValueError("Unsafe package merge")
            if any(e[0] in siblings for e in g["collaboration"]) or any(
                v[0] in siblings for v in g["roles"].values()
            ):
                raise ValueError("Linked sibling duties")
        if kind == "OWNER" and x["role"] != "succeed" and t in w.dynamic()["active_work"].values():
            raise ValueError("Cannot reassign an active package as unstarted")
        if kind == "OWNER":
            if (work[t]["authors"] and x["role"] != "succeed") or m == work[t]["reviewer"]:
                raise ValueError("Illegal ownership change")
            if x["role"] == "succeed" and not any(
                y["operation"] == "RETIRE" and y["member"] == work[t]["owner"]
                for y in c["operations"]
            ):
                raise ValueError("Missing succession")
            work[t]["owner"] = m
        if kind == "VERIFY":
            if m == work[t]["owner"] or m in work[t]["authors"]:
                raise ValueError("Self review")
            work[t]["reviewer"] = m
        if kind == "ROLE" and x.get("role") not in {"diagnose", "handoff"}:
            raise ValueError("Unsupported scoped role")
        if kind == "LINK" and (x["peer"] not in live or m == x["peer"]):
            raise ValueError("Invalid collaboration")
        if kind == "DEPEND":
            if x["upstream"] not in work or t == x["upstream"]:
                raise ValueError("Invalid dependency")
            work[t]["dependencies"] = list(set(work[t]["dependencies"]) | {x["upstream"]})
        if kind == "TURN":
            turns += 1
    if not {c["producer"], c["consumer"]} <= live:
        raise ValueError("Inactive contributor")
    if any(
        v["owner"] not in live or (v["reviewer"] and v["reviewer"] not in live)
        for v in work.values()
    ):
        raise ValueError("Uncovered work")

    def visit(t, ancestors):
        if t in ancestors:
            raise ValueError("Cyclic dependency")
        for u in work[t]["dependencies"]:
            visit(u, ancestors | {t})

    for t in work:
        visit(t, set())
    turns += len(w.control()["priority"])
    if turns * CALL_BOUND > budget["available_tokens"] or turns > min(
        budget["remaining_attempts"], budget["remaining_decisions"]
    ):
        raise ValueError("Not enough worker resources")
    if any(
        x["operation"] == "JOIN"
        and not any(
            y["operation"] == "TURN" and y["member"] == x["member"] for y in c["operations"]
        )
        for x in c["operations"]
    ):
        raise ValueError("Member has no opportunity")


def allowed(w, rt, arm, c):
    try:
        validate(w, rt, arm, c)
    except ValueError:
        return False
    return True


def wire(state):
    ids = list(state["candidates"])

    def string(**extra):
        return dict(type="string", minLength=1, **extra)

    def obj(**props):
        return dict(
            type="object", properties=props, required=list(props), additionalProperties=False
        )

    def array(items):
        return dict(type="array", items=items, uniqueItems=True)

    members = array(string(enum=list(POOL)))
    action = string(enum=["KEEP", "CHANGE", "ABSTAIN"])
    alternatives = [[], *[c["operations"] for c in state["candidates"].values()]]
    schema = obj(
        assessment=obj(
            anomaly_type=string(enum=["A1", "A2", "A3", "A4", "A5", "STABLE", "UNKNOWN"]),
            evidence_refs=array(string(enum=list(state["project_graph"]))),
            current_organization_blocker=string(),
        ),
        decision=obj(action=action, candidate_id=string(enum=["none", *ids]), reason=string()),
        membership_decision=obj(
            action=string(
                enum=["KEEP_SIZE", "ADD_MEMBER", "RETIRE_MEMBER", "PAUSE_MEMBER", "RESUME_MEMBER"]
            ),
            current_active_members=dict(type="integer"),
            proposed_active_members=dict(type="integer"),
            members_to_activate=members,
            members_to_retire=members,
        ),
        organization_patch=obj(
            base_graph_version=dict(const=state["organization_graph"]["version"]),
            base_hash=dict(const=state["base_hash"]),
            target_graph_version=dict(type="integer", minimum=0),
            operations=dict(type="array", enum=alternatives),
        ),
        expected_contribution=obj(
            producer=string(),
            consumer=string(),
            artifact=string(),
            intended_use=string(),
            verification=string(),
            failure_condition=string(),
        ),
        execution_plan=obj(
            immediate_action=obj(actor=string(), action=string(), expected_artifact=string()),
            subsequent_actions=array(string()),
            preconditions=array(string()),
        ),
        resource_plan=obj(
            team_token_limit=dict(const=5000000),
            reserved_worker_actions=array(string(enum=list(POOL))),
            coordination_cost=obj(
                estimated_input_tokens=dict(type="integer", minimum=0),
                estimated_output_tokens=dict(type="integer", minimum=0),
                reason=string(),
            ),
        ),
        reevaluation=obj(trigger=string(), required_evidence=array(string())),
    )
    return dict(
        model="deepseek-flash",
        thinking={"type": "disabled"},
        temperature=1.0,
        top_p=1.0,
        stream=False,
        max_tokens=4096,
        messages=[
            dict(role="system", content=PROMPT + " " + GUIDANCE),
            dict(role="user", content=json.dumps(state, ensure_ascii=False, separators=(",", ":"))),
        ],
        tools=[
            dict(
                type="function",
                function=dict(
                    name="activate_organization",
                    description="Submit one ordered, version-bound organization patch.",
                    parameters=schema,
                ),
            )
        ],
        tool_choice="auto",
    )


GUIDANCE = """Read the project graph for observed engineering facts, the obligation graph for outstanding products, and the organization graph for current responsibilities. Use only cited public receipts. Distinguish repeated verified failure A1, an unusable upstream product A2, integration conflict A3, a verification gap A4, and sustained delivery stall A5. Use STABLE or UNKNOWN as appropriate. No anomaly requires a particular change. First identify the problem; then identify why the current team cannot handle it or why KEEP is adequate. D0 governs member lifecycle; D1 scoped duties; D2 package ownership and boundaries; D3 collaboration and information flow; D4 cross-package ordering; D5 independent verification; D6 integration and delivery responsibility; D7 priorities and the shared resource pool. Only listed combinations can execute. Never claim that assignment verifies, adoption solves, or adding a person improves utility. For CHANGE copy the full operations array in sequence and the candidate's producer, consumer and artifact. Identify the work newly covered, compare overlap and coordination costs, and name an observable failure condition. For KEEP and ABSTAIN select none, use an empty patch, no reserved actions or new outcome (use 'none' for its fields). For ABSTAIN name missing evidence and a concrete trigger. The immediate action names the candidate producer and expected artifact. For CHANGE copy each operation object verbatim including every field. Estimate coordination input and output tokens separately and give your reason; a prediction does not grant budget. List the reservation in TURN order. All members share the same five million token limit."""


def decide(state, proposal):
    Draft202012Validator(wire(state)["tools"][0]["function"]["parameters"]).validate(proposal)
    g = state["organization_graph"]
    dec = proposal["decision"]
    patch = proposal["organization_patch"]["operations"]
    mem = proposal["membership_decision"]
    contribution = proposal["expected_contribution"]
    c = state["candidates"].get(dec["candidate_id"])
    if proposal["organization_patch"]["target_graph_version"] != g["version"] + len(patch):
        raise ValueError("Wrong target version")
    if not proposal["assessment"]["evidence_refs"]:
        raise ValueError("Cite a visible receipt")
    if dec["action"] == "CHANGE":
        if not c or not patch or patch != c["operations"]:
            raise ValueError("Patch not offered or operations reordered")
        immediate = proposal["execution_plan"]["immediate_action"]
        if immediate["actor"] != c["producer"] or immediate["expected_artifact"] != c["artifact"]:
            raise ValueError("Unbound first action")
        if any(contribution[k] != c[k] for k in ("producer", "consumer", "artifact")):
            raise ValueError("Unbound contribution")
    elif c or patch or any(v != "none" for v in contribution.values()):
        raise ValueError("Nonchange creates work")
    joins = [x["member"] for x in patch if x["operation"] in {"JOIN", "RESUME"}]
    exits = [x["member"] for x in patch if x["operation"] in {"RETIRE", "PAUSE"}]
    old = sum(s == "live" for s in g["members"].values())
    tag = next(
        (
            {
                "JOIN": "ADD_MEMBER",
                "RETIRE": "RETIRE_MEMBER",
                "RESUME": "RESUME_MEMBER",
                "PAUSE": "PAUSE_MEMBER",
            }[x["operation"]]
            for x in patch
            if x["dimension"] == "D0"
        ),
        "KEEP_SIZE",
    )
    if mem != dict(
        action=tag,
        current_active_members=old,
        proposed_active_members=old + len(joins) - len(exits),
        members_to_activate=joins,
        members_to_retire=exits,
    ):
        raise ValueError("Membership totals or identities differ")
    if proposal["resource_plan"]["reserved_worker_actions"] != [
        x["member"] for x in patch if x["operation"] == "TURN"
    ]:
        raise ValueError("Unbound scheduling promise")
    if dec["action"] == "ABSTAIN" and not proposal["reevaluation"]["required_evidence"]:
        raise ValueError("Specify missing evidence")
    return c


def execute_operation(w, x, reason):
    k = x["operation"]
    m = x["member"]
    t = x.get("task")
    c = w.control()
    d = w.dynamic()
    if k == "JOIN":
        w.join(reason)
    elif k == "RETIRE":
        for key, v in list(c["roles"].items()):
            if v[1] == m:
                c["roles"].pop(key)
                c["roles"][key.replace(m, x["successor"])] = [v[0], x["successor"], v[2]]
        d["active_work"].pop(m, None)
        d["collaboration"] = [e for e in d["collaboration"] if m not in e[1:]]
        w.retire(m, reason)
    elif k == "PAUSE":
        c["paused"].append(m)
    elif k == "RESUME":
        c["paused"].remove(m)
    elif k in {"ROLE", "INTEGRATE"}:
        c["roles"][f"{t}/{m}/{k}"] = [t, m, x.get("role", "integrate")]
    elif k == "OWNER":
        w._task(t)["owner"] = m
        for actor, task in list(d["active_work"].items()):
            if task == t and actor != m:
                d["active_work"].pop(actor)
    elif k == "LINK":
        for e in ([t, m, x["peer"]], [t, x["peer"], m]):
            if e not in d["collaboration"]:
                d["collaboration"].append(e)
    elif k == "VERIFY":
        d["work"][t]["reviewer"] = m
    elif k == "DEPEND":
        if x["upstream"] not in w._task(t)["depends_on"]:
            w._action_change_dependency(m, PROJECT, t, x["upstream"], "add", reason)
        c["roles"][f"{t}/{m}/coordinate"] = [t, m, "coordinate:" + x["upstream"]]
    elif k == "SPLIT":
        w._action_split_work(m, PROJECT, t, x["children"], reason)
    elif k == "MERGE":
        children = d["work"][t]["children"]
        if len(children) < 2 or any(
            d["work"][a]["children"]
            or d["work"][a]["authors"]
            or d["work"][a]["completion"]
            or w._task(a)["owner"] != m
            or w._task(a)["depends_on"]
            or a in d["active_work"].values()
            or any(a in w._task(b)["depends_on"] for b in d["work"])
            for a in children
        ):
            raise ValueError("Only unstarted, same-owner independent siblings can merge")
        if any(e[0] in children for e in d["collaboration"]) or any(
            v[0] in children for v in c["roles"].values()
        ):
            raise ValueError("Unmigrated sibling obligations")
        for a in children:
            c.setdefault("archived_packages", {})[a] = dict(
                task=w._software()["tasks"].pop(a), work=d["work"].pop(a)
            )
        d["work"][t]["children"] = []
    elif k == "TURN":
        c["priority"].append(m)
    else:
        raise ValueError("Unsupported operation")


def apply(w, rt, state, proposal):
    c = decide(state, proposal)
    key = state["decision_key"]
    replay = False
    with w.store.lock():
        w.state = w.store.load()
        ctrl = w.control()
        if key in ctrl["receipts"]:
            old = ctrl["receipts"][key]
            if old["proposal_hash"] != sha(proposal):
                raise ValueError("Conflicting replay")
            receipt = deepcopy(old)
            replay = True
        else:
            before = snapshot(w)
            if (
                sha(before) != state["base_hash"]
                or before["version"] != proposal["organization_patch"]["base_graph_version"]
            ):
                raise ValueError("Stale graph")
            receipt = dict(
                key=key,
                base=sha(before),
                version_before=before["version"],
                completed=[],
                proposal_hash=sha(proposal),
            )
            if c:
                validate(w, rt, state["condition"], c)
            elif w.protocol()["terminal"] or rt.team_budget.snapshot()["held_tokens"]:
                raise ValueError("Closed or in flight")
            for x in c["operations"] if c else []:
                try:
                    execute_operation(w, x, proposal["decision"]["reason"])
                except Exception as exc:
                    w.state = w.store.load()
                    receipt["error"] = str(exc)
                    break
                receipt["completed"].append(x)
                w.control()["version"] += 1
                w.control()["receipts"][key] = {
                    **deepcopy(receipt),
                    "status": "partial",
                    "version_after": w.control()["version"],
                    "after": sha(snapshot(w)),
                }
                w.store.save(w.state)
            receipt.update(
                status="partial" if "error" in receipt else proposal["decision"]["action"],
                version_after=w.control()["version"],
                after=sha(snapshot(w)),
            )
            w.control()["receipts"][key] = receipt
            w.store.save(w.state)
    rt.sync_members()
    if c and receipt["status"] == "CHANGE" and not replay:
        msg = "Current public organization decision: " + json.dumps(
            {
                k: proposal[k]
                for k in (
                    "organization_patch",
                    "expected_contribution",
                    "execution_plan",
                    "reevaluation",
                )
            }
        )
        for m in w.organization_active_members():
            rt.policies[m].conversation.send_message(msg)
    elif receipt.get("status") == "partial":
        # The committed prefix is visible on the next decision; another plan may repair it.
        rt.recorder.record("organization_patch_partial", receipt)
    return receipt
