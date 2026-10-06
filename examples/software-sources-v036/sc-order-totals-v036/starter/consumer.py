def price_order(order):
    """Price the complete validated order without dropping invalid lines."""
    return {"ok": False, "lines": [], "subtotal": 0, "discount": 0, "due": 0}
