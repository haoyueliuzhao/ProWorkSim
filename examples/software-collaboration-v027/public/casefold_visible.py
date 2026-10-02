
# These visible interaction examples execute after the existing visible suite.
assert fields.String(casefold=True).deserialize(" Straße ") == " strasse "
assert fields.String(strip_whitespace=True, casefold=True).deserialize(" Straße ") == "strasse"
assert fields.String(casefold=True).serialize("v", {"v": "UPPER"}) == "UPPER"
