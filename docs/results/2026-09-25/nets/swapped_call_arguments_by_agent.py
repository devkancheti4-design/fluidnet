# Fault class: swapped call arguments.
#
# Shape: a call passes two of its argument values in each other's places,
# e.g. open(mode, filename) for open(filename, mode), copy(dst, src) for
# copy(src, dst), f(x, key=b, other=a) for f(x, key=a, other=b).  The callee,
# the argument texts and everything else on the line are right; only which
# value sits in which parameter slot is wrong.
#
# The rewrite exchanges two whole argument values of ONE call, keeping every
# other byte of the line.  Adjacent positional pairs come first (the common
# slip), then farther positional pairs, then keyword values.  A line that
# continues a call opened on an earlier line is handled through o.all_lines.

import keyword as _keyword

_MAX = 24
_OPEN = "([{"
_CLOSE = ")]}"
_PAIR = {")": "(", "]": "[", "}": "{"}
_NOT_CALL_BEFORE = set(_keyword.kwlist) - {"True", "False", "None"}
# Callees whose result does not depend on argument order: a swap cannot fix them.
_SYMMETRIC = {"max", "min", "gcd", "lcm", "hypot"}
_STMT_START = {
    "def", "class", "import", "from", "return", "yield", "for", "while", "if",
    "elif", "else", "with", "global", "nonlocal", "del", "assert", "except",
    "raise", "try", "finally", "lambda", "async", "await", "pass", "break",
    "continue",
}
_PREFIX_CHARS = set("rRbBuUfF")


class _Frame:
    __slots__ = ("kind", "is_call", "callee", "args", "cur_start",
                 "cur_kw_value", "cur_star", "lambdas", "seen_code", "assigns")

    def __init__(self, kind, is_call, callee):
        self.kind = kind            # "(", "[", "{" or "top"
        self.is_call = is_call
        self.callee = callee
        self.args = []              # finished items: (start, end, kind, value_start)
        self.cur_start = None       # offset of first code char of current item
        self.cur_kw_value = None    # offset where a keyword argument's value starts
        self.cur_star = False
        self.lambdas = 0
        self.seen_code = []         # significant tokens of the current item (few)
        self.assigns = False        # an assignment operator appeared at this level


def _scan(text):
    """Scan Python source text; return the list of argument lists found.

    Each element is (frame_kind, is_call, callee, items, closed, assigns) where items are
    (start, end, kind, value_start) with kind in {"pos", "kw", "star"}; offsets
    index into `text`.  A frame of kind "top" collects comma-separated items at
    bracket depth 0 of each logical line (used only for lines that continue a
    call opened on an earlier line, when scanning one line on its own).
    """
    out = []
    n = len(text)
    i = 0
    stack = [_Frame("top", False, None)]
    prev_tok = None          # last significant token text
    prev2_tok = None         # the one before it
    line_first_tok = None
    line_has_tok = False
    tok_end = 0              # end offset of the last significant token

    def finish_item(fr, end):
        if fr.cur_start is not None:
            if fr.cur_star:
                kind = "star"
            elif fr.cur_kw_value is not None:
                kind = "kw"
            else:
                kind = "pos"
            fr.args.append((fr.cur_start, end, kind,
                            fr.cur_kw_value if kind == "kw" else fr.cur_start))
        fr.cur_start = None
        fr.cur_kw_value = None
        fr.cur_star = False
        fr.lambdas = 0
        fr.seen_code = []

    def close_frame(fr, closed):
        out.append((fr.kind, fr.is_call, fr.callee, fr.args, closed, fr.assigns))

    def mark(fr, start, tok):
        if fr.cur_start is None:
            fr.cur_start = start
            if tok in ("*", "**"):
                fr.cur_star = True
        if len(fr.seen_code) < 3:
            fr.seen_code.append(tok)

    while i < n:
        c = text[i]
        if c == "\n":
            # End of a physical line.  At depth 0 it also ends the logical line.
            if len(stack) == 1:
                fr = stack[0]
                finish_item(fr, tok_end)
                if len(fr.args) >= 1:
                    close_frame(fr, True)
                stack[0] = _Frame("top", False, None)
                line_has_tok = False
                line_first_tok = None
                prev_tok = prev2_tok = None
            i += 1
            continue
        if c in " \t\r\f\\":
            i += 1
            continue
        if c == "#":
            j = text.find("\n", i)
            i = n if j < 0 else j
            continue
        fr = stack[-1]
        # String literal (with optional prefix).
        j = i
        while j < n and j - i < 3 and text[j] in _PREFIX_CHARS:
            j += 1
        if j < n and text[j] in "'\"" and (j == i or not (i > 0 and (text[i - 1].isalnum() or text[i - 1] == "_"))):
            q = text[j]
            triple = text[j:j + 3] == q * 3
            k = j + (3 if triple else 1)
            while k < n:
                ch = text[k]
                if ch == "\\":
                    k += 2
                    continue
                if triple:
                    if text[k:k + 3] == q * 3:
                        k += 3
                        break
                elif ch == q:
                    k += 1
                    break
                elif ch == "\n":
                    break
                k += 1
            k = min(k, n)
            mark(fr, i, "STR")
            prev2_tok, prev_tok = prev_tok, "STR"
            tok_end = k
            if not line_has_tok:
                line_has_tok, line_first_tok = True, "STR"
            i = k
            continue
        # Name / number.
        if c.isalnum() or c == "_" or ord(c) > 127:
            k = i
            while k < n and (text[k].isalnum() or text[k] in "_." or ord(text[k]) > 127):
                if text[k] == "." and k + 1 < n and text[k + 1] == ".":
                    break
                k += 1
            word = text[i:k]
            mark(fr, i, word)
            if word == "lambda":
                fr.lambdas += 1
            prev2_tok, prev_tok = prev_tok, word
            tok_end = k
            if not line_has_tok:
                line_has_tok, line_first_tok = True, word
            i = k
            continue
        if not line_has_tok:
            line_has_tok, line_first_tok = True, c
        if c in _OPEN:
            is_call = False
            callee = None
            if c == "(" and prev_tok is not None:
                last = prev_tok.rsplit(".", 1)[-1]
                if prev_tok in (")", "]"):
                    is_call = True
                elif (prev_tok[:1].isalpha() or prev_tok[:1] == "_") and prev_tok not in _NOT_CALL_BEFORE \
                        and last not in _NOT_CALL_BEFORE and prev2_tok not in ("def", "class"):
                    is_call = True
                    callee = last
                    if prev_tok in ("match", "case") and prev2_tok is None:
                        is_call = False
            mark(fr, i, c)
            stack.append(_Frame(c, is_call, callee))
            prev2_tok, prev_tok = prev_tok, c
            tok_end = i + 1
            i += 1
            continue
        if c in _CLOSE:
            if len(stack) > 1 and stack[-1].kind == _PAIR[c]:
                inner = stack.pop()
                finish_item(inner, tok_end)
                close_frame(inner, True)
                mark(stack[-1], i, c)
            else:
                # Unmatched closer: the line continues a bracket opened earlier.
                top = stack[0]
                finish_item(top, tok_end)
                if len(top.args) >= 1:
                    close_frame(top, True)
                stack[0] = _Frame("top", False, None)
                stack[0].cur_start = None
            prev2_tok, prev_tok = prev_tok, c
            tok_end = i + 1
            i += 1
            continue
        # Operators.
        two = text[i:i + 2]
        three = text[i:i + 3]
        if three in ("**=", "//=", ">>=", "<<=", "..."):
            op = three
        elif two in ("==", "!=", "<=", ">=", ":=", "->", "**", "//", "<<", ">>",
                     "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "@="):
            op = two
        else:
            op = c
        if op == ",":
            if fr.lambdas > 0:
                mark(fr, i, ",")
            else:
                finish_item(fr, tok_end)
        elif op == ":" and fr.lambdas > 0:
            fr.lambdas -= 1
            mark(fr, i, ":")
        elif op == "=" and fr.cur_start is not None and len(fr.seen_code) == 1 \
                and fr.cur_kw_value is None and fr.kind in ("(", "top"):
            # keyword argument: NAME = value ; value starts at next code char
            k = i + 1
            while k < n and text[k] in " \t":
                k += 1
            fr.cur_kw_value = k
            fr.seen_code.append("=")
        else:
            if op == "=" or (op.endswith("=") and op not in ("==", "!=", "<=", ">=", ":=")):
                fr.assigns = True
            mark(fr, i, op)
        prev2_tok, prev_tok = prev_tok, op
        tok_end = i + len(op)
        i += len(op)
    # End of text: flush every open frame (unclosed calls still list their items).
    while len(stack) > 1:
        fr = stack.pop()
        close_frame(fr, False)       # trailing partial item is not finished
    top = stack[0]
    finish_item(top, tok_end)
    if top.args:
        close_frame(top, True)
    return out


def _value_span(item):
    start, end, kind, vstart = item
    return (vstart, end) if kind == "kw" else (start, end)


def _arg_shaped(text, items, assigns):
    """True when comma-separated items could be a call's argument list:
    no assignment at their level, keyword keys are plain names, and no
    positional item follows a keyword item."""
    if assigns:
        return False
    seen_kw = False
    for start, end, kind, vstart in items:
        if kind == "kw":
            key = text[start:vstart].rstrip().rstrip("=").strip()
            if not key.isidentifier():
                return False
            seen_kw = True
        elif kind == "pos" and seen_kw:
            return False
    return True


def _first_word(line):
    s = line.strip()
    k = 0
    while k < len(s) and (s[k].isalnum() or s[k] == "_"):
        k += 1
    return s[:k]


def _bare_list_ok(line, items, assigns):
    """Depth-0 items of a line read alone may be the arguments a continuation
    line carries for a call opened on an earlier line."""
    s = line.strip()
    if not s or s[0] in "#@" or _first_word(s) in _STMT_START:
        return False
    return _arg_shaped(line, items, assigns)


def _unmatched_or_trailing(line):
    """Read alone, the line closes a bracket it never opened or ends in a comma."""
    bal = 0
    code = _code_only(line.strip())
    for ch in code:
        if ch in _OPEN:
            bal += 1
        elif ch in _CLOSE:
            bal -= 1
            if bal < 0:
                return True
    return bal == 0 and "".join(code).rstrip().endswith(",")


def _code_only(s):
    """Characters of s outside string literals and comments."""
    out = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "#":
            break
        if c in "'\"":
            q = c
            triple = s[i:i + 3] == q * 3
            k = i + (3 if triple else 1)
            while k < n:
                if s[k] == "\\":
                    k += 2
                    continue
                if triple and s[k:k + 3] == q * 3:
                    k += 3
                    break
                if not triple and s[k] == q:
                    k += 1
                    break
                k += 1
            out.append("S")
            i = k
            continue
        out.append(c)
        i += 1
    return out


def _line_lists(line, strict_bare):
    """Argument lists visible in one line read alone: (items, callee, is_call)."""
    res = []
    for kind, is_call, callee, items, closed, assigns in _scan(line):
        if is_call:
            res.append((items, callee, True))
        elif kind == "top" and _bare_list_ok(line, items, assigns):
            if not strict_bare or _unmatched_or_trailing(line):
                res.append((items, None, False))
    return res


_CACHE = {}


def _file_calls(norm_lines):
    text = "\n".join(norm_lines) + "\n"
    got = _CACHE.get(text)
    if got is None:
        starts, off = [], 0
        for l in norm_lines:
            starts.append(off)
            off += len(l) + 1
        calls = [(f[3], f[2], True) for f in _scan(text) if f[1]]
        got = (starts, calls)
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[text] = got
    return got


def _pairs(items):
    """Index pairs in three tiers: adjacent positional, other positional, keyword values."""
    pos = [k for k, it in enumerate(items) if it[2] == "pos"]
    kw = [k for k, it in enumerate(items) if it[2] == "kw"]
    first, second, third = [], [], []
    for a in range(len(pos)):
        for b in range(a + 1, len(pos)):
            (first if b == a + 1 else second).append((pos[a], pos[b]))
    for a in range(len(kw)):
        for b in range(a + 1, len(kw)):
            third.append((kw[a], kw[b]))
    for p in pos:
        for k in kw:
            third.append((p, k))
    return first, second, third


def _swap(text, s1, s2):
    (a0, a1), (b0, b1) = sorted([s1, s2])
    if a1 > b0:
        return None
    return text[:a0] + text[b0:b1] + text[a1:b0] + text[a0:a1] + text[b1:]


def _tiers_for_line(line, lines, lineno):
    """Exchangeable value-span pairs on the line, relative to `line`, in priority tiers.
    With the file's lines, argument lists come from the whole file (so a line that
    continues a call opened earlier is understood); otherwise from the line alone."""
    lists, lo, hi = None, 0, len(line)
    if lines and isinstance(lineno, int) and 1 <= lineno <= len(lines):
        norm = [l.rstrip("\r\n") for l in lines]
        if norm[lineno - 1] == line:
            starts, lists = _file_calls(norm)
            lo = starts[lineno - 1]
            hi = lo + len(line)
    if lists is None:
        lists = _line_lists(line, strict_bare=True)
    tiers = ([], [], [])
    for items, callee, _ in lists:
        if callee in _SYMMETRIC:
            continue
        on_line = [it for it in items if lo <= it[0] and it[1] <= hi and it[2] != "star"]
        if len(on_line) < 2:
            continue
        for tier, prs in zip(tiers, _pairs(on_line)):
            for a, b in prs:
                sa, sb = _value_span(on_line[a]), _value_span(on_line[b])
                tier.append(((sa[0] - lo, sa[1] - lo), (sb[0] - lo, sb[1] - lo)))
    return tiers


class _Signal:
    """Lines holding (or continuing) a call with two or more argument values to exchange."""

    pattern = r"\w\s*\(.*,|^\s*[^#\s].*,"

    def search(self, line):
        text = line.rstrip("\r\n")
        if "," not in text:
            return None
        try:
            for items, callee, _ in _line_lists(text, strict_bare=False):
                if callee in _SYMMETRIC:
                    continue
                if sum(1 for it in items if it[2] != "star") >= 2:
                    return True
        except Exception:
            return None
        return None


_SIG = _Signal()


def rewrite(line, o):
    lines = getattr(o, "all_lines", None)
    lineno = getattr(o, "lineno", None)
    body = line.rstrip("\r\n")
    tail = line[len(body):]
    try:
        tiers = _tiers_for_line(body, lines, lineno)
    except Exception:
        return []
    out, seen = [], {body}
    for tier in tiers:
        for sa, sb in tier:
            if body[sa[0]:sa[1]] == body[sb[0]:sb[1]]:
                continue
            cand = _swap(body, sa, sb)
            if cand is None or cand in seen:
                continue
            seen.add(cand)
            out.append(cand + tail)
            if len(out) >= _MAX:
                return out
    return out


register(4, "swapped-call-arguments",
         "a call passes two of its argument values in each other's parameter slots "
         "(e.g. open(mode, name) for open(name, mode)); the fix exchanges the two and changes nothing else",
         _SIG, rewrite)


def _indent(s):
    return s[:len(s) - len(s.lstrip(" \t"))]


def prop(orig, cand):
    o = orig.rstrip("\r\n")
    c = cand.rstrip("\r\n")
    checked = 1
    if o == c:
        return False, "candidate is identical to the original line", checked
    checked += 1
    if _indent(o) != _indent(c):
        return False, "indentation changed", checked
    checked += 1
    if len(o) != len(c) or sorted(o) != sorted(c):
        return False, "candidate is not a rearrangement of the original line's characters", checked
    # Exactly two sibling argument values of one argument list exchanged, all
    # else byte-identical.  The list is a call on the line, or the depth-0 items
    # of a line that could continue a call opened earlier.
    checked += 1
    try:
        lists = _line_lists(o, strict_bare=False)
    except Exception:
        return None, "could not scan the original line", 0
    found, hit, in_call = False, None, False
    for items, callee, is_call in lists:
        vals = [it for it in items if it[2] != "star"]
        for x in range(len(vals)):
            for y in range(x + 1, len(vals)):
                sa, sb = _value_span(vals[x]), _value_span(vals[y])
                if o[sa[0]:sa[1]] != o[sb[0]:sb[1]] and _swap(o, sa, sb) == c:
                    found, hit, in_call = True, callee, is_call
                    break
            if found:
                break
        if found:
            break
    if not found:
        return False, "candidate is not an exchange of two argument values of one call", checked
    checked += 1
    if hit in _SYMMETRIC:
        return False, "the callee ignores argument order; exchanging its arguments changes nothing", checked
    # If the original line compiles on its own and the exchange happened inside
    # a call written on the line, the candidate must compile too.  (A bare
    # continuation line may compile only by accident, e.g. as a chained
    # assignment, so it is not held to this.)
    if not in_call:
        return True, "", checked
    try:
        compile(o.strip(), "<orig>", "exec")
        compiles = True
    except Exception:
        compiles = False
    if compiles:
        checked += 1
        try:
            compile(c.strip(), "<cand>", "exec")
        except Exception as e:
            return False, "candidate no longer compiles: %s" % (e,), checked
    return True, "", checked


teach_property(4, "every candidate is the original line with exactly two argument values of one call "
                  "exchanged: same indentation, same characters, every other byte unchanged, never a "
                  "call that ignores argument order, and it still compiles if the original did", prop)
