import re


def _validate(document, patches):
    if type(document) is not str or len(document) > 4096 or type(patches) is not list or len(patches) > 16:
        raise ValueError("patch:invalid")
    seen = set()
    for patch in patches:
        if type(patch) is not dict or set(patch) != {"id", "start", "end", "expected", "replacement"}:
            raise ValueError("patch:invalid")
        key, start, end = patch["id"], patch["start"], patch["end"]
        if (type(key) is not str or re.fullmatch(r"[a-z][a-z0-9_]{0,15}", key) is None
                or key in seen or type(start) is not int or type(end) is not int
                or not 0 <= start <= end <= len(document)
                or type(patch["expected"]) is not str or type(patch["replacement"]) is not str
                or len(patch["replacement"]) > 256):
            raise ValueError("patch:invalid")
        seen.add(key)
    if any(document[p["start"]:p["end"]] != p["expected"] for p in patches):
        raise ValueError("patch:stale")
    for index, left in enumerate(patches):
        a, b = left["start"], left["end"]
        for right in patches[index + 1:]:
            c, d = right["start"], right["end"]
            conflict = (max(a, c) < min(b, d) if a < b and c < d
                        else c < a < d if a == b else a < c < b)
            if conflict:
                raise ValueError("patch:conflict")


def apply_batch(document, patches):
    _validate(document, patches)
    ordered = sorted(patches, key=lambda p: (p["start"], p["start"] != p["end"], p["id"]))
    pieces, cursor = [], 0
    for patch in ordered:
        pieces.extend((document[cursor:patch["start"]], patch["replacement"]))
        cursor = patch["end"]
    pieces.append(document[cursor:])
    return "".join(pieces)
