"""Fail closed before v057 experiment resources while incident recovery is held.

This module has no release command, environment override, host repair action or
background watcher. Missing/invalid configuration is also a dispatch hold.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOLD_FILE = ROOT / "config/v057-shared-server-hold.json"
VERSION = "v057-shared-server-incident-hold-r1"


class SharedServerHold(RuntimeError):
    """No new experiment resource may be created or started."""


def read_hold():
    """Read-only status; failure to establish a valid release remains held."""
    try:
        value = json.loads(HOLD_FILE.read_bytes())
    except (OSError, ValueError) as error:
        return {"version": VERSION, "hold": True,
                "reason": "Hold configuration is unavailable or invalid: " + type(error).__name__}
    if (not isinstance(value, dict) or value.get("version") != VERSION
            or type(value.get("hold")) is not bool or value.get("automatic_release") is not False):
        return {"version": VERSION, "hold": True, "reason": "Unrecognized shared-server hold configuration"}
    if value["hold"] is False and (not isinstance(value.get("release_authorization"), str)
                                   or not value["release_authorization"].strip()):
        return {"version": VERSION, "hold": True, "reason": "No explicit reviewed release authorization recorded"}
    return value


def require_experiment_dispatch_allowed(entrypoint):
    value = read_hold()
    if value["hold"]:
        raise SharedServerHold(f"v057 shared-server hold blocks {entrypoint}: {value.get('reason', 'incident hold')}")
    return value
