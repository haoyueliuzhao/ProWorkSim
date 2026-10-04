from datetime import datetime
from types import SimpleNamespace
from models import EventSchema


def export_events(rows):
    objects = [SimpleNamespace(event_name=row["label"],
               happened_at=datetime.fromisoformat(row["timestamp"]),
               meta={"owner": row["owner"]}, secret=row["secret"]) for row in rows]
    return EventSchema().dump(objects, many=True)
