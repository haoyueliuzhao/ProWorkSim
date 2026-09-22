"""Operating-world communication policies over generic condition semantics."""

import copy
import json

from ..core.conditions import apply_response
from ..core.projections import derive_condition_view, derive_current_work_view, rebuild_projections
from ..core.types import CheckStatus
from ..policies.organization import authority

DEFAULT_POLICIES = {
    "scope": {
        "power": "confirm",
        "subject": "analytical_assumptions",
        "evidence_kind": "credential",
        "reference_source": "required_basis",
        "version_dimension": "basis_requirement_version",
        "purpose": "analytical_input",
    },
    "audience": {
        "power": "confirm",
        "subject": "audience",
        "evidence_kind": "version",
        "artifact_id": "brief",
        "version_dimension": "requirement_version",
    },
    "evidence": {
        "power": "provide",
        "subject": "evidence",
        "evidence_kind": "version",
        "reference_source": "evidence_reference",
        "version_dimension": "requirement_version",
    },
}


def request_policy(state, topic):
    return copy.deepcopy(state.get("communication_policies", DEFAULT_POLICIES).get(topic))


def supports_request(state, topic):
    return request_policy(state, topic) is not None


def _reference(state, item, policy):
    if policy.get("reference_source"):
        return copy.deepcopy(item.get(policy["reference_source"]))
    artifact = state.get("artifacts", {}).get(policy.get("artifact_id"), {})
    version = artifact.get("current_version")
    return {"artifact_id": artifact["artifact_id"], "version_id": version} if version else None


def condition_template(state, item, kind, requested_role, required_version):
    """Translate domain request labels into a generic evidence requirement."""
    policy = request_policy(state, kind)
    if not policy:
        raise ValueError("Unknown blocker condition policy")
    if policy["evidence_kind"] == "credential" and required_version is None:
        raise ValueError("A credential blocker requires an explicit applicable version")
    condition = {
        "work_item_id": item["work_item_id"],
        "requirement_version": item["requirement_version"],
        "providers": list(
            dict.fromkeys([requested_role, *policy.get("alternative_providers", [])])
        ),
        "unavailable_providers": [],
        "expected_version": required_version,
        "purpose": kind,
        "required_power": policy["power"],
        "subject": policy["subject"],
        "evidence_spec": {
            "kind": policy["evidence_kind"],
            "reference": _reference(state, item, policy),
        },
        "context": {
            "project_id": state.get("project", {}).get("project_id"),
            "work_id": item["work_item_id"],
            "requirement_dimension": policy["subject"],
            "requirement_version": item.get(
                policy["version_dimension"], item["requirement_version"]
            ),
            "work_node": item.get("node_id", item["work_item_id"]),
            "period": item.get("source_period"),
            "purpose": policy.get("purpose", kind),
            "at": state["clock"],
        },
        "status": "open",
        "request_id": None,
        "history": [],
    }
    if "schema_version" not in state:
        condition["evidence_spec"] = {"kind": "legacy_protocol"}
        condition["required_power"] = None
    return condition


def register_request(state, item, actor, to, topic, message, blocker_id=None):
    from ..blockers import bind_request

    policy = request_policy(state, topic)
    if not policy or item["owner_role"] != actor:
        raise ValueError("Only a work owner can register this condition request")
    if message.get("sender") != actor or to not in message.get("recipients", []):
        raise ValueError("Request must bind its real sender and recipient")
    if blocker_id:
        bind_request(state, blocker_id, message["message_id"], actor, item["work_item_id"])
    request = {
        "request_id": message["message_id"],
        "work_item_id": item["work_item_id"],
        "requirement_version": item["requirement_version"],
        "basis_requirement_version": item.get(
            "basis_requirement_version", item["requirement_version"]
        ),
        "topic": topic,
        "requested_role": to,
        "basis_ref": copy.deepcopy(item.get("required_basis")),
        "blocker_id": blocker_id,
        "brief_version": state.get("artifacts", {}).get("brief", {}).get("current_version"),
        "evidence_reference": _reference(state, item, policy),
        "condition_version": item.get(policy["version_dimension"], item["requirement_version"]),
        "status": "pending",
    }
    state.setdefault("requests", {})[request["request_id"]] = request
    return copy.deepcopy(request)


def _current(state, request):
    item = state["work_items"][request["work_item_id"]]
    return (
        item["work_item_id"] not in state.get("work_replacements", {})
        and item["requirement_version"] == request["requirement_version"]
        and derive_current_work_view(state)[item["work_item_id"]]["status"]
        not in {"superseded", "cancelled"}
    )


def _request_identity(state, request):
    item = state["work_items"].get(request["work_item_id"])
    message = next(
        (m for m in state.get("messages", []) if m.get("message_id") == request["request_id"]), None
    )
    return (
        item is not None
        and message is not None
        and message["sender"] == item["owner_role"]
        and request["requested_role"] in message["recipients"]
        and message.get("work_item_id") == item["work_item_id"]
        and message.get("topic", message.get("subject")) == request["topic"]
    )


def _grant_reference(state, reference, actor, reply_id):
    # Grant only the referenced immutable version, never the artifact-wide ACL.
    artifact_id = reference.get("object_id", reference.get("artifact_id"))
    version = reference["version_id"]
    from ..core.visibility import grant_version

    if not grant_version(state, artifact_id, version, actor, reply_id):
        return
    record = {
        "actor_id": actor,
        "reference": copy.deepcopy(reference),
        "message_id": reply_id,
        "at": state["clock"],
    }
    state.setdefault("communication_grants", []).append(record)
    if artifact_id == "basis":
        state.setdefault("basis_visibility", []).append(
            {
                "actor_id": actor,
                "version_id": version,
                "confirmation_ref": reply_id,
                "at": state["clock"],
            }
        )


def deliver_reply(world, payload):
    """Deliver at most one reply per request, then assess conditions separately."""
    state = world.state
    request_id = payload.get("request_id")
    request = state.get("requests", {}).get(request_id)
    if request is None or not _request_identity(state, request):
        raise ValueError("Reply does not refer to an authentic request")
    if request.get("reply_message_id"):
        return {"reply_message_id": request["reply_message_id"], "duplicate": True}
    item = state["work_items"][request["work_item_id"]]
    actor, topic = request["requested_role"], request["topic"]
    policy = request_policy(state, topic)
    if policy is None:
        raise ValueError("No communication policy for this request")
    authorized = authority(
        state, actor, policy["power"], policy["subject"], item.get("node_id", item["work_item_id"])
    )
    reference = copy.deepcopy(request.get("evidence_reference"))
    if "evidence_reference" not in request:
        reference = (
            request.get("basis_ref")
            if topic == "scope"
            else (
                {"artifact_id": "brief", "version_id": request["brief_version"]}
                if topic == "audience" and request.get("brief_version")
                else None
            )
        )
    available_override = (
        state.get("provider_availability", {})
        .get(actor, {})
        .get(topic, {})
        .get(item["work_item_id"])
    )
    unavailable = (
        available_override is False
        or (available_override is None and topic in state.get("unavailable_topics", []))
        or reference is None
    )
    response_status = (
        "wrong_role" if not authorized else "unavailable" if unavailable else "delivered"
    )
    world._reads = []
    if response_status == "delivered":
        try:
            data = world._read(
                actor,
                reference.get("object_id", reference.get("artifact_id")),
                reference["version_id"],
            )
            try:
                body = json.loads(data)
            except (ValueError, UnicodeDecodeError):
                body = {"status": "delivered", "reference": reference}
            if topic == "scope" and isinstance(body, dict):
                body["approved_basis"] = copy.deepcopy(reference)
        except ValueError:
            response_status, unavailable, reference = "unavailable", True, None
            body = {
                "status": "unavailable",
                "reason": "Provider cannot access the requested version",
            }
    else:
        reference = None
        body = {
            "status": "not_authorized" if not authorized else "unavailable",
            "topic": topic,
            "work_item_id": item["work_item_id"],
            "reason": "当前没有可授权提供的确认或资料；本次答复不代表未来永远不可取得。",
        }
    message = world._message(
        actor, [item["owner_role"]], "定向请求回复", body, [reference] if reference else []
    )
    message.update(
        in_response_to=request_id,
        work_item_id=item["work_item_id"],
        requirement_version=request["requirement_version"],
    )
    if reference and authorized:
        _grant_reference(state, reference, item["owner_role"], message["message_id"])
    response = {
        "response_id": message["message_id"],
        "request_id": request_id,
        "responder": actor,
        "work_item_id": item["work_item_id"],
        "requirement_version": request["requirement_version"],
        "condition_version": request.get(
            "condition_version",
            request["basis_requirement_version"]
            if topic == "scope"
            else request["requirement_version"],
        ),
        "purpose": topic,
        "reference": reference,
        "status": response_status,
        "reason": body.get("reason") if isinstance(body, dict) else None,
    }
    result = apply_response(state, response)
    request.update(
        status="outdated_reply" if not _current(state, request) else response_status,
        delivery_status="delivered",
        response_status=response_status,
        reply_message_id=message["message_id"],
        condition_checks=result["checks"],
    )
    request["conditions_satisfied"] = bool(result["checks"]) and all(
        c["status"] == CheckStatus.PASS.value for c in result["checks"].values()
    )
    resolved = [
        state["condition_specs"][cid].get("blocker_id") for cid in result["resolved_conditions"]
    ]
    world._staff_record(
        actor,
        "scoped_reply",
        payload,
        {
            "message": message,
            "resolved_blockers": [bid for bid in resolved if bid],
            "condition_checks": result["checks"],
        },
        world._reads,
    )
    return {"reply_message_id": message["message_id"], "duplicate": False, **result}


def restore_information(
    world,
    actor,
    topic,
    provider,
    reference,
    condition_ids,
    opportunity_id=None,
    reason="Authorised information has become available",
):
    """Apply an explicit arrival; do not manufacture approval or satisfy requests.

    Existing evidence must independently satisfy every selected current condition.
    Work remains blocked until a fresh request receives that evidence. A missing
    basis may be bound, but a different existing requirement binding is never
    silently replaced. The caller supplies transactional commit/rollback.
    """
    from ..core.conditions import check_evidence
    from ..policies.organization import require_authority

    state = world.state
    policy = request_policy(state, topic)
    if not policy or not condition_ids or not isinstance(reason, str) or not reason.strip():
        raise ValueError("Restoration requires a known policy, conditions and concrete reason")
    if len(set(condition_ids)) != len(condition_ids):
        raise ValueError("Restoration condition identifiers must be unique")
    validated = []
    conditions_view = derive_condition_view(state)
    work_view = derive_current_work_view(state)
    for condition_id in condition_ids:
        condition = state.get("condition_specs", {}).get(condition_id)
        if condition is None or condition.get("purpose") != topic:
            raise ValueError("Restoration must target matching explicit conditions")
        item = state["work_items"][condition["work_item_id"]]
        if (
            item["work_item_id"] in state.get("work_replacements", {})
            or item["requirement_version"] != condition["requirement_version"]
            or work_view[item["work_item_id"]]["status"] in {"accepted", "superseded", "cancelled"}
            or conditions_view[condition_id]["status"] not in {"open", "unavailable"}
        ):
            raise ValueError("Restoration cannot change historical or completed obligations")
        node = item.get("node_id", item["work_item_id"])
        require_authority(state, actor, "restore_information", policy["subject"], node)
        require_authority(state, provider, policy["power"], policy["subject"], node)
        if provider not in condition["providers"]:
            raise ValueError("Provider is not configured for this condition")
        # The existing condition's contextual requirements are unchanged.
        check = check_evidence(state, condition, {"reference": reference})
        if check.status != CheckStatus.PASS:
            raise ValueError(
                f"Restored evidence does not satisfy the current requirement: {check.reasons}"
            )
        source = policy.get("reference_source")
        if source and item.get(source) not in (None, reference):
            # Normalize the two accepted version-reference spellings.
            from ..core.references import VersionRef

            if VersionRef.from_mapping(item[source]) != VersionRef.from_mapping(reference):
                raise ValueError("Restoration cannot replace an existing obligation binding")
        artifact_id = reference.get("object_id", reference.get("artifact_id"))
        world._artifact(provider, artifact_id, version=reference["version_id"])
        validated.append((condition, item, source))
    opportunity = None
    if opportunity_id is not None:
        opportunity = next(
            (
                entry
                for entry in state.get("future_opportunities", [])
                if entry.get("opportunity_id") == opportunity_id
            ),
            None,
        )
        if (
            opportunity is None
            or opportunity.get("status") not in {"pending", "available"}
            or opportunity.get("condition_id") not in condition_ids
            or opportunity.get("provider") not in (None, provider)
        ):
            raise ValueError("Restoration does not match an open future opportunity")
    availability = (
        state.setdefault("provider_availability", {}).setdefault(provider, {}).setdefault(topic, {})
    )
    for condition, item, source in validated:
        availability[item["work_item_id"]] = True
        condition["evidence_spec"]["reference"] = copy.deepcopy(reference)
        condition.setdefault("history", []).append(
            {
                "at": state["clock"],
                "event": "information_available",
                "actor_id": actor,
                "provider": provider,
                "reference": copy.deepcopy(reference),
                "reason": reason,
            }
        )
        if source and item.get(source) is None:
            item[source] = copy.deepcopy(reference)
            if source == "required_basis":
                item["required_credentials"] = [copy.deepcopy(reference)]
    if opportunity:
        opportunity["status"] = "consumed"
        opportunity["consumed_at"] = state["clock"]
    result = {
        "restoration_id": f"restoration-{len(state.get('information_restorations', [])) + 1}",
        "actor_id": actor,
        "provider": provider,
        "topic": topic,
        "reference": copy.deepcopy(reference),
        "condition_ids": list(condition_ids),
        "opportunity_id": opportunity_id,
        "reason": reason,
        "at": state["clock"],
    }
    notified_work = set()
    for condition, item, _ in validated:
        if item["work_item_id"] in notified_work:
            continue
        notified_work.add(item["work_item_id"])
        notice = world._message(
            actor,
            [item["owner_role"]],
            "请求资料已可提供",
            {
                "event": "information_available",
                "work_item_id": item["work_item_id"],
                "provider": provider,
                "topic": topic,
                "condition_ids": [
                    c["condition_id"]
                    for c, w, _ in validated
                    if w["work_item_id"] == item["work_item_id"]
                ],
                "instruction": "资料请求路线已恢复；可发出新请求取得与当前义务匹配的证据。旧回复的含义保持不变。",
            },
        )
        result.setdefault("notice_message_ids", []).append(notice["message_id"])
    state.setdefault("information_restorations", []).append(result)
    rebuild_projections(state)
    return copy.deepcopy(result)
