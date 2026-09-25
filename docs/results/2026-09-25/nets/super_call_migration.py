# super_call.py — ONE migration, taught 2026-09-24 from ONE worked example, by hand, no model.
#
# kind 4 — incident: click types.py:281, class IntRange(IntParamType)
#     rv = IntParamType.convert(self, value, param, ctx)       <- before
#     rv = super().convert(value, param, ctx)                  <- after
# The migration: a method reached through a base class NAMED explicitly, with `self` passed by hand, becomes
# `super().method(...)`. Not a bug fix — no test fails before it and none should fail after; the behaviour
# must stay exactly the same.
#
# When is that true? super() starts the search after the enclosing class in the method resolution order,
# and for a class the first base listed comes straight after it. So: only when the named class is the
# enclosing class's FIRST base. Anything else — a grandparent, a second base, a class that is not a base at
# all — can change which method runs, and is not proposed. A subclass elsewhere that builds a diamond can
# still reorder the chain; that is the suite's to catch, and the sweep only trusts lines the suite runs.
#
# Held out: every other site in click. The maintainers' own commit (08a0d69) is the answer key; it was
# not consulted for the rule beyond the one line above.

import ast as _ast, io as _io, tokenize as _tk

_CALL = re.compile(r"\b([A-Za-z_][\w.]*)\.(\w+)\(\s*self\s*(,\s*|\))")


def _enclosing_first_base(o):
    """The first base of the innermost class around the observed line, as written ('' if none)."""
    src = "\n".join(getattr(o, "all_lines", None) or [])
    try:
        tree = _ast.parse(src)
    except SyntaxError:
        return ""
    best = None
    for n in _ast.walk(tree):
        if isinstance(n, _ast.ClassDef) and n.lineno <= o.lineno <= n.end_lineno:
            if best is None or n.lineno > best.lineno:
                best = n
    return _ast.unparse(best.bases[0]) if best is not None and best.bases else ""


def _to_super(line, o):
    first = _enclosing_first_base(o)
    out = []
    for m in _CALL.finditer(line):
        if m.group(1) != first or m.group(1) == "super":
            continue
        close = ")" if m.group(3) == ")" else ""
        new = line[:m.start()] + f"super().{m.group(2)}(" + close + line[m.end():]
        out.append(new)
    return out or [line]


register(4, "explicit-base-call-to-super",
         "a method reached through the class's first base named explicitly, with self passed by hand, "
         "written as super().method(...)",
         _CALL,
         _to_super)


# ---------------------------------------------------------------- the property
# "Only the receiver changed: a dotted class name became super(), the explicit `self` argument (and its
#  comma) is gone, and every other token — the method name, every argument, everything around the call —
#  is identical." Checked on tokens, independently of how the rewrite was produced.
def _toks(s):
    try:
        return [t.string for t in _tk.generate_tokens(_io.StringIO(s.strip()).readline)
                if t.type not in (_tk.NEWLINE, _tk.NL, _tk.ENDMARKER, _tk.INDENT, _tk.DEDENT, _tk.COMMENT)]
    except (_tk.TokenError, SyntaxError):
        return None


def _prop_receiver_only(orig, cand):
    a, b = _toks(orig), _toks(cand)
    if a is None or b is None:
        return None, "could not tokenise", 0
    import difflib
    ops = [op for op in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_opcodes() if op[0] != "equal"]
    receiver = [op for op in ops if op[0] == "replace"]
    removed = [op for op in ops if op[0] == "delete"]
    if len(receiver) != 1 or len(removed) != 1 or len(ops) != 2:
        return False, f"expected one receiver replaced and one `self` removed; found {len(ops)} changes", len(a)
    _, i1, i2, j1, j2 = receiver[0]
    old_recv, new_recv = a[i1:i2], b[j1:j2]
    if new_recv != ["super", "(", ")"]:
        return False, f"the receiver became {''.join(new_recv)!r}, not super()", len(a)
    if not old_recv or any(t != "." and not t.isidentifier() for t in old_recv) or old_recv[-1] == ".":
        return False, f"the old receiver {''.join(old_recv)!r} is not a class name", len(a)
    _, k1, k2, _, _ = removed[0]
    gone = a[k1:k2]
    if gone not in (["self", ","], ["self"]) or a[k1 - 1] != "(" or a[k1 - 3] != "." :
        return False, f"removed {gone!r}; only the explicit self argument may go", len(a)
    return True, "", len(a)


teach_property(4, "only the receiver changed: a class name became super(), the explicit self is gone, "
                  "and every other token is identical",
               _prop_receiver_only)
