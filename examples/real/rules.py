# rules.py — three fault classes for the shapes that dominate REAL sub-20-line fixes, each taught from one
# worked example and shipped with a PROPERTY. Load with:
#
#     fluidfix guard . --dictionary examples/real/rules.py
#
# Measured on 565 real single-file fix commits from click, arrow, rich and python-sortedcontainers: 92%
# change 20 lines or fewer, and once the one-line fixes are set aside the largest mechanical shapes are a
# value guarded before use (15 real instances), a missing import added (9), and a collection mutated and
# then returned (from the model-bug corpus; 0 in this real history — said plainly).
#
# These edit a SPAN: a candidate containing "\n" becomes several lines. The suite judges every candidate,
# byte-exact rollback on rejection, and the property refuses wrong ones before the suite ever runs.
import sys as _sys

# ---------------------------------------------------------------- kind 4: a value that may be None, used bare
# worked example — rich b7ddacf4, logging.py:
#     self.keywords = self.keywords        <- shipped: None flows on when no keywords were given
#     if self.keywords is None:            <- the fix
#         self.keywords = self.KEYWORDS
# The class: `NAME = <a call>` followed by uses of NAME. Insert a None-guard after it. The default comes
# from what the file vouches for — an UPPERCASE constant or attribute whose name contains NAME's — and
# then the neutral literals. The suite picks.
# any plain assignment — a parameter passed through (`self.keywords = keywords`) is the commonest None source
_ASSIGN = re.compile(r"^(\s*)((?:self\.)?[A-Za-z_]\w*)\s*=\s*([^=].*)$")


def _guard_none(line, o):
    m = _ASSIGN.match(line)
    if not m or " if " in line or line.rstrip().endswith(":") or "==" in line:
        return []
    indent, name, _rhs = m.groups()
    body = "\n".join(getattr(o, "all_lines", None) or [])
    base = name.split(".")[-1].upper()
    vouched = sorted({c for c in re.findall(r"\b((?:self\.)?[A-Z][A-Z0-9_]{2,})\b", body)
                      if base in c.split(".")[-1]})          # KEYWORDS vouches for keywords
    if name.startswith("self."):
        # a constant defined bare in the class body is reached as self.CONST from a method — the file
        # vouches for the name; the qualification is the assigned name's own (measured 2026-09-22: 3 of 12
        # generated instances proposed the bare name and hit NameError)
        vouched = [c if c.startswith("self.") else f"self.{c}" for c in vouched] + \
                  [c for c in vouched if not c.startswith("self.")]
    out = []
    for d in (vouched + ['""', "0", "[]", "{}"])[:8]:
        out.append(f"{line}\n{indent}if {name} is None:\n{indent}    {name} = {d}")
    return out


register(4, "none-flows-on-unguarded",
         "a value that may be None is assigned from a call and used without a default",
         _ASSIGN, _guard_none)


def _prop_guard_touches_only_the_name(orig, cand):
    parts = cand.split("\n")
    if len(parts) != 3 or parts[0] != orig:
        return False, "the original line must be kept verbatim and exactly two lines added", 1
    m = _ASSIGN.match(orig)
    name = m.group(2) if m else None
    g = re.match(r"^\s*if (\S+) is None:\s*$", parts[1])
    a = re.match(r"^\s*(\S+) = .+$", parts[2])
    if not (name and g and a and g.group(1) == name and a.group(1) == name):
        return False, "the guard must test and assign exactly the assigned name", 3
    return True, "", 3


teach_property(4, "the original line is kept verbatim; exactly one `if NAME is None:` guard assigning "
                  "NAME is added; nothing else moves", _prop_guard_touches_only_the_name)


# ---------------------------------------------------------------- kind 5: a module used, never imported
# worked example — click 19655099, _winconsole.py:  `time.sleep(...)` with no `import time`.
# The class: `mod.attr` is used somewhere in the file, `mod` is a standard-library module, and no import
# provides it. The insertion lands ABOVE the file's first import (or its first def, if it has none), so the
# signal is that line and the applier emits the import in front of it.
_TOP = re.compile(r"^(?:import |from \S+ import |def |class )")
_STDLIB = set(getattr(_sys, "stdlib_module_names", ()))


def _add_import(line, o):
    body = getattr(o, "all_lines", None) or []
    firsts = [i for i, l in enumerate(body) if _TOP.match(l)]
    if not firsts or body[firsts[0]] != line:
        return []                                   # only the first such line takes the insertion
    text = "\n".join(body)
    imported = set(re.findall(r"^\s*import\s+([A-Za-z_]\w*)", text, re.M)) | \
               set(re.findall(r"^\s*from\s+([A-Za-z_]\w*)", text, re.M))
    used = {m for m in re.findall(r"(?<![\w.])([a-z_]\w*)\.[A-Za-z_]\w*", text)}
    out = []
    for mod in sorted(used & _STDLIB - imported - {"self", "cls"}):
        out.append(f"import {mod}\n{line}")
    return out


register(5, "module-used-never-imported",
         "a standard-library module is dereferenced somewhere in the file and no import provides it",
         _TOP, _add_import)


def _prop_one_stdlib_import(orig, cand):
    parts = cand.split("\n")
    if len(parts) != 2 or parts[1] != orig:
        return False, "exactly one line may be added, above the original, which stays verbatim", 1
    m = re.match(r"^import ([A-Za-z_]\w*)$", parts[0])
    if not m or m.group(1) not in _STDLIB:
        return False, "the added line must be `import <stdlib module>`", 2
    return True, "", 2


teach_property(5, "exactly one `import <stdlib module>` line is added above the original line, which "
                  "stays verbatim", _prop_one_stdlib_import)


# ---------------------------------------------------------------- kind 6: mutated in place, never returned
# worked example — insert_sorted in the model-bug corpus, two different writers:  `xs.insert(i, v)` as the
# last line, the caller gets None. Measured 24/24 on unseen generated instances (2026-09-19); 0 instances in
# the 565-commit real history, which is why it is last here.
_CALL = re.compile(r"^\s*[A-Za-z_]\w*\.\w+\(.*\)\s*$")


def _mutate_then_return(line, o):
    m = re.match(r"^(\s*)([A-Za-z_]\w*)\.(\w+)\((.*)\)\s*$", line)
    if not m:
        return []
    indent, receiver = m.group(1), m.group(2)
    return [f"{line}\n{indent}return {receiver}"]


register(6, "mutating-call-missing-its-return",
         "a collection is mutated in place and the function ends without returning it",
         _CALL, _mutate_then_return)


def _prop_returns_the_receiver(orig, cand):
    m = re.match(r"^(\s*)([A-Za-z_]\w*)\.", orig)
    want = f"{orig}\n{m.group(1)}return {m.group(2)}" if m else None
    if cand != want:
        return False, "the only allowed addition is `return <receiver>` after the untouched call", 1
    return True, "", 1


teach_property(6, "the call line is kept verbatim and exactly `return <its receiver>` is added",
               _prop_returns_the_receiver)
