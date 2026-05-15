def normalize(data: bytes, tabstop: int = 8) -> bytes | None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None

    if text.startswith("﻿"):
        text = text[1:]

    text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = [line.rstrip(" \t") for line in text.split("\n")]

    while len(lines) > 1 and lines[-1] == "":
        lines.pop()
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"

    expanded: list[str] = []
    for line in text.split("\n"):
        i = 0
        while i < len(line) and line[i] == "\t":
            i += 1
        expanded.append(" " * (tabstop * i) + line[i:])
    text = "\n".join(expanded)

    return text.encode("utf-8")
