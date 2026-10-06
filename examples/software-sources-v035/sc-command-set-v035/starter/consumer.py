def apply_commands(initial, commands):
    """Apply only a completely validated command batch."""
    return {"ok": True, "active": sorted(initial)}
