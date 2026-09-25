# SPDX-License-Identifier: AGPL-3.0-or-later
"""Many small nets, one overseer.

A guard's dictionary is 16 slots, 7 of them yours — a hard ceiling, but a ceiling PER PROCESS. So each net
is one `fluidfix guard` process with its own dictionary, N nets carry 7N taught classes, and the overseer
only has to route. Routing is a measurement, not a guess: each net's signals are scanned over the source
files, and nets are tried in order of how much of the repository they recognise. The first net whose guard
repairs wins; every other net's refusal is kept."""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_SKIP = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "tests", "test", "build", "dist"}


def fluidfix_bin() -> str:
    beside = Path(sys.executable).parent / "fluidfix"
    if beside.exists():
        return str(beside)
    found = shutil.which("fluidfix")
    if not found:
        raise RuntimeError("fluidfix is not installed beside this interpreter or on PATH")
    return found


def signals_of(dictionary: str) -> list:
    """The signals a dictionary registers, captured without touching the live registry."""
    got = []
    ns = {"re": re, "register": lambda k, n, d, s, a: got.append((k, n, s)),
          "teach_property": lambda *a, **k: None, "SpanEdit": object}
    try:
        from fluidfix import propcheck
        ns["propcheck"] = propcheck
    except ImportError:
        ns["propcheck"] = None
    src = Path(dictionary).read_text(encoding="utf-8")
    exec(compile(src, dictionary, "exec"), ns)
    return got


def source_files(root: Path):
    for p in root.rglob("*.py"):
        if not any(part in _SKIP for part in p.relative_to(root).parts):
            yield p


@dataclass
class NetScore:
    dictionary: str
    classes: int
    hits: int
    files: list[str] = field(default_factory=list)


def score(root: str | Path, nets: list[str]) -> list[NetScore]:
    """Order nets by how much of the repository their signals recognise. Highest first."""
    root = Path(root)
    texts = {str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="replace")
             for p in source_files(root)}
    out = []
    for net in nets:
        sigs = signals_of(net)
        hits, files = 0, []
        for rel, text in texts.items():
            n = sum(len(sig.findall(text)) for _k, _n, sig in sigs if sig is not None)
            if n:
                hits += n; files.append(rel)
        out.append(NetScore(net, len(sigs), hits, files))
    return sorted(out, key=lambda s: -s.hits)


@dataclass
class Outcome:
    net: str
    status: str                  # repaired | refused | green | error
    output: str
    exit: int
    patched: str = ""            # the repaired file's text, when a repair was found


def run_net(root: str | Path, net: str, commit: bool, python: str | None = None,
            extra: list[str] | None = None) -> Outcome:
    """One net = one fluidfix process with one dictionary."""
    cmd = [fluidfix_bin(), "guard", str(root), "--dictionary", net]
    cmd.append("--commit" if commit else "--dry-run")
    if python:
        cmd += ["--python", python]
    cmd += extra or []
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    if "repaired line" in out or "PROPOSED (dry-run)" in out:
        status = "repaired"
    elif "suite green" in out:
        status = "green"
    elif r.returncode == 2 or "REFUSED" in out:
        status = "refused"
    else:
        status = "error"
    return Outcome(net, status, out.strip(), r.returncode)


def watch(root: str | Path, nets: list[str], commit: bool = False, python: str | None = None,
          extra: list[str] | None = None) -> dict:
    """Route once. Returns {"order": [...], "outcomes": [...], "winner": net | None}."""
    order = score(root, nets)
    outcomes, winner = [], None
    for s in order:
        o = run_net(root, s.dictionary, commit, python, extra)
        outcomes.append(o)
        if o.status in ("repaired", "green"):
            winner = s.dictionary
            break
    return {"order": order, "outcomes": outcomes, "winner": winner}


# ------------------------------------------------------------------ buggy finds, the nets fix and certify
#
# Measured 2026-09-24 on real click (a regression at parser.py:437, `<` -> `<=`, 92 failing tests): the blind
# guard searched core.py, decorators.py and formatting.py and refused at its 300 s budget without opening
# parser.py — the knowledge was there, the SEARCH was the bottleneck. buggy's mutation lane put parser.py:437
# first in 279 s and proposed `<= -> <`; `fluidfix repair --file` repairs it exactly in 130 s. So watch asks
# buggy WHERE, and the nets only ever search the files buggy names.

def hits_in_scope(dictionary: str, root, rel: str, lines: list | None = None) -> int:
    """How many lines in scope — a file, or buggy's lines in it — this net's own signals match. That is the
    size of the uniqueness proof the net must run there: every candidate on every matching line is judged."""
    try:
        text = (Path(root) / rel).read_text(encoding="utf-8").split("\n")
    except OSError:
        return 0
    try:
        sigs = [sig for _k, _n, sig in signals_of(dictionary)]
    except Exception:                  # an unreadable net costs nothing to order; its repair reports the error
        return 0
    want = range(1, len(text) + 1) if not lines else [l for l in lines if 0 < l <= len(text)]
    return sum(1 for l in want if any(sig.search(text[l - 1]) for sig in sigs))


def buggy_bin() -> str | None:
    beside = Path(sys.executable).parent / "buggy"
    return str(beside) if beside.exists() else shutil.which("buggy")


def buggy_has_mutation(bb: str) -> bool:
    """PyPI's buggy-cli 0.1.0 predates the mutation lane — the lane that found the click bug."""
    r = subprocess.run([bb, "locate", "--help"], capture_output=True, text=True)
    return "--no-mutate" in r.stdout


@dataclass
class Leads:
    files: list = field(default_factory=list)      # buggy's files, best evidence first
    lines: dict = field(default_factory=dict)      # file -> the lines buggy flagged in it, any lane
    repairs: list = field(default_factory=list)    # buggy's proposed one-token repairs {file, line, was, now, edit}
    seconds: float = 0.0
    commit: str = ""                               # the commit bisect blamed, if it converged
    status: str = ""                               # buggy's own: red | green | error
    measured: int = 0                              # lines the mutation lane measured
    cut: int = 0                                   # lines its budget left unmeasured — silence, not innocence
    mut_seconds: float = 0.0                       # what the mutation lane spent
    workers: int = 0                               # the hive it ran with (0 = serial)


def leads_from(d: dict, top_files: int = 3) -> Leads:
    """Order files by the kind of evidence: an EXPERIMENT (the mutation lane) and the INTRODUCING COMMIT are
    direct; coverage (the cause law) and where missing code belongs (the omission law) are circumstantial.
    A lane's rank 0 is a veto and contributes nothing."""
    order = []
    def take(f):
        if f and f not in order:
            order.append(f)
    # A proposed repair is buggy's strongest evidence of WHERE: its mutant flipped every failing test and broke
    # no passing one (ALL and CLEAN). Its WHAT may still be wrong — a deletion stands in when buggy has no
    # operator for the line — and fluidnet certifies that separately; the place leads regardless. Measured
    # 2026-09-25 on click: with the whole target measured, buggy's only repair sat on the fault
    # (_textwrap.py:168, `-=` -> `pass`, where `+=` is right) while five call-path lines outranked it, and the
    # top-3 file cut left _textwrap.py out.
    for r in d.get("repairs") or []:
        take(r.get("file"))
    for m in d.get("mutation") or []:
        if int(m.get("rank", 0) or 0) > 0: take(m["file"])
    for f in ((d.get("when") or {}).get("hunks") or {}):
        take(f)
    for lane in ("where", "omission"):
        for m in d.get(lane) or []:
            if int(m.get("rank", 0) or 0) > 0: take(m["file"])
    # buggy's POINTING is its top findings per lane — the ones its own report shows a person (8, 8, 5), each
    # list already ranked. `buggy locate --json` prints every scored line; taking all of them handed a repair
    # a 600-line "focus" in click's core.py, which searched like the whole file (measured 2026-09-24: 55+
    # minutes, against 165 s on buggy's 11 flagged lines).
    TOP = {"mutation": 8, "where": 8, "omission": 5}
    lines = {}
    for r in d.get("repairs") or []:
        if r.get("file") and r.get("line"):
            lines.setdefault(r["file"], set()).add(int(r["line"]))
    for lane, k in TOP.items():
        for m in (d.get(lane) or [])[:k]:
            if int(m.get("rank", 0) or 0) > 0:
                lines.setdefault(m["file"], set()).add(int(m["line"]))
    cost = d.get("mutation_cost") or {}
    return Leads(files=order[:top_files], lines={f: sorted(v) for f, v in lines.items()},
                 repairs=list(d.get("repairs") or []),
                 seconds=float(d.get("seconds") or 0), commit=(d.get("when") or {}).get("commit", ""),
                 status=d.get("status", ""), measured=int(cost.get("measured") or 0),
                 cut=int(cost.get("cut") or 0), mut_seconds=float(cost.get("seconds") or 0),
                 workers=int(cost.get("workers") or 0))


def buggy_leads(root, python: str | None = None, jobs: int = 1, mutate_seconds: int = 240,
                top_files: int = 3, timeout: int = 1800, mutants: int | None = None) -> Leads | None:
    """Run `buggy locate --json` in its own process group. None when buggy is not installed."""
    import json, os, signal, tempfile
    bb = buggy_bin()
    if not bb:
        return None
    cmd = [bb, "locate", str(root), "--json", "-j", str(jobs), "--mutate-seconds", str(mutate_seconds)] + \
          (["--mutants", str(mutants)] if mutants else []) + (["--python", python] if python else [])
    with tempfile.TemporaryFile() as fo:
        p = subprocess.Popen(cmd, stdout=fo, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pass
        try:
            os.killpg(p.pid, signal.SIGKILL)      # nothing a mutant spawned may outlive the run
        except (ProcessLookupError, PermissionError):
            pass
        p.wait(); fo.seek(0); out = fo.read().decode(errors="replace")
    d = None
    i = out.find("{")
    if i >= 0:
        try:
            d = json.loads(out[i:])
        except ValueError:
            d = None
    if d is None and (Path(root) / ".buggy" / "locate.json").exists():
        d = json.loads((Path(root) / ".buggy" / "locate.json").read_text())
    if d is None:
        return Leads(status="error")
    return leads_from(d, top_files)


def _free_bytes() -> int:
    """Memory the hive may use: free + inactive pages (macOS vm_stat), MemAvailable (Linux), else half of RAM."""
    try:
        if sys.platform == "darwin":
            out = subprocess.run(["vm_stat"], capture_output=True, text=True).stdout
            page = int(re.search(r"page size of (\d+)", out).group(1))
            pages = sum(int(m) for m in re.findall(r"Pages (?:free|inactive):\s+(\d+)", out))
            return pages * page
        for l in Path("/proc/meminfo").read_text().splitlines():
            if l.startswith("MemAvailable:"):
                return int(l.split()[1]) * 1024
    except Exception:
        pass
    import os
    return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") // 2


def hive_size(leads: Leads, cores: int | None = None, free: int | None = None, max_seconds: int = 1800,
              per_worker: int = 400 * 2 ** 20, per_line: int = 6) -> tuple[int, int, int]:
    """(workers, seconds, mutants) to measure the WHOLE target, from buggy's own first run: it measured
    `measured` lines in `mut_seconds` on `workers`, and left `cut` unmeasured. The work is lines / rate; the
    hive is as many workers as that work needs within `max_seconds`, never more than the cores (two kept for
    the machine) or the memory (`per_worker` each) allow. Measured 2026-09-25 on click: one worker, 240 s,
    47 lines measured and 1,130 cut — the bug's file never reached."""
    import math, os
    cores = cores or os.cpu_count() or 2
    free = _free_bytes() if free is None else free
    most = max(1, min(cores - 2, free // per_worker))
    total = leads.measured + leads.cut
    if leads.measured <= 0 or leads.mut_seconds <= 0:
        return most, max_seconds, max(300, total * per_line)
    work = total * leads.mut_seconds * max(1, leads.workers) / leads.measured * 1.2     # worker-seconds, +20%
    jobs = min(most, max(1, math.ceil(work / max_seconds)))
    return jobs, min(max_seconds, math.ceil(work / jobs)), max(300, total * per_line)


def apply_repair(root, rep: dict) -> str | None:
    """buggy's proposal as a whole new file, only if the line still reads what buggy saw."""
    f = Path(root) / rep["file"]
    lines = f.read_text(encoding="utf-8").split("\n")
    i = int(rep["line"]) - 1
    if not (0 <= i < len(lines)) or lines[i] != rep["was"]:
        return None
    lines[i] = rep["now"]
    return "\n".join(lines)


def _commit(root, rel: str, message: str) -> None:
    subprocess.run(["git", "add", "--", rel], cwd=root, capture_output=True)
    subprocess.run(["git", "commit", "-q", "-m", message, "--", rel], cwd=root, capture_output=True)


def fluidfix_has_focus() -> bool:
    """`fluidfix repair --focus` arrived after fluidfix 0.16.0."""
    r = subprocess.run([fluidfix_bin(), "repair", "--help"], capture_output=True, text=True)
    return "--focus" in r.stdout


def fluidfix_has_budget() -> bool:
    """`fluidfix repair --budget` (the loop's CAPPED lane) arrived after e09eb24."""
    r = subprocess.run([fluidfix_bin(), "repair", "--help"], capture_output=True, text=True)
    return "--budget" in r.stdout


def repair_file(root, net: str | None, rel: str, commit: bool, python: str | None = None,
                focus: list | None = None, budget: int | None = None) -> Outcome:
    """One net, the file named. `fluidfix repair` writes a repair it ships; unless committing, the bytes are
    put back and the repair is reported as a diff."""
    import difflib, json
    f = Path(root) / rel
    before = f.read_bytes()
    cmd = [fluidfix_bin(), "repair", str(root), "--file", rel, "--json"] + \
          (["--dictionary", net] if net else []) + (["--python", python] if python else []) + \
          (["--focus", ",".join(map(str, focus))] if focus else []) + \
          (["--budget", str(budget)] if budget else [])
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    after = f.read_bytes()
    d = {}
    i = out.find("{")
    if i >= 0:
        try:
            d = json.loads(out[i:])
        except ValueError:
            pass
    if r.returncode == 0 and d.get("repaired"):
        diff = "".join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
                                            f"a/{rel}", f"b/{rel}"))
        if commit:
            _commit(root, rel, f"fluidnet: repair {rel}:{d.get('lineno')} ({Path(net).name if net else 'shipped'})")
        else:
            f.write_bytes(before)
        scope = d.get("scope", "file")
        return Outcome(net or "shipped", "repaired",
                       (diff or out.strip()) + (f"\n(scope: {scope} — unique within these lines only)"
                                                if scope != "file" else ""), 0, after.decode())
    if after != before:                                  # a refusal leaves the file as found
        f.write_bytes(before)
    status = ("stopped at budget" if d.get("ruling") == "RAISE_BUDGET" else
              "refused" if r.returncode == 2 else "error")
    return Outcome(net or "shipped", status, out.strip()[-600:], r.returncode)


def _same_program(x: str, y: str) -> bool:
    import ast
    try:
        return ast.dump(ast.parse(x)) == ast.dump(ast.parse(y))
    except SyntaxError:
        return x == y


def _changed_lines(original: str, patched: str) -> list[int]:
    """The lines of `original` a patch touches (an insertion counts the line it follows)."""
    import difflib
    out = set()
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(a=original.splitlines(), b=patched.splitlines(),
                                                         autojunk=False).get_opcodes():
        if tag != "equal":
            out.update(range(i1 + 1, max(i2, i1 + 1) + 1) if i2 > i1 else [max(1, i1)])
    return sorted(out)


def _edit_size(original: str, text: str) -> int:
    """Characters changed, line by line — the smaller of two equal programs is the one that ships."""
    import difflib
    return sum(max(i2 - i1, j2 - j1)
               for x, y in zip(original.splitlines(), text.splitlines()) if x != y
               for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, x, y).get_opcodes() if tag != "equal")


@dataclass
class Judged:
    verdict: str                    # UNIQUE | CONFIRMED | AMBIGUOUS | NOT-CHECKED | a certificate's refusal
    why: str
    certificate: object = None
    ship: str | None = None         # the text to ship: the fix, or an equal program with a smaller edit
    rival: str | None = None        # AMBIGUOUS: the other program that also passes
    rival_net: str = ""
    seconds: float = 0.0

    @property
    def ok(self) -> bool:
        return self.verdict in ("UNIQUE", "CONFIRMED", "NOT-CHECKED")


def judge_outside_fix(root, rel: str, patched: str, nets: list[str], python: str | None = None,
                      order: list | None = None) -> Judged:
    """A fix fluidnet did not write — buggy's, an agent's, a colleague's — under the two laws fluidnet's own
    fixes obey. CERTIFIED: red before, green on the full suite, stable, nothing else broken. UNIQUE: the nets
    search the lines it touches, and no DIFFERENT program there also passes. Certification alone is the
    overfit hole — measured 2026-09-25 on click: `self.initial_indent -= indent` -> `pass` passed all 2,240
    tests and was certified, and it drops the first-line indent that click's `+=` keeps. A different passing
    program means the suite cannot choose: AMBIGUOUS, and nothing ships until a test tells them apart
    (`fluidnet resolve`). The same program written differently confirms it; the smaller edit ships."""
    import time
    from .certify import certify
    t0 = time.time()
    c = certify(root, rel, patched, python=python or sys.executable)
    if not c.ok:
        return Judged(c.verdict, c.why, c, seconds=round(time.time() - t0, 1))
    original = (Path(root) / rel).read_text(encoding="utf-8")
    lines = _changed_lines(original, patched)
    if not fluidfix_has_focus():                           # a check that did not run is never a pass
        return Judged("NOT-CHECKED", "certified; uniqueness not checked — this fluidfix has no `repair --focus`",
                      c, patched, seconds=round(time.time() - t0, 1))
    order = order if order is not None else score(root, nets)
    twins, errors = [], []
    for s in sorted(order, key=lambda n: hits_in_scope(n.dictionary, root, rel, lines)):
        o = repair_file(root, s.dictionary, rel, False, python, focus=lines)
        if o.status == "repaired" and o.patched:
            if not _same_program(o.patched, patched):
                return Judged("AMBIGUOUS", f"{Path(s.dictionary).name} writes a different program at "
                              f"{rel}:{','.join(map(str, lines))} that also passes the full suite — the tests "
                              f"cannot choose; add one that tells them apart", c, None, o.patched,
                              s.dictionary, round(time.time() - t0, 1))
            twins.append((s.dictionary, o.patched))
        elif o.status == "error":
            errors.append(Path(s.dictionary).name)
    if twins:
        net, text = min(twins, key=lambda t: _edit_size(original, t[1]))
        ship = text if _edit_size(original, text) < _edit_size(original, patched) else patched
        return Judged("CONFIRMED", f"certified, and {Path(net).name} writes the same program", c, ship,
                      seconds=round(time.time() - t0, 1))
    if errors:
        return Judged("NOT-CHECKED", f"certified; uniqueness not checked — {', '.join(errors)} errored", c,
                      patched, seconds=round(time.time() - t0, 1))
    return Judged("UNIQUE", "certified, and no other program at its lines passes", c, patched,
                  seconds=round(time.time() - t0, 1))


def watch_with_buggy(root, nets: list[str], commit: bool = False, python: str | None = None,
                     jobs: int = 1, mutate_seconds: int = 240, top_files: int = 3, fallback: bool = True,
                     file_budget: int = 600, hive: bool = True, lead: dict | None = None,
                     body=None, mode: str = "thrift", learned: str | None = None, asks: int = 2) -> dict:
    """buggy locates; fluidnet certifies buggy's proposals, then each net repairs with the file named.
    Falls back to the blind search only when buggy is absent or names no file."""
    import time
    from .certify import certify
    t0 = time.time()
    stages, outcomes = [], []
    order = score(root, nets)
    focused = fluidfix_has_focus()
    budget = file_budget if file_budget and fluidfix_has_budget() else None

    def done(winner):
        return {"order": order, "outcomes": outcomes, "winner": winner, "stages": stages, "leads": leads,
                "seconds": round(time.time() - t0, 1)}

    def certify_buggys_repairs(lds):
        """The recursive half: a patch fluidnet did not write, judged like fluidnet's own — certified, and the
        only program at its line (see judge_outside_fix)."""
        for rep in lds.repairs:
            patched = apply_repair(root, rep)
            if patched is None:
                continue
            j = judge_outside_fix(root, rep["file"], patched, nets, python, order)
            cv = j.certificate.verdict if j.certificate is not None else j.verdict
            stages.append(("certify buggy's repair", j.certificate.seconds if j.certificate is not None else 0,
                           f"{cv}: {rep['file']}:{rep['line']} {rep.get('edit', '')}"))
            if j.certificate is None or not j.certificate.ok:
                continue
            stages.append(("is buggy's repair the only fix at its line?",
                           round(j.seconds - j.certificate.seconds, 1),
                           {"AMBIGUOUS": f"AMBIGUOUS: {Path(j.rival_net).name} writes a different program that also passes",
                            "CONFIRMED": "confirmed: a net writes the same program",
                            "UNIQUE": "no other fix at this line passes"}.get(j.verdict,
                           f"NOT CHECKED — {j.why}; shipped on certification alone")))
            if j.verdict == "AMBIGUOUS":
                import difflib
                f = Path(root) / rep["file"]
                rival = "".join(difflib.unified_diff(f.read_text(encoding="utf-8").splitlines(True),
                                                     j.rival.splitlines(True), f"a/{rep['file']}", f"b/{rep['file']}", n=1))
                outcomes.append(Outcome("ambiguous", "ambiguous",
                                        f"two different fixes at {rep['file']}:{rep['line']} both pass the full suite — the "
                                        f"tests cannot choose; add one that tells them apart\n"
                                        f"  buggy:  {rep['now'].strip()}\n  {Path(j.rival_net).name}:\n{rival}", 2, j.rival))
                ambiguous_pair[:] = [patched, j.rival]; ambiguous_file[:] = [rep["file"]]
                return "AMBIGUOUS"
            f = Path(root) / rep["file"]
            original = f.read_text(encoding="utf-8")
            who = ("buggy (certified by fluidnet)" if j.ship == patched else
                   "buggy located, a net wrote the same program (certified by fluidnet)")
            if commit:
                f.write_text(j.ship, encoding="utf-8")
                _commit(root, rep["file"], f"fluidnet: certified repair {rep['file']}:{rep['line']} ({who})")
            import difflib
            diff = "".join(difflib.unified_diff(original.splitlines(True), j.ship.splitlines(True),
                                                f"a/{rep['file']}", f"b/{rep['file']}", n=1))
            outcomes.append(Outcome(who, "repaired", diff, 0, j.ship))
            return who
        return None

    # The taught nets, searching only the files buggy named.
    # Proving a fix unique means judging every candidate in scope. With the whole file as scope, a broad taught
    # class in a big file is thousands of candidates (a sibling-attribute bug in click's core.py: 35 min, then
    # refused). With buggy's lines as scope the same bug shipped exactly in 165 s. So: buggy's lines first,
    # the certificate stating that scope; the whole file only if nothing in them ships.
    # Which net first? Not the one that recognises most of the repository: measured 2026-09-25 on click, the
    # broad sibling-attribute net went first on the whole of termui.py and was still proving uniqueness after
    # 49 minutes, while the net that owns the bug's shape repairs it in 45 s. A net's cost in a scope is its
    # signal hits THERE, so for each of buggy's files, in buggy's order, the nets run cheapest first: a narrow
    # net that is wrong refuses in seconds, and a broad one runs only after. No net is skipped — every net also
    # carries fluidfix's shipped classes, so zero hits of its own is still a search.
    # And how long in each whole file? Bounded. Measured 2026-09-25 on click: buggy's leads went to core.py for
    # a bug in _textwrap.py and one net's whole-file search there ran 38 minutes before anything else could
    # look. Past the budget the loop stops between candidate sets, the file untouched, ruling RAISE_BUDGET —
    # never a guess; the same 600 s the guard gives its escalation. buggy's focus is small: unbounded.
    def rival_at(rel, patched, besides):
        """Every fix obeys one law, whoever found it: no OTHER net may write a different passing program at the
        lines it touches. Measured 2026-09-25 on click core.py:1877: a boolean-operator net writes `and` there, a
        sibling-attribute net writes `context_settings`, both pass all 2,240 tests — whichever net ran first
        would have shipped, by the order of a loop. Returns (net, text) for a rival, else None."""
        original = (Path(root) / rel).read_text(encoding="utf-8")
        lines = _changed_lines(original, patched)
        t1 = time.time()
        for s in sorted(order, key=lambda n: hits_in_scope(n.dictionary, root, rel, lines)):
            if s.dictionary == besides:
                continue
            o = repair_file(root, s.dictionary, rel, False, python, focus=lines)
            if o.status == "repaired" and o.patched and not _same_program(o.patched, patched):
                stages.append((f"is the fix the only one at {rel}:{','.join(map(str, lines))}?", round(time.time() - t1, 1),
                               f"AMBIGUOUS: {Path(s.dictionary).name} writes a different program that also passes"))
                return s.dictionary, o.patched
        stages.append((f"is the fix the only one at {rel}:{','.join(map(str, lines))}?", round(time.time() - t1, 1),
                       "yes: no other net writes a different passing program there"))
        return None

    def nets_on(lds, scope, who="buggy's focus"):
        for rel in lds.files:
            focus = lds.lines.get(rel) if scope == "focus" else None
            if scope == "focus" and not focus:
                continue
            for s in sorted(order, key=lambda n: hits_in_scope(n.dictionary, root, rel, focus)):
                t1 = time.time()
                # nothing is committed on one loop's word: certified (for a focus), and unique across the nets
                o = repair_file(root, s.dictionary, rel, False, python, focus=focus,
                                budget=budget if scope == "file" else None)
                outcomes.append(o)
                stages.append((f"repair {rel} ({Path(s.dictionary).name}, {scope})", round(time.time() - t1, 1), o.status))
                if o.status != "repaired":
                    continue
                if scope == "focus":
                    # a lead HELPED find it — so fluidnet certifies it, independently, before the help counts.
                    # Only a CERTIFIED fix goes ahead; otherwise the lead is rejected and the search goes on as if
                    # it had never been given.
                    c = certify(root, rel, o.patched, python=python or sys.executable)
                    stages.append((f"certify the fix {who} found", c.seconds, c.verdict))
                    if not c.ok:
                        o.status = "rejected"
                        continue
                    o.output += "\ncertified by fluidnet: red before, green on the full suite, stable, nothing else broken"
                if focused:
                    rival = rival_at(rel, o.patched, s.dictionary)
                    if rival is not None:
                        import difflib
                        net2, text2 = rival
                        f = Path(root) / rel
                        d2 = "".join(difflib.unified_diff(f.read_text(encoding="utf-8").splitlines(True), text2.splitlines(True),
                                                          f"a/{rel}", f"b/{rel}", n=1))
                        outcomes.append(Outcome("ambiguous", "ambiguous",
                                                f"two different fixes at {rel} both pass the full suite — the tests cannot "
                                                f"choose; add one that tells them apart\n  {Path(s.dictionary).name}:\n{o.output}"
                                                f"\n  {Path(net2).name}:\n{d2}", 2, text2))
                        ambiguous_pair[:] = [o.patched, text2]; ambiguous_file[:] = [rel]
                        return "AMBIGUOUS"
                if commit:
                    (Path(root) / rel).write_text(o.patched, encoding="utf-8")
                    _commit(root, rel, f"fluidnet: repair {rel} ({Path(s.dictionary).name}, {scope}, unique across the nets)")
                return s.dictionary
        return None

    ambiguous_pair: list = []
    ambiguous_file: list = []

    def ask_body(kind, prompt):
        r = body.ask(kind, prompt, root)
        stages.append((f"body: {kind}", r.seconds, (f"{r.tokens:,} tokens" if r.tokens is not None else "tokens not reported")
                       + ("" if r.ok else f" · failed: {r.error[:80]}")))
        return r

    def ambiguous():
        """Two different programs pass. The core cannot choose — so, with a body, it asks the AI agent, used only as
        an ORACLE, for one fact: a test, or NO-DIFFERENCE with a probe. The core MEASURES that fact (the test run
        under each program twice; the probe run under each, twice, under coverage) and the EQUIV law rules on the
        measurement: REFUSE, SHIP_A, SHIP_B, or ASK again — within a budget of `asks`. The oracle's words decide
        nothing. Measured 2026-09-25 on click: a test separated `and` from `self.context_settings` (shipped), and a
        correct NO-DIFFERENCE with no way to weigh it was refused — the case this law exists for."""
        if body is None or len(ambiguous_pair) != 2 or not ambiguous_file:
            r = done(None); r["status"] = "ambiguous"; r["candidates"] = list(ambiguous_pair)
            return r
        from . import body as B
        from .equiv import equiv, situation, VERDICTS, SHIP_A, SHIP_B, REFUSE
        from .resolve import measure_test, measure_probe
        import difflib
        rel = ambiguous_file[0]; A, Bc = ambiguous_pair
        f = Path(root) / rel; original = f.read_text(encoding="utf-8")
        same = _same_program(A, Bc)
        smaller_a = _edit_size(original, A) <= _edit_size(original, Bc)
        feedback, test_rel = "", None
        for n in range(1, asks + 1):
            last = n == asks
            kind, e1, e2, stable, test_rel, note = 0, False, False, False, None, "no usable answer"
            if not same:
                r = ask_body(f"the oracle (ask {n} of {asks})", B.pin_prompt(root, rel, ambiguous_pair, ["A", "B"]) + feedback)
                code, nd = B.parse_code(r.text), B.no_difference(r.text)
                if nd and code:
                    m = measure_probe(root, rel, ambiguous_pair, code, python=python or sys.executable)
                    kind, e1, e2, stable = 2, m["covers"], m["equal"], m["stable"]
                    note = (f"a probe: {'reached every differing line' if e1 else 'missed differing lines'}, "
                            f"{'identical' if e2 else 'different'} output, {'stable' if stable else 'unstable'}"
                            + (f" — {m['detail']}" if m["detail"] else ""))
                elif code:
                    k = 0
                    while (Path(root) / "tests" / f"test_fluidnet_pin{k or ''}.py").exists():
                        k += 1
                    test_rel = f"tests/test_fluidnet_pin{k or ''}.py"
                    (Path(root) / "tests").mkdir(exist_ok=True)
                    (Path(root) / test_rel).write_text(code, encoding="utf-8")
                    m = measure_test(root, rel, ambiguous_pair, test_rel, python=python or sys.executable)
                    kind, (e1, e2), stable = 1, m["pass"], m["stable"]
                    note = (f"a test: passes under A {e1}, under B {e2}, {'stable' if stable else 'flips on a re-run'}")
            x = situation(same, kind, e1, e2, smaller_a, last, stable); v = equiv(x)
            stages.append(("the EQUIV law", 0.0, f"x={x} · {note} · smaller edit {'A' if smaller_a else 'B'}"
                                                 f"{' · last ask' if last else ''} -> {VERDICTS[v]}"))
            if v in (SHIP_A, SHIP_B):
                win = A if v == SHIP_A else Bc
                if kind == 1:                   # the test becomes part of the suite: certify with it included
                    c = certify(root, rel, win, python=python or sys.executable)
                    stages.append(("certify with the oracle's test included", c.seconds, c.verdict))
                    if not c.ok:
                        (Path(root) / test_rel).unlink(missing_ok=True)
                        break
                keep = [rel] + ([test_rel] if kind == 1 else [])
                if commit:
                    f.write_text(win, encoding="utf-8")
                    why = {0: "the same program written twice; the smaller edit", 1: f"a new test ({test_rel}) seen to separate the two",
                           2: "a probe that reached every differing line printed identical output under both; the smaller edit"}[kind]
                    subprocess.run(["git", "add", "--", *keep], cwd=root, capture_output=True)
                    subprocess.run(["git", "commit", "-q", "-m", f"fluidnet: repair {rel} — the EQUIV law chose it: {why}",
                                    "--", *keep], cwd=root, capture_output=True)
                elif test_rel:
                    (Path(root) / test_rel).unlink(missing_ok=True)
                outcomes.append(Outcome("equiv", "repaired", "".join(difflib.unified_diff(
                    original.splitlines(True), win.splitlines(True), f"a/{rel}", f"b/{rel}", n=1)), 0, win))
                return done(f"the EQUIV law ({VERDICTS[v]}) on the oracle's " + {0: "nothing — one program",
                            1: "test", 2: "probe"}[kind])
            if test_rel:
                (Path(root) / test_rel).unlink(missing_ok=True)
            if v == REFUSE:
                break
            feedback = (f"\n\nYour previous answer was measured: {note}. Answer again — the engine only ships what it "
                        f"can measure.")
        r = done(None); r["status"] = "ambiguous"; r["candidates"] = list(ambiguous_pair)
        return r

    def learn(where: dict):
        """Nothing shipped: no net knows this shape. With a body, the core asks for VOCABULARY — a rule and its
        property, never the fix — saves it as a learned net, and searches the lead again with it. The rule stays:
        every later bug of this shape is the core's alone, 0 tokens."""
        if body is None or not where:
            return None
        from . import body as B
        r = ask_body("vocabulary for a shape no net knows", B.vocabulary_prompt(root, python or sys.executable, where))
        code = B.parse_code(r.text)
        if not code:
            return None
        d = Path(learned) if learned else Path(root) / ".fluidnet" / "learned"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"learned_{time.strftime('%Y%m%d_%H%M%S')}.py"
        f.write_text(code, encoding="utf-8")
        stages.append(("learned net saved", 0.0, str(f)))
        order.append(NetScore(str(f), 1, 0, []))
        won = nets_on(Leads(files=list(where), lines=where, status="red"), "focus", who="the learned rule's")
        return won

    # Round zero: a lead handed in — by a person, or by an agent working as the core's body — is DATA, not a
    # decision: {file: [lines]}. The core searches there with its own nets, certifies what it finds, and proves it
    # is the only fix across the nets; buggy runs only if the lead leads nowhere. Measured 2026-09-25 on click:
    # buggy's locating was ~260 s of the core's median 367 s, and an agent points at the line in seconds.
    leads = Leads(status="red")
    if body is not None and mode == "speed" and not lead:
        from . import body as B
        r = ask_body("point at the fault", B.point_prompt(root, python or sys.executable))
        lead = B.parse_lead(r.text) or None
    if lead and focused:
        leads = Leads(files=list(lead), lines={f: sorted(int(x) for x in ls) for f, ls in lead.items()}, status="red")
        stages.append(("lead handed in", 0.0, "; ".join(f"{f}:{','.join(map(str, ls))}" for f, ls in leads.lines.items())))
        won = nets_on(leads, "focus", who="the lead")
        if won == "AMBIGUOUS":
            return ambiguous()
        if won:
            return done(won)
        stages.append(("the lead led nowhere", 0.0, "buggy locates, as if no lead had been given"))
    leads = buggy_leads(root, python, jobs, mutate_seconds, top_files)
    # buggy's status contract: green (pytest exited 0), red, or harness (the suite could not be judged —
    # nothing collected, a collection or internal error, a killed run). harness means DO NOTHING: it is not
    # green, and a blind search over a suite that cannot be judged would only produce refusals.
    # green is pytest's own exit 0: nothing to do. harness is buggy's word that IT could not judge the suite —
    # and buggy only ever helps, so its verdict never stops fluidnet from judging for itself. Measured
    # 2026-09-24 on click: parametrized test ids with spaces (`[no-wrap mark-sentence < max]`) made buggy
    # read zero failing tests out of a red suite and answer `harness` in 0 s. fluidnet's own guard has its own
    # harness check; a suite that truly cannot be judged still gets nothing attempted there.
    if leads is not None and leads.status == "green":
        return {"order": [], "outcomes": [], "winner": None, "leads": leads, "seconds": round(time.time() - t0, 1),
                "stages": stages + [("locate (buggy)", round(leads.seconds, 1), "suite green — nothing to do")],
                "status": "green"}
    if leads is None or not leads.files:
        why = ("buggy is not installed" if leads is None else
               "buggy could not judge the suite (harness)" if leads.status == "harness" else
               f"buggy named no file ({leads.status or 'no evidence'})")
        r = watch(root, nets, commit, python)
        r.update(stages=stages + [("locate", 0.0, why + " — fluidnet searches alone")], leads=leads, seconds=round(time.time() - t0, 1))
        return r
    stages.append(("locate (buggy)", round(leads.seconds, 1),
                   f"files {', '.join(leads.files)}; {len(leads.repairs)} proposed repair(s)"
                   + (f"; introduced by {leads.commit[:8]}" if leads.commit else "")))
    # Round one: buggy as asked — its own repairs certified, then its lines.
    won = certify_buggys_repairs(leads)
    if won == "AMBIGUOUS":
        return ambiguous()
    won = won or (focused and nets_on(leads, "focus"))
    if won == "AMBIGUOUS":
        return ambiguous()
    if won:
        return done(won)
    # Round two: more buggies when the target is bigger than the first run could measure. buggy says how much it
    # left unmeasured, and silence is not innocence: measured 2026-09-25 on click, one worker and 240 s measured
    # 47 lines and cut 1,130, and the bug's file was among the cut — its ranking was partial evidence, and the
    # nets took it as a verdict. So the hive is redeployed, sized from buggy's own rate to cover the target.
    if hive and leads.cut > 0:
        j, secs, muts = hive_size(leads)
        t1 = time.time()
        big = buggy_leads(root, python, j, secs, top_files, timeout=secs + 900, mutants=muts)
        what = (f"measured {big.measured} of {big.measured + big.cut} lines; files {', '.join(big.files)}; "
                f"{len(big.repairs)} proposed repair(s)" if big and big.files else "no files")
        stages.append((f"locate (buggy hive: {j} workers, {secs} s; first run cut {leads.cut} of "
                       f"{leads.measured + leads.cut} lines)", round(time.time() - t1, 1), what))
        if big is not None and big.status == "red" and big.files:
            leads = big
            won = certify_buggys_repairs(leads)
            if won == "AMBIGUOUS":
                return ambiguous()
            won = won or (focused and nets_on(leads, "focus"))
            if won == "AMBIGUOUS":
                return ambiguous()
            if won:
                return done(won)
    # Round three: the whole of each of buggy's files, each net bounded.
    won = nets_on(leads, "file")
    if won == "AMBIGUOUS":
        return ambiguous()
    if won:
        return done(won)
    # buggy's help led nowhere: drop it, and let fluidnet search on its own, as if buggy had never spoken.
    # Measured 2026-09-24 on click: buggy named core.py, formatting.py and testing.py for a bug in
    # _textwrap.py; the nets refused all three and, with no fallback, the answer was a refusal that
    # fluidnet's own search — the file named — reaches exactly in 89 s.
    if fallback:
        t2 = time.time()
        # the blind search is bounded the same way: measured 2026-09-25, with buggy's files exhausted the first
        # net's unbounded guard pass on click was still running when the 90-minute harness cap ended it.
        blind = watch(root, nets, commit, python, extra=["--budget", str(file_budget)] if file_budget else None)
        stages.append(("buggy's files exhausted — fluidnet searches alone", round(time.time() - t2, 1),
                       f"winner: {blind['winner']}" if blind["winner"] else "refused"))
        if not blind["winner"] and body is not None:
            won = learn(lead or {f: leads.lines.get(f, [])[:3] for f in leads.files[:1] if leads.lines.get(f)})
            if won == "AMBIGUOUS":
                return ambiguous()
            if won:
                return done(won)
        blind.update(stages=stages, leads=leads, seconds=round(time.time() - t0, 1))
        return blind
    if body is not None:
        won = learn(lead or {f: leads.lines.get(f, [])[:3] for f in leads.files[:1] if leads.lines.get(f)})
        if won == "AMBIGUOUS":
            return ambiguous()
        if won:
            return done(won)
    return {"order": order, "outcomes": outcomes, "winner": None, "stages": stages, "leads": leads,
            "seconds": round(time.time() - t0, 1)}
