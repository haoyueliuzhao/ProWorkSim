"""Public migration client; no private fixture or expected answer is here."""
import migration
import rule_v1
import rule_v2

def migrated_results(rule, documents):
    converted = migration.migrate_v1_to_v2(rule)
    return {"rule": converted, "results": [rule_v2.evaluate_v2(converted, document) for document in documents]}

def legacy_results(rule, documents):
    return [rule_v1.evaluate(rule, document) for document in documents]
