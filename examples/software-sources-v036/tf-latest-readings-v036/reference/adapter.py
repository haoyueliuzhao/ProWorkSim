import textfsm


def readings(text):
    with open("readings.template", encoding="utf-8") as stream:
        parser = textfsm.TextFSM(stream)
    return [{"name": name, "value": int(value)} for name, value in parser.ParseText(text)]
