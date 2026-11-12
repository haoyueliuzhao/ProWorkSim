"""Small API controls; the companion check tool owns real process fault injection."""
import json
import sqlite3

import pytest

from proworksim.software_observer_journal_v203_2_1 import (
    JournalCorruption,
    JournalError,
    ObservationConflict,
    ObserverJournal,
    ProjectionConflict,
    inspect_export,
)


def test_restart_duplicate_and_conflict_preserve_first_durable_bytes(tmp_path):
    path = tmp_path / "observer.sqlite"
    payload = {"actor": "a", "nested": {"value": 1}}
    with ObserverJournal(path) as journal:
        first = journal.append("RECEIPT", "a:1", payload, {})
        payload["nested"]["value"] = 9
    with ObserverJournal(path) as journal:
        duplicate = journal.append("RECEIPT", "a:1", {"actor": "a", "nested": {"value": 1}}, {})
        assert duplicate["duplicate"] and duplicate["sequence"] == first["sequence"]
        with pytest.raises(ObservationConflict):
            journal.append("RECEIPT", "a:1", payload, {})
        rows = list(journal.records())
        assert len(rows) == 1 and rows[0]["payload"]["nested"]["value"] == 1
        proof = journal.integrity(expected_records=1)
        assert proof["status"] == "ok" and proof["known_conflicting_appends"] == 1
        assert proof["capture_status"] == "partial" and not proof["complete_capture_proven"]


def test_durable_outbox_checkpoint_and_compare_and_swap(tmp_path):
    path = tmp_path / "observer.sqlite"
    with ObserverJournal(path) as journal:
        for number in range(3):
            journal.append("RECEIPT", str(number), {"number": number})
        journal.save_projection("default", 2, {"projected": [0, 1]}, expected_cursor=0)
    with ObserverJournal(path) as journal, ObserverJournal(path) as rival:
        assert journal.load_projection()["state"] == {"projected": [0, 1]}
        assert [row["key"] for row in journal.pending()] == ["2"]
        rival.save_projection("default", 3, {"projected": [0, 1, 2]}, expected_cursor=2)
        with pytest.raises(ProjectionConflict):
            journal.save_projection("default", 3, {}, expected_cursor=2)
        with pytest.raises(ProjectionConflict):
            journal.save_projection("default", 1, {}, expected_cursor=3)
        assert journal.integrity()["default_pending"] == 0


def test_projection_transaction_rolls_back_on_failure(tmp_path):
    with ObserverJournal(tmp_path / "observer.sqlite") as journal:
        journal.append("INITIAL", "initial", {})
        def fail(stage):
            if stage == "before_projection_commit":
                raise OSError("injected projection disk failure")
        journal._fault = fail
        with pytest.raises(OSError):
            journal.save_projection("default", 1, {"initial": True}, expected_cursor=0)
        assert journal.load_projection()["cursor"] == 0
        assert len(list(journal.pending())) == 1


def test_invalid_or_oversized_append_has_no_memory_pending_queue(tmp_path):
    with ObserverJournal(tmp_path / "observer.sqlite", max_record_bytes=256) as journal:
        with pytest.raises(JournalError):
            journal.append("RECEIPT", "oversize", {"text": "x" * 1024})
        with pytest.raises(ValueError):
            journal.append("RECEIPT", "nan", {"number": float("nan")})
        assert list(journal.records()) == []
        assert not hasattr(journal, "_pending")
        proof = journal.integrity(expected_records=1)
        assert proof["capture_status"] == "partial"
        assert not proof["precommit_loss_detectable_without_external_manifest"]


def test_export_complete_partial_and_corrupt_do_not_modify_authority(tmp_path):
    with ObserverJournal(tmp_path / "observer.sqlite") as journal:
        journal.append("INITIAL", "initial", {"value": 1})
        export = tmp_path / "export.jsonl"
        journal.export(export)
        original = export.read_bytes()
        assert inspect_export(export)["status"] == "complete"
        export.write_bytes(original.rsplit(b"\n", 2)[0] + b"\n" + b'{"unfinished":')
        assert inspect_export(export)["status"] == "partial"
        assert inspect_export(export)["incomplete_tail"]
        lines = original.splitlines()
        record = json.loads(lines[1])
        record["payload"]["value"] = 8
        lines[1] = json.dumps(record).encode()
        export.write_bytes(b"\n".join(lines) + b"\n")
        assert inspect_export(export)["status"] == "corrupt"
        assert journal.integrity(expected_records=1)["status"] == "ok"


def test_sqlite_semantic_corruption_is_not_silently_repaired(tmp_path):
    path = tmp_path / "observer.sqlite"
    with ObserverJournal(path) as journal:
        journal.append("INITIAL", "initial", {"value": 1})
    with sqlite3.connect(path) as db:
        db.execute("UPDATE observations SET record_json=?", ('{"broken":true}',))
    with ObserverJournal(path) as journal:
        proof = journal.integrity()
        assert proof["status"] == "corrupt"
        with pytest.raises(JournalCorruption):
            list(journal.records())
        with pytest.raises(JournalCorruption):
            journal.append("RECEIPT", "later", {})
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM observations").fetchone()[0] == 1


def test_prefix_iteration_and_source_are_exact(tmp_path):
    with ObserverJournal(tmp_path / "observer.sqlite") as journal:
        for i in range(4):
            journal.append("RECEIPT", str(i), {"i": i}, {"capture_key": str(i)})
        rows = list(journal.records(after=1, through=3))
        assert [row["sequence"] for row in rows] == [2, 3]
        assert rows[0]["source"] == {"capture_key": "1"}
        assert journal.integrity(expected_records=4)["expected_count_matches"]


def test_lookup_preserves_first_source_and_detects_corruption(tmp_path):
    path = tmp_path / "observer.sqlite"
    with ObserverJournal(path) as journal:
        assert journal.lookup("missing") is None
        source = {"capture_time": 123.5, "episode_id": "cpu"}
        journal.append("INITIAL", "initial", {}, source)
        assert journal.lookup("initial")["source"] == source
    with sqlite3.connect(path) as database:
        database.execute("UPDATE observations SET record_sha256=?", ("bad",))
    with ObserverJournal(path) as journal:
        with pytest.raises(JournalCorruption):
            journal.lookup("initial")
