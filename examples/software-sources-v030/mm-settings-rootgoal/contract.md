# Deliver atomic settings overlays with a public projection

The shared root goal is an in-memory settings update API. Two equal members
create and revise their own execution tasks, responsibility, dependencies and
integration; the environment provides no prepared subtasks.

Deliver `models.SettingsSchema` and `consumer.apply_settings(base, patch)`.
Settings have required string name, required nested network with required string
host and integer port 1..65535, required string token, and nonnegative integer
retries defaulting to 3 when a complete base omits it. Unknown keys, including
nested keys, are ignored. Marshmallow integer strings are accepted. The base is
valid under this contract. The consumer loads the full base and loads the patch
as a partial schema update, so omitted required fields (including nested ones)
are retained and omitted defaults must not overwrite existing values. Merge
network keys; replace other supplied fields. An invalid patch is atomic: no
change applies. Return `{"ok": bool, "state": complete_loaded_state,
"public": schema_dump_projection}`. State retains token; the public projection
must omit token using schema serialization semantics. Preserve caller objects.
Use SettingsSchema.load for validation and SettingsSchema.dump for the public
projection. Empty patch preserves the full state.

Public normal example: svc at localhost:8000 with token keep and retries 3,
patched with network.port "9000", becomes port 9000 with all other fields retained
and no token in public. A patch combining name new with port 0 returns ok false
and the entire previous state. Completion requires both reusable schema and
integrated atomic update behavior.

# Shared working agreement

The task starts from a public root requirement, source code and these acceptance
criteria. There are no preassigned execution subtasks or owners. Use the visible
task board to create or revise work and responsibility if needed. A fixed delivery
is only a version to assess, not a statement that independent acceptance passed.

`test_visible.py` executes a small original upstream regression subset and separate
public normal-path examples; passing the upstream subset alone does not establish
that the consumer works. The public examples below are part of the contract.
Independent checks use different inputs and remain controller-only. Member-authored
checks can be placed in `test_member.py`. The upstream library and visible test
files are read-only. The application modules listed in the workspace are editable.
Use the real Marshmallow API required below; reimplementing schema processing by
hand is outside the contract. Preserve caller inputs. Only specified valid input
shapes and specified validation errors are in scope; no CLI, network or persistence
is required.
