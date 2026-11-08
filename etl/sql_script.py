from __future__ import annotations


def _dollar_token(script: str, start: int) -> str | None:
    if script[start] != "$":
        return None
    end = script.find("$", start + 1)
    if end < 0:
        return None
    token = script[start : end + 1]
    body = token[1:-1]
    if body == "" or body.isidentifier():
        return token
    return None


def split_sql(script: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []
    index = 0
    limit = len(script)
    tag: str | None = None
    while index < limit:
        if tag is None and script.startswith("--", index):
            newline = script.find("\n", index)
            index = limit if newline < 0 else newline + 1
            continue
        if tag is None and script[index] == "'":
            buf.append("'")
            index += 1
            while index < limit:
                buf.append(script[index])
                if script[index] == "'":
                    if index + 1 < limit and script[index + 1] == "'":
                        buf.append("'")
                        index += 2
                        continue
                    index += 1
                    break
                index += 1
            continue
        token = _dollar_token(script, index)
        if token is not None and (tag is None or token == tag):
            tag = None if tag is not None else token
            buf.append(token)
            index += len(token)
            continue
        if tag is None and script[index] == ";":
            statement = "".join(buf).strip()
            if statement:
                statements.append(statement)
            buf = []
            index += 1
            continue
        buf.append(script[index])
        index += 1
    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)
    return statements
