def work_items(text):
    result, group = [], None
    for line in text.splitlines():
        fields = line.split(" ")
        if fields[0] == "group":
            group = fields[1]
        else:
            result.append({"group": group, "item": fields[1], "minutes": int(fields[2])})
    return result
