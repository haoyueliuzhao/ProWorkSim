import textfsm


def work_items(text):
    with open("work.template", encoding="utf-8") as stream:
        parser = textfsm.TextFSM(stream)
    return [{"group": group, "item": item, "minutes": int(minutes)}
            for group, item, minutes in parser.ParseText(text)]
