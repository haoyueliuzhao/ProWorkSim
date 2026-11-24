"""Frozen v231 panel and whole-pair cash admission on one explicitly designated account."""

from pathlib import Path
from .software_graph_budget_v229 import WindowLedger, AdmissionStopped
from .storage import read_json

ROOT = Path(__file__).resolve().parents[2]
DESIGN = ROOT / "artifacts/software-benchmark-v230/engineering-r1/next-paired-design.json"
RUN = ROOT / "runs/software-benchmark-v231/paired-r1"


def panel_row(state):
    name = state["case"]
    path = (
        "software-benchmark-v228/diagnosis-supplement-launch-r2"
        if name.startswith("Astropy")
        else "software-benchmark-v229/dev1-balance90-r1"
    )
    rows = read_json(ROOT / "artifacts" / path / "panel.json")["rows"]
    suffix = name.lower()
    return next(r for r in rows if r["instance_id"].split("__")[-1] == suffix)


class PairedLedger(WindowLedger):
    @classmethod
    def load(cls, path):
        a = read_json(path)
        obj = cls.__new__(cls)
        obj.path, obj.cap = Path(a["ledger"]), a["cap_nanoyuan"]
        if not obj.path.is_file() or type(obj.cap) is not int or obj.cap <= 0:
            raise ValueError("Missing funded ledger")
        return obj

    def reserve_pair(self, state):
        key = "v231:" + state["case"]
        limits = state["remaining_per_branch"]
        with self.db() as db:
            if db.execute("select value from meta where key='cap'").fetchone() != (str(self.cap),):
                raise ValueError("Wrong account limit")
            slots = [(key + ":" + arm, key, limits, "pending") for arm in ("T0", "T1")]
            existing = db.execute(
                "select slot,block_id,token_limit from block_slots where block_id=? order by slot",
                (key,),
            ).fetchall()
            if existing:
                if existing != [x[:3] for x in slots]:
                    raise ValueError("Existing pair differs")
                return
            paid = db.execute(
                "select coalesce(sum(cost),0) from requests where slot in (select id from slots where status='closed')"
            ).fetchone()[0]
            active = db.execute(
                "select coalesce(sum(hold),0) from slots where status!='closed'"
            ).fetchone()[0]
            pending = db.execute(
                "select coalesce(sum(token_limit),0)*8000 from block_slots where status='pending'"
            ).fetchone()[0]
            if paid + active + pending + 2 * limits * 8000 > self.cap:
                raise AdmissionStopped("Insufficient cash for both full continuations")
            db.executemany("insert into block_slots values(?,?,?,?)", slots)
