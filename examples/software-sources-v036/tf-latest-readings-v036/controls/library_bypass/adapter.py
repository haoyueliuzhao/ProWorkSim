def readings(text):
    result = []
    for line in text.splitlines():
        _, name, value = line.split(" ")
        result.append({"name": name, "value": int(value)})
    return result
