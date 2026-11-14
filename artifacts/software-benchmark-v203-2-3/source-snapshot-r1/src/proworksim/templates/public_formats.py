"""Public output grammar, not answers, for finite template contracts.

Rule workers already encode these formats in Python. Non-specialized workers
must receive the same specifications through their public work requirements.
No record values, expected statuses, findings or future events are included.
"""

REPORT_FORMAT = {
    "version": "report-public-format-v0.11",
    "structure": "At the content_check.path, supply {sections:[{section_id,body,claims:[claim]}]}. Preserve unrelated existing sections. Every section_id must be a unique nonempty string. Each contracted section has exactly one claim. Contracted section/claim identifiers are those in content_check.claims.",
    "claim_keys_exactly": ["claim_id", "value", "period", "trend", "source_alias", "source_path", "status"],
    "claim_values": "Use actual adopted source value/period. source_alias and source_path identify that claim's public source/value_path. status is supported for a numeric value, unresolved for null; null stays JSON null.",
    "trend": "If current value is null, unknown. If no previous_path is declared, unassessed. Otherwise unknown if previous is null, up/down/flat from comparison to the previous value.",
    "body_grammars": [
        "{label} in {period}: {value}; trend {trend}; source {source_alias}:{dot.join(source_path)}.",
        "{period}: {label} = {value} ({trend}) [{source_alias}:{dot.join(source_path)}].",
    ],
    "body_placeholders": "Use the public claim label and actual values; null renders as the literal unknown. The contracted body is exactly one of these two full finite sentences. Free prose belongs in uncontracted sections and is not semantically graded.",
    "source_references": "At each content_check.sources.reference_path, include object_id and version_id matching this exact work's actual source adoption. Source fields in JSON do not create adoption facts.",
}

RECONCILIATION_FORMAT = {
    "version": "reconciliation-public-format-v0.11",
    "structure": "At content_check.path, supply {rows:[row], summary:counts, unresolved:[key], period, base_unit}; This result object has exactly these five keys, each row exactly row_fields, and each evidence exactly the eight stated fields; put extra explanation outside this result object. Source references use each content_check.sources.reference_path and match actual exact-work adoptions.",
    "row_fields": ["key", "period", "left_ids", "right_ids", "left_value", "right_value", "delta", "evidence", "status"],
    "coverage": "One row for every key in the union of both source tables. key contains values of key_fields in their stated order. left_ids/right_ids retain all original record IDs, including ambiguous candidates. Do not drop duplicates, absent sides, conflicts or missing values.",
    "evidence": "For every original candidate, preserve an evidence object with alias, record_id, location, period, definition, currency, unit, value copied from that source. Evidence entries form a multiset: retain repeated candidates.",
    "statuses": ["matched", "converted", "conflict", "incomparable", "missing", "ambiguous"],
    "classification": "More than one candidate on either side is ambiguous; an absent side is missing. Otherwise periods/definitions/currencies must match, period must be the public reporting_period and both units must occur in unit_factors, or the pair is incomparable. Compatible pairs with null values are missing. Compatible numeric pairs use the public factors and base_unit; unequal normalized values are conflict; equal normalized values are matched for the same original unit, converted for different original units.",
    "numbers": "Only compatible numeric pairs have left_value/right_value/delta (left minus right). All three otherwise remain JSON null. row.period is the shared period only for exactly one candidate per side with equal periods, otherwise null.",
    "summary": "Object with exactly the six status names and their integer row counts, including zero counts. unresolved lists keys whose status is not matched or converted. Top-level period/base_unit are those of the public basis.",
}
