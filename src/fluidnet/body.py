# SPDX-License-Identifier: AGPL-3.0-or-later
"""The body — an AI agent working as the core's suit. It never decides and never touches the tree.

fluidnet is the core: it locates (buggy), generates, judges, fixes and proves. When it lacks a fact it asks the
body for DATA, as text, and does every file operation itself:

    POINT        "where is the fault?"                 -> LEAD: src/pkg/x.py:12[,14]
    PIN          "two fixes pass — which input tells    -> one pytest file in a ```python block
                  them apart?"                            (or NO-DIFFERENCE: why)
    VOCABULARY   "no net knows this shape"              -> a dictionary file (rule + property) in a ```python block

A request carries every fact the body needs (the failure, the source around it, the candidates), so a body needs
no tools and pays no search: text in, text out. The body is any command that reads the request on stdin and
prints the reply — `claude -p --output-format json` reports its token usage, and any other agent or a person
at a prompt will do. Measured 2026-09-25 on click: an agent runtime spent ~47,000 tokens just to point at a line
it found by reading, and one to three calls per ten bugs is all the token-saving mode asks for."""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Reply:
    text: str = ""
    tokens: int | None = None      # input + output + cache, when the body reports usage
    seconds: float = 0.0
    ok: bool = True
    error: str = ""


class Body:
    def __init__(self, cmd: str, timeout: int = 600):
        self.cmd, self.timeout = cmd, timeout
        self.calls: list[tuple[str, Reply]] = []

    def ask(self, kind: str, prompt: str, cwd) -> Reply:
        t0 = time.time()
        try:
            p = subprocess.run(shlex.split(self.cmd), input=prompt, cwd=str(cwd), capture_output=True, text=True,
                               timeout=self.timeout)
            raw = p.stdout
            r = Reply(raw.strip(), ok=p.returncode == 0, error=(p.stderr or "")[-300:])
        except (OSError, subprocess.TimeoutExpired) as e:
            r = Reply("", ok=False, error=str(e)[:300])
            raw = ""
        try:                                                    # `claude -p --output-format json`
            d = json.loads(raw)
            if isinstance(d, dict) and "result" in d:
                u = d.get("usage") or {}
                r.text = str(d.get("result") or "")
                r.tokens = sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                                             "cache_creation_input_tokens", "cache_read_input_tokens"))
                r.ok = r.ok and not d.get("is_error")
        except (ValueError, TypeError):
            pass
        r.seconds = round(time.time() - t0, 1)
        self.calls.append((kind, r))
        return r


# ------------------------------------------------------------------ the facts a request carries

def _snippet(root, rel: str, line: int, around: int = 8) -> str:
    try:
        L = (Path(root) / rel).read_text(encoding="utf-8").split("\n")
    except OSError:
        return ""
    a, b = max(1, line - around), min(len(L), line + around)
    return "\n".join(f"{n:>5} | {L[n - 1]}" for n in range(a, b + 1))


def failure_facts(root, python: str, limit: int = 6000) -> tuple[str, list[tuple[str, int]]]:
    """The first failure, short traceback, and the source frames under the project it passes through."""
    p = subprocess.run([python, "-m", "pytest", "-x", "-q", "-p", "no:cacheprovider", "--tb=short", "--no-header"],
                       cwd=str(root), capture_output=True, text=True)
    text = p.stdout
    m = re.search(r"^=+ (FAILURES|ERRORS) =+$", text, re.M)       # the failure itself, not the progress dots
    out = (text[m.start():] if m else text)[:limit]
    frames = []
    for f, ln in re.findall(r"^([\w./-]+\.py):(\d+)", out, re.M):
        if not f.startswith(("tests/", "test/")) and "site-packages" not in f and (Path(root) / f).exists():
            if (f, int(ln)) not in frames:
                frames.append((f, int(ln)))
    return out, frames[-4:]


def point_prompt(root, python: str) -> str:
    out, frames = failure_facts(root, python)
    src = "\n\n".join(f"--- {f} around line {ln}\n{_snippet(root, f, ln)}" for f, ln in frames)
    return ("You point at code for a repair engine that decides and fixes everything itself. Do not fix anything.\n"
            "From the failing test output and source below, name the source line(s) where the fault most likely is "
            "(at most 3 lines, at most 2 files, never a test file).\n\n"
            f"FAILING TEST OUTPUT\n{out}\n\nSOURCE\n{src}\n\n"
            "Reply with only: LEAD: <path>:<line>[,<line>]   (one LEAD line per file, paths as shown above)")


def pin_prompt(root, rel: str, candidates: list[str], names: list[str]) -> str:
    import difflib
    original = (Path(root) / rel).read_text(encoding="utf-8")
    diffs = "\n".join(f"--- candidate {n}\n" + "".join(difflib.unified_diff(original.splitlines(True), c.splitlines(True),
                                                                             f"a/{rel}", f"b/{rel}", n=6))
                      for n, c in zip(names, candidates))
    return ("You supply ONE test to a repair engine that decides everything itself. Do not choose in words.\n"
            f"Two different fixes to {rel} both pass the project's entire existing test suite:\n\n{diffs}\n\n"
            "If some concrete input makes the code behave differently under them, reply with ONE complete pytest file "
            "in a single ```python block, whose test passes under the correct fix and fails under the other (import "
            "the package as the existing tests do). If no input can tell them apart, reply only: "
            "NO-DIFFERENCE: <one sentence why>")


def vocabulary_prompt(root, python: str, lead: dict) -> str:
    out, _ = failure_facts(root, python)
    src = "\n\n".join(f"--- {f} around line {ln}\n{_snippet(root, f, ln, 12)}" for f, ls in lead.items() for ln in ls[:2])
    return ("You teach a repair engine a CLASS of fault; it generates, judges and applies every fix itself. Do not "
            "write the fix. The engine has no class for the fault behind this failure.\n\n"
            f"FAILING TEST OUTPUT\n{out}\n\nSOURCE\n{src}\n\n"
            "Reply with ONE Python file in a single ```python block, written generally so it covers every occurrence "
            "of this KIND of fault in any code. The names re, register, teach_property and SpanEdit are provided:\n"
            "  _SIG = re.compile(r'...')                      # lines that can show the fault\n"
            "  def rewrite(line, o): return [ ...candidates ] # o.all_lines, o.lineno (1-based); a str, or\n"
            "                                                 # SpanEdit(start, end, text) that includes o.lineno\n"
            "  register(4, 'short-name', 'one sentence: the fault', _SIG, rewrite)\n"
            "  def prop(orig, cand): return (ok, why, n_checked)  # what every candidate must keep true\n"
            "  teach_property(4, 'one sentence a maintainer can review', prop)\n"
            "At most ~24 candidates per line.")


# ------------------------------------------------------------------ reading the reply

def parse_lead(text: str) -> dict:
    out = {}
    for f, ls in re.findall(r"LEAD:\s*([\w./-]+\.py):([\d,\s]+)", text or ""):
        nums = [int(x) for x in re.findall(r"\d+", ls)]
        if nums:
            out.setdefault(f, [])
            out[f] += [n for n in nums if n not in out[f]]
    return out


def parse_code(text: str) -> str | None:
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text or "", re.S)
    return m.group(1).rstrip() + "\n" if m else None


def no_difference(text: str) -> str | None:
    m = re.search(r"NO-DIFFERENCE:\s*(.+)", text or "")
    return m.group(1).strip() if m else None
