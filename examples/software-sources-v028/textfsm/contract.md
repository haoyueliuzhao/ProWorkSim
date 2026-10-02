# Ordered parsed records

Shared goal: repair TextFSM List ordering and deliver a working record consumer. Two equal-permission members choose responsibilities; both tasks initially have no owner. Either member may implement either or both.

1. Restore TextFSM's `List` value order in `TextFSMOptions.List.OnSaveRecord`. Keep values in encounter order, including repeated values. Preserve existing parser behavior and selected upstream regressions.
2. Implement `consumer.record_items(text)`. Parse text with the real `textfsm.TextFSM` API using this template:

```text
Value Required KEY (\w+)
Value List ITEM (\S+)

Start
 ^key: ${KEY}
 ^item: ${ITEM}
 ^end -> Record

```

Return `[{"key": key, "items": list_of_items}, ...]` in parsed record order. `key:` selects the record key, `item:` appends an item, and `end` closes a record. Empty text returns `[]`. Preserve item order and duplicates; no hand-written replacement parser. Both the library and consumer must work together; a fixed library patch can be exchanged and integrated, but two-person participation is not required by correctness.

This consumer requirement is a project derivation, not part of the original single-agent SWE-smith mutation. `test_visible.py` executes a fixed subset of original upstream unittest methods. No claim of the official complete Docker suite is made.
