"""Process-safe observer evidence journal; never dispatches or retries world actions.

A returned ``durable=True`` means SQLite committed with WAL/FULL synchronous mode.
An observation lost before commit cannot be reconstructed by this component. A
crash after commit but before the caller receives the acknowledgement is ambiguous
until the caller checks the same idempotency key. Recovery reads observations only.

Projection checkpoints and their cursors commit together. The remaining rows form
an on-disk outbox; neither append nor recovery keeps an in-memory pending queue.
Filesystem/hardware failure and a power-loss durability claim are outside the CPU
process-crash tests. Hashes detect accidental changes, not a hostile database owner.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
from typing import Any, Iterator

FORMAT = "observer-journal-v203.2.1"
GENESIS = "0" * 64


class JournalError(RuntimeError):
    """Observation could not be recorded; callers must preserve the world result."""


class ObservationConflict(JournalError):
    """The same observation key was submitted with different canonical contents."""


class JournalCorruption(JournalError):
    """The existing evidence is invalid; it must not be silently replaced."""


class ProjectionConflict(JournalError):
    """Another projector moved the cursor, or a checkpoint would move backwards."""


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _chain(sequence: int, previous: str, record_hash: str) -> str:
    return sha256({"sequence": sequence, "previous_sha256": previous,
                   "record_sha256": record_hash})


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ObserverJournal:
    """One SQLite connection per process; concurrent appends get one commit order.

    ``records()`` is a bounded-memory iterator over a committed prefix. Consumers
    may rebuild derived state, but must never replay the original world action.
    Use explicit close/context managers; a connection inherited across fork is
    rejected. Busy/disk/serialization errors propagate to a fail-open adapter.
    """

    def __init__(self, path: str | Path, *, timeout: float = 0.25,
                 max_record_bytes: int = 16 * 1024 * 1024):
        if max_record_bytes <= 0:
            raise ValueError("max_record_bytes must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_record_bytes = max_record_bytes
        self._pid = os.getpid()
        self._closed = False
        existed = self.path.exists()
        self._db = sqlite3.connect(self.path, timeout=timeout, isolation_level=None)
        self._db.row_factory = sqlite3.Row
        try:
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.execute("PRAGMA synchronous=FULL")
            self._db.execute("PRAGMA cache_size=-2048")
            self._db.execute("PRAGMA wal_autocheckpoint=256")
            self._db.execute("BEGIN IMMEDIATE")
            self._db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            self._db.execute("""CREATE TABLE IF NOT EXISTS observations (
                sequence INTEGER PRIMARY KEY, event_key TEXT UNIQUE NOT NULL,
                record_json TEXT NOT NULL, record_sha256 TEXT NOT NULL,
                previous_sha256 TEXT NOT NULL, chain_sha256 TEXT NOT NULL)""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS projections (
                name TEXT PRIMARY KEY, cursor INTEGER NOT NULL, state_json TEXT NOT NULL,
                state_sha256 TEXT NOT NULL, source_chain_sha256 TEXT NOT NULL)""")
            self._db.execute("""CREATE TABLE IF NOT EXISTS conflicts (
                event_key TEXT NOT NULL, existing_sha256 TEXT NOT NULL,
                rejected_sha256 TEXT NOT NULL, occurrences INTEGER NOT NULL,
                PRIMARY KEY(event_key, rejected_sha256))""")
            self._db.execute("INSERT OR IGNORE INTO metadata VALUES ('format', ?)", (FORMAT,))
            self._db.execute("INSERT OR IGNORE INTO metadata VALUES ('journal_id', ?)", (str(uuid.uuid4()),))
            version = self._db.execute("SELECT value FROM metadata WHERE key='format'").fetchone()[0]
            if version != FORMAT:
                raise JournalCorruption("Unsupported observer journal format")
            self._db.commit()
            if not existed:
                _fsync_directory(self.path.parent)
        except BaseException:
            self._db.close()
            self._closed = True
            raise

    def _check(self) -> None:
        if self._closed:
            raise JournalError("Observer journal is closed")
        if os.getpid() != self._pid:
            raise JournalError("Open a separate observer journal connection after fork")

    def _fault(self, stage: str) -> None:
        """Internal no-op seam for real subprocess crash injection in CPU checks."""

    def _encode(self, value: Any) -> str:
        encoded = canonical(value)
        if len(encoded.encode("utf-8")) > self.max_record_bytes:
            raise JournalError("Observation exceeds configured byte limit; no memory retry queue")
        return encoded

    @staticmethod
    def _decode(row: sqlite3.Row | dict) -> dict:
        try:
            record = json.loads(row["record_json"])
            record_hash = sha256(record)
            if (set(record) != {"kind", "key", "payload", "source"}
                    or record["key"] != row["event_key"]
                    or record_hash != row["record_sha256"]
                    or _chain(row["sequence"], row["previous_sha256"], record_hash) != row["chain_sha256"]):
                raise ValueError("Record structure or hash differs")
            return {"sequence": row["sequence"], **record,
                    "record_sha256": record_hash,
                    "previous_sha256": row["previous_sha256"],
                    "chain_sha256": row["chain_sha256"]}
        except (ValueError, TypeError, KeyError) as exc:
            raise JournalCorruption(f"Invalid observation sequence {row['sequence']}: {exc}") from exc

    def append(self, kind: str, key: str, payload: dict, source: dict | None = None) -> dict:
        self._check()
        if not isinstance(kind, str) or not kind or not isinstance(key, str) or not key:
            raise ValueError("Observation kind and key must be nonempty strings")
        if not isinstance(payload, dict) or (source is not None and not isinstance(source, dict)):
            raise TypeError("Observation payload/source must be dictionaries")
        if source is None:
            source = {"capture_key": key, "payload_structure_sha256": sha256(payload)}
        record = {"kind": kind, "key": key, "payload": payload, "source": source}
        encoded = self._encode(record)
        record_hash = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        self._fault("before_write")
        self._db.execute("BEGIN IMMEDIATE")
        try:
            old = self._db.execute("SELECT * FROM observations WHERE event_key=?", (key,)).fetchone()
            if old is not None:
                self._decode(old)
                if old["record_json"] != encoded:
                    self._db.execute("""INSERT INTO conflicts VALUES (?, ?, ?, 1)
                        ON CONFLICT(event_key, rejected_sha256)
                        DO UPDATE SET occurrences=occurrences+1""", (key, old["record_sha256"], record_hash))
                    self._db.commit()
                    raise ObservationConflict(f"Observation key {key!r} conflicts with its durable bytes")
                self._db.commit()
                return {"sequence": old["sequence"], "record_sha256": record_hash,
                        "duplicate": True, "durable": True}
            last = self._db.execute("SELECT * FROM observations ORDER BY sequence DESC LIMIT 1").fetchone()
            if last is not None:
                self._decode(last)
            sequence = last["sequence"] + 1 if last is not None else 1
            previous = last["chain_sha256"] if last is not None else GENESIS
            self._db.execute("INSERT INTO observations VALUES (?, ?, ?, ?, ?, ?)",
                             (sequence, key, encoded, record_hash, previous,
                              _chain(sequence, previous, record_hash)))
            self._fault("after_insert_before_commit")
            self._db.commit()
        except BaseException:
            if self._db.in_transaction:
                self._db.rollback()
            raise
        self._fault("after_commit")
        return {"sequence": sequence, "record_sha256": record_hash,
                "duplicate": False, "durable": True}

    def _head(self) -> tuple[int, str]:
        row = self._db.execute("SELECT sequence, chain_sha256 FROM observations ORDER BY sequence DESC LIMIT 1").fetchone()
        return (row[0], row[1]) if row is not None else (0, GENESIS)

    def records(self, after: int = 0, through: int | None = None) -> Iterator[dict]:
        self._check()
        if after < 0:
            raise ValueError("after must be nonnegative")
        end = self._head()[0] if through is None else through
        previous_row = self._db.execute("SELECT chain_sha256 FROM observations WHERE sequence=?", (after,)).fetchone()
        if after and previous_row is None:
            raise ValueError("after is not a committed sequence")
        previous = previous_row[0] if previous_row is not None else GENESIS
        expected = after + 1
        cursor = self._db.execute("SELECT * FROM observations WHERE sequence>? AND sequence<=? ORDER BY sequence", (after, end))
        try:
            for row in cursor:
                decoded = self._decode(row)
                if decoded["sequence"] != expected or decoded["previous_sha256"] != previous:
                    raise JournalCorruption("Missing sequence or broken observation hash chain")
                yield decoded
                expected += 1
                previous = decoded["chain_sha256"]
        finally:
            cursor.close()
        if end > after and expected != end + 1:
            raise JournalCorruption("Committed prefix ends before the requested sequence")

    def load_projection(self, name: str = "default") -> dict:
        self._check()
        row = self._db.execute("SELECT * FROM projections WHERE name=?", (name,)).fetchone()
        if row is None:
            return {"name": name, "cursor": 0, "state": None, "source_chain_sha256": GENESIS}
        try:
            state = json.loads(row["state_json"])
            reference = self._db.execute("SELECT chain_sha256 FROM observations WHERE sequence=?", (row["cursor"],)).fetchone()
            expected = reference[0] if reference is not None else GENESIS
            if (sha256(state) != row["state_sha256"] or expected != row["source_chain_sha256"]
                    or (row["cursor"] and reference is None)):
                raise ValueError("Projection checkpoint hash/reference mismatch")
        except (ValueError, TypeError) as exc:
            raise JournalCorruption(str(exc)) from exc
        return {"name": name, "cursor": row["cursor"], "state": state,
                "source_chain_sha256": row["source_chain_sha256"]}

    def save_projection(self, name: str, through_sequence: int, state: Any, *, expected_cursor: int) -> dict:
        self._check()
        encoded = self._encode(state)
        self._db.execute("BEGIN IMMEDIATE")
        try:
            prior = self.load_projection(name)
            if prior["cursor"] != expected_cursor or through_sequence < expected_cursor:
                raise ProjectionConflict("Projection cursor changed or would move backwards")
            reference = self._db.execute("SELECT chain_sha256 FROM observations WHERE sequence=?", (through_sequence,)).fetchone()
            if through_sequence < 0 or (through_sequence and reference is None):
                raise ValueError("Projection must reference a committed observation prefix")
            head = reference[0] if reference is not None else GENESIS
            self._db.execute("""INSERT INTO projections VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET cursor=excluded.cursor,
                state_json=excluded.state_json, state_sha256=excluded.state_sha256,
                source_chain_sha256=excluded.source_chain_sha256""",
                             (name, through_sequence, encoded, sha256(state), head))
            self._fault("before_projection_commit")
            self._db.commit()
        except BaseException:
            if self._db.in_transaction:
                self._db.rollback()
            raise
        return self.load_projection(name)

    def pending(self, name: str = "default") -> Iterator[dict]:
        return self.records(after=self.load_projection(name)["cursor"])

    def integrity(self, expected_records: int | None = None) -> dict:
        """Report evidence integrity, never infer lossless world-action coverage.

        A matching count cannot prove which actions were missed before commit.
        Callers must compare independent action/request manifests for that claim.
        """
        result = {"format": FORMAT, "status": "ok", "capture_status": "not_proven",
                  "complete_capture_proven": False, "world_actions_replayed": 0,
                  "precommit_loss_detectable_without_external_manifest": False,
                  "expected_records": expected_records, "issues": []}
        try:
            self._check()
            self._db.execute("BEGIN")
            try:
                checks = [row[0] for row in self._db.execute("PRAGMA quick_check")]
                if checks != ["ok"]:
                    raise JournalCorruption("; ".join(checks))
                count = 0
                head = GENESIS
                for record in self.records():
                    count += 1
                    head = record["chain_sha256"]
                conflicts = self._db.execute("SELECT COALESCE(SUM(occurrences), 0) FROM conflicts").fetchone()[0]
                names = [row[0] for row in self._db.execute("SELECT name FROM projections ORDER BY name")]
                projections = {name: self.load_projection(name) for name in names}
                result.update({"durable_records": count, "head_sha256": head,
                               "known_conflicting_appends": conflicts,
                               "projections": {name: {"cursor": p["cursor"], "pending": count - p["cursor"]}
                                               for name, p in projections.items()},
                               "default_pending": count - projections.get("default", {"cursor": 0})["cursor"],
                               "expected_count_matches": None if expected_records is None else count == expected_records,
                               "sqlite_quick_check": checks, "durable_prefix_valid": True})
                if conflicts or (expected_records is not None and count != expected_records):
                    result["capture_status"] = "partial"
            finally:
                self._db.rollback()
        except (sqlite3.DatabaseError, JournalError, ValueError, TypeError) as exc:
            result.update({"status": "corrupt", "capture_status": "unknown",
                           "durable_prefix_valid": False, "issues": [repr(exc)]})
        return result

    def export(self, path: str | Path) -> dict:
        """Atomically publish one JSONL prefix; abandoned .partial files are evidence.

        Existing complete exports survive a crash before replace. An interrupted
        staging file is never used as the append authority or automatically fixed.
        """
        self._check()
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        count, head = self._head()
        partial = target.with_name(target.name + ".partial-" + uuid.uuid4().hex)
        with partial.open("x", encoding="utf-8") as stream:
            stream.write(canonical({"type": "header", "format": FORMAT,
                                    "expected_records": count, "head_sha256": head}) + "\n")
            for record in self.records(through=count):
                stream.write(canonical({"type": "record", **record}) + "\n")
                stream.flush()
                self._fault("export_after_record")
            stream.write(canonical({"type": "footer", "records": count, "head_sha256": head}) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self._fault("export_before_replace")
        os.replace(partial, target)
        _fsync_directory(target.parent)
        return {"path": str(target), "records": count, "head_sha256": head, "complete": True}

    def close(self) -> None:
        if not self._closed:
            self._check()
            self._db.close()
            self._closed = True

    def __enter__(self) -> "ObserverJournal":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


def inspect_export(path: str | Path) -> dict:
    """Validate an export without repairing it; classify complete/partial/corrupt."""
    result = {"status": "partial", "complete_records": 0, "incomplete_tail": False,
              "footer_present": False, "issues": []}
    previous = GENESIS
    header = None
    try:
        with Path(path).open("rb") as stream:
            for line in stream:
                if not line.endswith(b"\n"):
                    result["incomplete_tail"] = True
                    break
                row = json.loads(line)
                if result["footer_present"]:
                    raise JournalCorruption("Data occurs after the export footer")
                if header is None:
                    if row.get("type") != "header" or row.get("format") != FORMAT:
                        raise JournalCorruption("Missing or unsupported export header")
                    header = row
                elif row.get("type") == "record":
                    record = {key: row[key] for key in ("kind", "key", "payload", "source")}
                    record_hash = sha256(record)
                    expected = result["complete_records"] + 1
                    if (row["sequence"] != expected or row["previous_sha256"] != previous
                            or row["record_sha256"] != record_hash
                            or row["chain_sha256"] != _chain(expected, previous, record_hash)):
                        raise JournalCorruption("Export record hash/sequence mismatch")
                    previous = row["chain_sha256"]
                    result["complete_records"] = expected
                elif row.get("type") == "footer":
                    if (row["records"] != result["complete_records"]
                            or row["head_sha256"] != previous
                            or header["expected_records"] != row["records"]
                            or header["head_sha256"] != previous):
                        raise JournalCorruption("Export footer does not match the committed prefix")
                    result["footer_present"] = True
                else:
                    raise JournalCorruption("Unexpected export row")
        if result["footer_present"] and not result["incomplete_tail"]:
            result["status"] = "complete"
    except (OSError, ValueError, TypeError, KeyError, JournalError) as exc:
        result.update({"status": "corrupt", "issues": [repr(exc)]})
    return result
