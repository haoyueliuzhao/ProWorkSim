from records import build_catalog


def catalog_rows(rows):
    catalog = build_catalog(rows)
    if catalog is None:
        return {"ok": False, "rows": []}
    return {"ok": True, "rows": [{"key": key, "value": value}
            for key, value in zip(catalog["keys"], catalog["values"])]}
