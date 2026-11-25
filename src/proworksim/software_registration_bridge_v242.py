"""Upgrade a branch-local tool registry before (and never between) prospective paired states."""

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace
import shutil
from . import software_sdk_resume_v203_3_4 as native
from .software_fixed_organization_clone_v131 import clone_function
from .storage import read_json, atomic_write, json_bytes

ADDITIONS = {"public_check_status", "record_public_check", "locate_work"}


def orders(source, member):
    for f in sorted(
        [*source.glob("physical-api/*/request.json"), *source.glob("api/*/request.json")]
    ):
        payload = read_json(f).get("payload", {})
        if payload.get("member_id") == member and payload.get("wire", {}).get("tools"):
            return [t["function"] for t in payload["wire"]["tools"]], str(f)
    raise ValueError("No original model-visible tool definitions")


def restore(prepared, runtime, path):
    source = Path(path).parent
    state, proof = native.read(path)
    mapped = {}
    changes = {}
    for member, w in runtime.policies.items():
        old, ref = orders(source, member)
        new = w.definitions
        saved = state["workers"][member]["agent_tools"]
        before = {t["name"]: t for t in old}
        after = {t["name"]: t for t in new}
        if (
            len(old) != len(saved)
            or len(before) != len(old)
            or len(after) != len(new)
            or set(before) - set(after)
            or not set(after) - set(before) <= ADDITIONS
        ):
            raise ValueError("Unsupported SDK tool set transition")
        if any(before[k]["parameters"] != after[k]["parameters"] for k in before):
            raise ValueError("Historical action schema differs")
        registered = {t["name"]: s for t, s in zip(old, saved, strict=True)}
        ids = []
        for i, t in enumerate(new):
            key = t["name"]
            if key in registered:
                ids.append(registered[key])
            else:
                new_id = sha256((proof["identity"] + member + key).encode()).hexdigest()[:32]
                ids.append(dict(name=f"pws_{new_id}_{i}", params={}))
        mapped[member] = ids
        changes[member] = dict(
            source_request=ref,
            old_count=len(old),
            current_count=len(new),
            added=sorted(set(after) - set(before)),
            common_argument_schemas_equal=True,
            old_registration_names_preserved=True,
        )

    def read_overlay(_):
        patched = {
            **state,
            "workers": {m: {**w, "agent_tools": mapped[m]} for m, w in state["workers"].items()},
        }
        return patched, proof

    def local_copy(src, dest, **kwargs):
        result = shutil.copytree(src, dest, **kwargs)
        member = Path(src).name
        if member in mapped and Path(src).parent == Path(path) / "workers":
            identity = state["workers"][member]["conversation_id"].replace("-", "")
            conf = Path(dest) / "conversations" / identity / "base_state.json"
            data = read_json(conf)
            if data["agent"]["tools"] != state["workers"][member]["agent_tools"]:
                raise ValueError("Serialized SDK tool identities disagree")
            data["agent"]["tools"] = mapped[member]
            atomic_write(conf, json_bytes(data))
        return result

    old = native.original.restore_runtime
    restore_runtime = clone_function(
        old,
        {
            **old.__globals__,
            "read": read_overlay,
            "shutil": SimpleNamespace(**{**vars(shutil), "copytree": local_copy}),
        },
    )
    receipt = restore_runtime(prepared, runtime, path)
    receipt["restored_rejection_bindings"] = {
        m: native.rebind_rejection(w) for m, w in runtime.policies.items()
    }
    receipt["common_prefix_registration_upgrade"] = changes
    for m, w in runtime.policies.items():
        if [t.name for t in w.agent.tools] != [t["name"] for t in mapped[m]]:
            raise ValueError("Restored registry mismatch")
    return receipt
