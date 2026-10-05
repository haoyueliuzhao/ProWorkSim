def catalog(records):
    """Produce the complete directory result under the public contract."""
    return {"records": [dict(row) for row in records], "total_quantity": len(records)}
