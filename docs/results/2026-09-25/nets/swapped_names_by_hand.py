# swapped_names.py — ONE fault class, taught 2026-09-24 from ONE worked example, by hand, no model.
#
# kind 4 — incident: click utils.py:141, the file is never created
#     open(mode, filename).close()      <- shipped
#     open(filename, mode).close()      <- the fix
# The class: two names inside one call's parentheses are in each other's places. Nothing is missing and
# nothing is extra — every name on the line is the right name, two of them sit where the other belongs.
# Candidates: every exchange of two different plain names (not an attribute after a dot, not a keyword or
# constant) that share the same parentheses, nearest pairs first. The suite picks.
#
# Before this file: no class in any net could write this fix — the vocabulary was blind to the shape.
# Held out: the other 11 swapped-name bugs click's suite catches, in 6 files. None consulted for tuning.

import io as _io, keyword as _kw, tokenize as _tk

_CAP = 24
_CONST = {"True", "False", "None"}


def _tokens(line):
    """Tokens of one physical line, tolerant of parentheses a continuation line closes."""
    out = []
    try:
        for t in _tk.generate_tokens(_io.StringIO(line).readline):
            out.append(t)
    except (_tk.TokenError, IndentationError, SyntaxError):
        pass
    return [t for t in out if t.type not in (_tk.NEWLINE, _tk.NL, _tk.ENDMARKER, _tk.INDENT, _tk.DEDENT)]


def _names_by_group(line):
    """Plain names, keyed by the parentheses that hold them: {group: [(index, token)]}."""
    toks, stack, groups, n = _tokens(line), [], {}, 0
    for i, t in enumerate(toks):
        if t.string in "([{" and t.type == _tk.OP:
            n += 1; stack.append(n)
        elif t.string in ")]}" and t.type == _tk.OP:
            if stack: stack.pop()
        elif t.type == _tk.NAME and stack and t.string not in _CONST and not _kw.iskeyword(t.string) \
                and not (i and toks[i - 1].string == "."):
            groups.setdefault(stack[-1], []).append((i, t))
    return groups


def _pairs(line):
    out = []
    for names in _names_by_group(line).values():
        for a in range(len(names)):
            for b in range(a + 1, len(names)):
                if names[a][1].string != names[b][1].string:
                    out.append((names[b][0] - names[a][0], names[a][1], names[b][1]))
    return sorted(out, key=lambda p: (p[0], p[1].start))


class _TwoNamesInOneCall:
    """The signal: a line whose parentheses hold two different plain names — a token check, not a regex."""
    def search(self, line):
        return bool(_pairs(line))


def _swap(line, o):
    out, seen = [], {line}
    for _, x, y in _pairs(line):
        (x0, x1), (y0, y1) = (x.start[1], x.end[1]), (y.start[1], y.end[1])
        cand = line[:x0] + y.string + line[x1:y0] + x.string + line[y1:]
        if cand not in seen:
            seen.add(cand); out.append(cand)
    return out[:_CAP] or [line]


register(4, "swapped-names",
         "two names inside one call's parentheses are in each other's places",
         _TwoNamesInOneCall(),
         _swap)


# ---------------------------------------------------------------- the property
# "The rewrite exchanges exactly two plain names on the line and nothing else moves: same tokens, same
#  count, exactly two positions differ, each holds the other's name." Refuses the applier bugs that matter
#  — a replace-all that renames every occurrence, a third name invented, an attribute or a literal moved.
def _prop_exchange(orig, cand):
    a = [(t.type, t.string) for t in _tokens(orig.strip())]
    b = [(t.type, t.string) for t in _tokens(cand.strip())]
    if not a or not b:
        return None, "could not tokenise", 0
    if len(a) != len(b):
        return False, f"token count changed {len(a)} -> {len(b)}", len(a)
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) != 2:
        return False, f"{len(diff)} tokens differ; an exchange moves exactly two", len(a)
    i, j = diff
    if not (a[i][0] == a[j][0] == _tk.NAME and a[i][1] == b[j][1] and a[j][1] == b[i][1]):
        return False, "the two changed tokens are not two names trading places", len(a)
    if any(k and a[k - 1][1] == "." for k in (i, j)):
        return False, "an attribute name moved", len(a)
    return True, "", len(a)


teach_property(4, "the rewrite exchanges exactly two plain names on the line and nothing else moves",
               _prop_exchange)
