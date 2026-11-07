"""Rule-based mutation operators. Functional ones scan any line; security ones act on `# mut:<kind>` sites."""
import re
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Operator:
    name: str
    category: str  # functional | security
    fn: Callable[[str], str | None]
    marker: str | None = None  # restrict to lines tagged `# mut:<marker>`


def _code(line: str) -> str:
    return line.split("  # ", 1)[0]


def _swap_first(line: str, pattern: str, table: dict[str, str]) -> str | None:
    code = _code(line)
    m = re.search(pattern, code)
    if not m:
        return None
    return code[:m.start()] + table[m.group(0)] + code[m.end():] + line[len(code):]


def off_by_one(line: str) -> str | None:
    if not re.match(r"\s*(if|elif|while|return|raise)\b", line) and " if " not in line:
        return None
    return _swap_first(line, r"(?<![-=<>!])(<=|>=|<|>)(?![=>])", {"<=": "<", "<": "<=", ">=": ">", ">": ">="})


def flip_conditional(line: str) -> str | None:
    if not re.match(r"\s*(if|elif|while)\b", line):
        return None
    return (_swap_first(line, r"==|!=", {"==": "!=", "!=": "=="})
            or _swap_first(line, r"\band\b|\bor\b", {"and": "or", "or": "and"})
            or _swap_first(line, r"\bnot\b ", {"not ": ""}))


_STATUS = {"200": "201", "201": "200", "204": "200", "400": "422", "401": "403", "403": "401", "404": "403",
           "409": "400", "422": "400", "429": "403"}


def wrong_status_code(line: str) -> str | None:
    m = re.search(r"status_code=(\d{3})", line)
    if not m or m.group(1) not in _STATUS:
        return None
    return line[:m.start(1)] + _STATUS[m.group(1)] + line[m.end(1):]


def _guard_false(line: str) -> str | None:
    m = re.match(r"(\s*)(if|elif) .*:(\s+#.*)?$", line)
    return f"{m.group(1)}{m.group(2)} False:{m.group(3) or ''}" if m else None


def remove_auth_check(line: str) -> str | None:
    m = re.match(r"(\s*)(\w+) = .*?(\s+#.*)$", line)
    return f'{m.group(1)}{m.group(2)} = {{"id": 1, "username": "anon"}}{m.group(3)}' if m else None


def leak_stack_trace(line: str) -> str | None:
    return line.replace('"internal error"', "traceback.format_exc()") if '"internal error"' in line else None


def skip_password_check(line: str) -> str | None:
    m = re.match(r"(\s*)if (\w+ is None) or not .*\):(\s+#.*)$", line)
    return f"{m.group(1)}if {m.group(2)}:{m.group(3)}" if m else None


def _split_args(text: str) -> list[str]:
    parts, depth, cur, quote = [], 0, "", ""
    for ch in text:
        if quote:
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0 and not quote:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())
    return parts


_EXEC = re.compile(r'execute\("(?P<sql>[^"{}]*\?[^"{}]*)", \((?P<params>.*?)\)\)(?P<tail>\.\w+\(\))?')


def string_concat_sql(line: str) -> str | None:
    """Inline the last bound parameter into the SQL text (classic injection)."""
    m = _EXEC.search(line)
    if not m:
        return None
    params = _split_args(m["params"])
    i = m["sql"].rfind("?")
    sql = m["sql"][:i] + "'{" + params[-1] + "}'" + m["sql"][i + 1:]
    rest = f', ({", ".join(params[:-1])},)' if params[:-1] else ""
    return line[:m.start()] + f'execute(f"{sql}"{rest})' + (m["tail"] or "") + line[m.end():]


def drop_owner_filter(line: str) -> str | None:
    m = _EXEC.search(line)
    if not m or "user_id = ? AND " not in m["sql"]:
        return None
    params = _split_args(m["params"])[1:]
    sql = m["sql"].replace("user_id = ? AND ", "1 = 1 AND ", 1)
    args = f', ({", ".join(params)},)' if params else ""
    return line[:m.start()] + f'execute("{sql}"{args})' + (m["tail"] or "") + line[m.end():]


OPERATORS = [
    Operator("off_by_one", "functional", off_by_one),
    Operator("flip_conditional", "functional", flip_conditional),
    Operator("wrong_status_code", "functional", wrong_status_code),
    Operator("drop_validation", "functional", _guard_false, "validate"),
    Operator("remove_auth_check", "security", remove_auth_check, "auth"),
    Operator("missing_ownership_check", "security", _guard_false, "owner"),
    Operator("drop_owner_filter", "security", drop_owner_filter, "ownerfilter"),
    Operator("skip_password_check", "security", skip_password_check, "credcheck"),
    Operator("string_concat_sql", "security", string_concat_sql, "sql"),
    Operator("leak_stack_trace", "security", leak_stack_trace, "trace"),
    Operator("disable_rate_limit", "security", _guard_false, "ratelimit"),
]
