"""New independent attempt identities with the unchanged v141 solver contract."""
from __future__ import annotations

import re

from . import software_benchmark_alignment_contract_v141 as original

VERSION = original.VERSION
DEPLOYMENT_VERSION = 'v146-independent-role-API-recovery-identities-r1'
GROUP_IDS = ('FREE2', 'REVIEW2')
TEAM_TOKEN_BUDGET = original.TEAM_TOKEN_BUDGET
condition = original.condition
shared_strategy = original.shared_strategy
validate_condition = original.validate_condition
initial_message = original.initial_message
preparation_profile = original.preparation_profile


def _original_identity(row):
    match = re.fullmatch(r'v146:(v142:.+):attempt([12])', row.get('slot_id', ''))
    if not match or row.get('organization_id') not in GROUP_IDS:
        raise ValueError('Only a distinct first or conditional second recovery identity is admitted')
    old, attempt = match.group(1), int(match.group(2))
    for key in ('original_slot_id', 'recovery_of_slot_id'):
        if key in row and row[key] != old:
            raise ValueError('Original attempt identity changed')
    for key in ('recovery_round', 'recovery_attempt'):
        if key in row and row[key] != attempt:
            raise ValueError('Conditional attempt number changed')
    return {**row, 'slot_id': old}


def validate_plan_identity(row):
    original.validate_plan_identity(_original_identity(row))
    return row


def validate_controller_identity(config, arm='PROJECT'):
    original.validate_controller_identity(_original_identity(config), arm=arm)
    return config
