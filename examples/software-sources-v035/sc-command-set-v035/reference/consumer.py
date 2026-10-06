import rules


def apply_commands(initial, commands):
    validated = rules.validate_commands(commands)
    active = set(initial)
    if validated is None:
        return {"ok": False, "active": sorted(active)}
    for command in validated:
        if command["op"] == "put":
            active.add(command["name"])
        else:
            active.discard(command["name"])
    return {"ok": True, "active": sorted(active)}
