import sqlparse


def statement_records(script):
    return [{"text": piece, "kind": sqlparse.parse(piece)[0].get_type()}
            for piece in sqlparse.split(script)]
