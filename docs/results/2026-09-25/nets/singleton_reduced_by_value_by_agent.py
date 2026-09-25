# Fault class: a singleton reduced by value.
#
# A sentinel is meant to exist exactly once, so code tests it with `is`.
# copy.copy, copy.deepcopy and pickle rebuild an object from what its
# reduce hook returns. When that recipe goes by value, the round trip
# builds a new object instead of returning the one that already exists:
#
#   * an Enum member whose value is identity-only (`A = object()`, or a
#     no-argument instance of a same-file class that has no __eq__):
#     Enum.__reduce_ex__ returns (cls, (value,)), the copied value is a new
#     object, and cls(new_object) raises "... is not a valid ...". (Enum
#     ignores a plain __reduce__ because it defines __reduce_ex__ itself.)
#   * a module-level instance of a stateless same-file class
#     (`MISSING = _Missing()`): the default reduce makes a second instance.
#   * a module-level bare `object()` sentinel: the same, and object itself
#     cannot be given a hook, so the sentinel needs a small class.
#
# The repair adds one reduce hook that rebuilds the object BY NAME:
#   Enum:      __reduce_ex__ -> getattr, (self.__class__, self._name_)
#   singleton: __reduce__    -> "GLOBAL_NAME"
# pickle stores a reference to the name, and copy/deepcopy hand back the
# same object. One candidate per enum or singleton, not one per line.

import ast

_SIG = re.compile(
    r"^(?:"
    r"[ \t]+[A-Za-z_]\w*[ \t]*=[ \t]*[A-Za-z_][\w.]*\([ \t]*\)"  # member in a class body
    r"|[A-Za-z_]\w*[ \t]*(?::[^=]+)?=[ \t]*[A-Za-z_][\w.]*\([ \t]*\)"  # module-level instance
    r")[ \t]*(?:#.*)?$"
)

_HOOKS = ("__reduce__", "__reduce_ex__")
_OWN_REDUCTION = _HOOKS + (
    "__getnewargs__",
    "__getnewargs_ex__",
    "__getstate__",
    "__setstate__",
    "__copy__",
    "__deepcopy__",
    "__new__",
    "__init__",
    "__eq__",
)
_ENUM_BASE = re.compile(r"(?:^|\.)\w*Enum$")
_CACHE = {}


def _tree(lines):
    src = "\n".join(lines) + "\n"
    key = hash(src)
    if key not in _CACHE:
        if len(_CACHE) > 32:
            _CACHE.clear()
        try:
            _CACHE[key] = ast.parse(src)
        except (SyntaxError, ValueError):
            _CACHE[key] = None
    return _CACHE[key]


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        head = _dotted(node.value)
        return head + "." + node.attr if head else ""
    return ""


def _indent(line):
    return line[: len(line) - len(line.lstrip())]


def _defined(cls):
    names = set()
    for stmt in cls.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(stmt.name)
        elif isinstance(stmt, ast.Assign):
            names.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            names.add(stmt.target.id)
    return names


def _classes(tree):
    return {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}


def _is_enum(cls, classes, seen=()):
    for base in cls.bases:
        name = _dotted(base)
        if _ENUM_BASE.search(name):
            return True
        local = classes.get(name)
        if local is not None and local.name not in seen:
            if _is_enum(local, classes, seen + (cls.name,)):
                return True
    return False


def _plain_stateless(cls, tree):
    """A same-file class with no base, no state, no own copy/pickle/eq rules."""
    if cls.decorator_list or cls.keywords:
        return False
    if any(_dotted(b) != "object" for b in cls.bases):
        return False
    if _defined(cls) & set(_OWN_REDUCTION):
        return False
    for node in ast.walk(cls):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and _dotted(t.value) == "self":
                    return False
    for other in ast.walk(tree):
        if isinstance(other, ast.ClassDef) and any(_dotted(b) == cls.name for b in other.bases):
            return False
    return True


def _identity_value(call, classes, tree):
    if not isinstance(call, ast.Call) or call.args or call.keywords:
        return False
    name = _dotted(call.func)
    if name in ("object", "builtins.object"):
        return True
    local = classes.get(name)
    return local is not None and _plain_stateless(local, tree)


def _style(tree):
    annotated = any(
        isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.returns is not None
        for n in ast.walk(tree)
    )
    future = any(
        isinstance(n, ast.ImportFrom)
        and n.module == "__future__"
        and any(a.name == "annotations" for a in n.names)
        for n in tree.body
    )
    return annotated, future


def _enum_hook(indent, tree):
    annotated, future = _style(tree)
    if annotated:
        ret = "tuple[object, ...]" if future else '"tuple[object, ...]"'
        head = f"def __reduce_ex__(self, proto: object) -> {ret}:"
    else:
        head = "def __reduce_ex__(self, proto):"
    return [
        indent + head,
        indent + "    # Reduce by name: an identity-only value cannot round-trip by value.",
        indent + "    return getattr, (self.__class__, self._name_)",
    ]


def _singleton_hook(indent, global_name, tree):
    annotated, _ = _style(tree)
    head = "def __reduce__(self) -> str:" if annotated else "def __reduce__(self):"
    return [
        indent + head,
        indent + "    # A singleton: copy and pickle it by reference to its global name.",
        indent + '    return "' + global_name + '"',
    ]


def _module_bindings(tree, name):
    count = 0
    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            count += sum(isinstance(t, ast.Name) and t.id == name for t in stmt.targets)
        elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            count += stmt.target.id == name and stmt.value is not None
        elif isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            count += stmt.name == name
    return count


def _enum_member(lines, tree, lineno):
    classes = _classes(tree)
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        hit = [s for s in cls.body if s.lineno == lineno]
        if not hit:
            continue
        stmt = hit[0]
        if not (
            isinstance(stmt, ast.Assign)
            and stmt.end_lineno == lineno
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], ast.Name)
            and stmt.lineno != cls.lineno
        ):
            return []
        if not _is_enum(cls, classes) or "__reduce_ex__" in _defined(cls):
            return []
        members = [
            s
            for s in cls.body
            if isinstance(s, ast.Assign)
            and len(s.targets) == 1
            and isinstance(s.targets[0], ast.Name)
            and not s.targets[0].id.startswith("_")
            and _identity_value(s.value, classes, tree)
        ]
        # one candidate per enum: only its first identity-valued member speaks
        if not members or members[0] is not stmt:
            return []
        end = cls.end_lineno
        body = lines[lineno - 1 : end]
        text = body + [""] + _enum_hook(_indent(lines[lineno - 1]), tree)
        return [SpanEdit(lineno, end, "\n".join(text))]
    return []


def _module_singleton(lines, tree, lineno):
    stmt = next((s for s in tree.body if s.lineno == lineno), None)
    if stmt is None or stmt.end_lineno != lineno:
        return []
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1:
        target, value = stmt.targets[0], stmt.value
    elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
        target, value = stmt.target, stmt.value
    else:
        return []
    if not isinstance(target, ast.Name) or _module_bindings(tree, target.id) != 1:
        return []
    name = target.id
    if not isinstance(value, ast.Call) or value.args or value.keywords:
        return []
    callee = _dotted(value.func)
    line = lines[lineno - 1]

    if callee in ("object", "builtins.object"):
        # bare object(): give the sentinel a class that can carry the hook
        words = [w for w in name.strip("_").split("_") if w]
        if not words:
            return []
        cls_name = "_" + "".join(w[:1].upper() + w[1:].lower() for w in words) + "Type"
        used = {getattr(n, "id", None) or getattr(n, "name", None) for n in ast.walk(tree)}
        if cls_name in used or re.search(r"\b%s\b" % re.escape(cls_name), "\n".join(lines)):
            return []
        new_line = re.sub(r"\b(?:builtins\.)?object\(\s*\)", cls_name + "()", line, count=1)
        text = (
            ["class " + cls_name + ":"]
            + _singleton_hook("    ", name, tree)
            + ["", "", new_line]
        )
        return [SpanEdit(lineno, lineno, "\n".join(text))]

    cls = _classes(tree).get(callee)
    if cls is None or cls.end_lineno >= lineno or not _plain_stateless(cls, tree):
        return []
    calls = sum(
        isinstance(n, ast.Call) and _dotted(n.func) == callee for n in ast.walk(tree)
    )
    if calls != 1 or not cls.body or cls.body[0].lineno == cls.lineno:
        return []
    start = cls.lineno
    indent = _indent(lines[cls.body[0].lineno - 1])
    text = (
        lines[start - 1 : cls.end_lineno]
        + [""]
        + _singleton_hook(indent, name, tree)
        + lines[cls.end_lineno : lineno]
    )
    return [SpanEdit(start, lineno, "\n".join(text))]


def rewrite(line, o):
    try:
        lines = list(o.all_lines)
        lineno = o.lineno
        if not (1 <= lineno <= len(lines)) or not _SIG.search(line):
            return []
        tree = _tree(lines)
        if tree is None:
            return []
        if line[:1] in (" ", "\t"):
            return _enum_member(lines, tree, lineno)
        return _module_singleton(lines, tree, lineno)
    except Exception:
        return []


register(
    4,
    "singleton-reduced-by-value",
    "a sentinel (an Enum member with an identity-only value such as object(), or a "
    "module-level singleton instance) is copied or pickled by value, so the round "
    "trip builds a new object instead of returning the one canonical sentinel; the "
    "repair adds a reduce hook that rebuilds it by name",
    _SIG,
    rewrite,
)


# ---------------------------------------------------------------- property


def _parse_fragment(text):
    for src in (text, "if True:\n" + text):
        try:
            return ast.parse(src)
        except (SyntaxError, ValueError):
            pass
    return None


def _hook_return(fn):
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant):
        body = body[1:]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None:
        return None
    return body[0].value


def _is_getattr_by_name(node):
    """getattr, (self.__class__ | type(self), self._name_ | self.name)"""
    if not (isinstance(node, ast.Tuple) and len(node.elts) == 2):
        return False
    fn, args = node.elts
    if _dotted(fn) != "getattr" or not isinstance(args, ast.Tuple) or len(args.elts) != 2:
        return False
    owner, member = args.elts
    owner_ok = _dotted(owner) == "self.__class__" or (
        isinstance(owner, ast.Call)
        and _dotted(owner.func) == "type"
        and len(owner.args) == 1
        and _dotted(owner.args[0]) == "self"
    )
    return owner_ok and _dotted(member) in ("self._name_", "self.name")


def _stmt_lists(tree):
    for node in ast.walk(tree):
        for field in ("body", "orelse", "finalbody"):
            block = getattr(node, field, None)
            if isinstance(block, list) and block and isinstance(block[0], ast.stmt):
                yield node, block


def prop(orig, cand):
    text = cand if isinstance(cand, str) else getattr(cand, "text", "")
    n = 0

    n += 1
    tree = _parse_fragment(text)
    if tree is None:
        return False, "the candidate is not valid Python", n

    n += 1
    otree = _parse_fragment(orig) if orig.strip() else None
    ostmt = otree.body[0] if otree is not None and otree.body else None
    if isinstance(ostmt, ast.If) and ostmt.body:
        ostmt = ostmt.body[0]
    if isinstance(ostmt, ast.Assign) and len(ostmt.targets) == 1:
        otarget, ovalue = ostmt.targets[0], ostmt.value
    elif isinstance(ostmt, ast.AnnAssign):
        otarget, ovalue = ostmt.target, ostmt.value
    else:
        return False, "the observed line is not a single-name assignment", n
    if not isinstance(otarget, ast.Name) or not isinstance(ovalue, ast.Call):
        return False, "the observed line does not bind a name to a call", n
    name = otarget.id

    n += 1
    # an Enum ignores __reduce__ (Enum defines __reduce_ex__), so for an enum
    # member only __reduce_ex__ counts; a module singleton gets exactly one hook
    member = orig[:1] in (" ", "\t")
    effective = ("__reduce_ex__",) if member else _HOOKS
    hooks = [
        f
        for f in ast.walk(tree)
        if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name in effective
    ]
    if len(hooks) != 1:
        return False, "the candidate must hold exactly one effective reduce hook, found %d" % len(hooks), n
    hook = hooks[0]
    params = [a.arg for a in hook.args.posonlyargs + hook.args.args]
    if hook.name == "__reduce_ex__" and len(params) != 2 or hook.name == "__reduce__" and len(params) != 1:
        return False, "the reduce hook has the wrong arity", n

    n += 1
    ret = _hook_return(hook)
    if ret is None:
        return False, "the reduce hook must be a single return", n
    by_enum_name = _is_getattr_by_name(ret)
    by_global_name = (
        isinstance(ret, ast.Constant)
        and isinstance(ret.value, str)
        and re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*", ret.value) is not None
    )
    if not (by_enum_name or by_global_name):
        return False, "the reduce hook does not rebuild the object by name", n

    n += 1
    kept = orig.strip() in [l.strip() for l in text.splitlines()]
    if orig[:1] in (" ", "\t"):
        # an enum member: the hook sits beside it in the same class body,
        # overrides Enum.__reduce_ex__, and looks the member up by name
        if not kept:
            return False, "the observed member line was changed", n
        if hook.name != "__reduce_ex__" or not by_enum_name:
            return False, "an Enum needs __reduce_ex__ returning getattr by member name", n
        siblings = [
            blk
            for _, blk in _stmt_lists(tree)
            if hook in blk
            and any(
                isinstance(s, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in s.targets)
                for s in blk
            )
        ]
        if not siblings:
            return False, "the hook is not in the same class body as the member", n
        return True, "", n

    # a module-level singleton: the hook lives in the class it instantiates
    # and names the global the observed line binds
    if not by_global_name or ret.value != name:
        return False, "the reduce hook must return the global name %r" % name, n
    owner = [
        c for c in ast.walk(tree) if isinstance(c, ast.ClassDef) and hook in c.body
    ]
    binds = [
        s
        for s in tree.body
        if isinstance(s, (ast.Assign, ast.AnnAssign))
        and any(
            isinstance(t, ast.Name) and t.id == name
            for t in (s.targets if isinstance(s, ast.Assign) else [s.target])
        )
        and isinstance(s.value, ast.Call)
    ]
    if len(owner) != 1 or len(binds) != 1:
        return False, "the hook's class or the global binding is missing", n
    if _dotted(binds[0].value.func) != owner[0].name:
        return False, "the global is not an instance of the class carrying the hook", n
    if not kept and _dotted(ovalue.func) not in ("object", "builtins.object"):
        return False, "the observed line was changed", n
    return True, "", n


teach_property(
    4,
    "the candidate is valid Python that keeps the observed sentinel binding and adds "
    "exactly one reduce hook, placed in the sentinel's own class, whose only statement "
    "returns the object by name (getattr on the Enum by member name, or the global "
    "name the observed line binds)",
    prop,
)
