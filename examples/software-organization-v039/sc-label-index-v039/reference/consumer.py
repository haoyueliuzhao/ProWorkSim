from labels import normalize_labels


def index_labels(values):
    normalized = normalize_labels(values)
    if normalized is None:
        return {"ok": False, "names": [], "positions": []}
    names, positions = [], []
    for value in normalized:
        if value not in names:
            names.append(value)
        positions.append(names.index(value))
    return {"ok": True, "names": names, "positions": positions}
