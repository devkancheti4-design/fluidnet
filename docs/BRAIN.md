# fluidnet as the code-action gate — an integration for truth layers like Brain (theup.io)

A truth layer for AI agents gates *queries and actions on facts*: one call before the action, a
deterministic ALLOW / WARN / BLOCK, evidence attached, an audit trail. Brain's Query Gate is that:
`POST /gate/query → ALLOW | WARN | BLOCK`, and its action classes are `read: passthrough`,
`write: validate`, `commit: require_approval`.

Nothing in that stack can judge a **patch**. When the agent's action is "change this file", a knowledge
graph has no opinion — the only judges of a code change are the repository's own test suite and a
property of the rewrite. fluidnet is those two judges behind the same verdict vocabulary.

```
fluidnet gate <root> --file <rel> --patch <file> [--dictionary rules.py]
    ALLOW   certified: red before, green after on the FULL suite, stable on re-check, nothing else
            broken, file restored byte-exact — and no class property refutes it
    BLOCK   a class property refuted it (with the refuting input, before any suite run), or the suite
            did: it fails, it breaks a passing test, or it goes green only sometimes
    WARN    the suite cannot judge — nothing was red, or it could not run
```

Every verdict carries the certificate, the property findings, the suite-run count, and the rollback
check. The patch is never left applied.

## Over MCP — the interface both sides speak

```
pip install 'fluidnet[mcp]'
fluidnet mcp            # stdio; three tools
```

| tool | what it answers |
|---|---|
| `gate(root, file, patched, dictionary?)` | ALLOW / WARN / BLOCK with evidence |
| `certify(root, file, patched)` | the certificate |
| `propose(root, dictionary?)` | what fluidfix would repair right now, as a diff, tree restored |

Any MCP runtime can mount it. In Brain's terms: route `write` actions on source files to `fluidnet.gate`,
ledger the verdict and its evidence, and let `commit` require ALLOW.

## The recursive test: patches models wrote, judged by the gate

`examples/brain/replay_gate.py`. Every broken program was written by a small model from prose; every
correct patch by a *different* model, a whole-function rewrite no line vocabulary could author; the
adversarial classes are generated mechanically. fluidnet contributed nothing but the judgment.

| class of patch | ALLOW | BLOCK | expected |
|---|---|---|---|
| correct, by another model | **14** | 0 | ALLOW |
| another model's wrong attempt | 0 | **9** | BLOCK |
| correct, but green only sometimes | 0 | **14** | BLOCK |
| fixes the red test, breaks a green one | 0 | **6** | BLOCK |
| correct on everything the suite can see, different beyond it | 27 | 0 | ALLOW — the suite cannot tell, and the certificate says how far it looked |
| a lookup table on the suite's exact inputs | 14 | 0 | **ALLOW — the hole** |

84 patches, no per-case tuning. The last row is the honest one: a suite-only gate cannot distinguish an
overfit table from a solution, because every input the suite mentions is in the table. That is exactly
what a class property is for — but a property speaks about a *rewrite* of a taught shape, not a
whole-function replacement. The gate names the limit rather than hiding it.

Where a property does apply, it is the difference. `tests/test_gate.py`: a suite that only asks `k = 1`
ALLOWs `int(k * len(text) - 1)`; with the class property loaded the same patch is **BLOCKed at zero suite
runs** with the refuting input `{'__L': 1, 'k': 2}`. rich's real suite accepted that exact line.

## What this does and does not claim

- Same conviction as a truth layer — don't let AI check its own work; deterministic verdict, not an LLM
  opinion; fail closed; everything on record. Different object: a patch, not a fact.
- No model anywhere in fluidnet's loop. Brain routes contested queries to models; fluidnet's judges are
  the suite and algebra.
- Bounded proofs, stated in the certificate. A suite is a finite set of examples; the overfit row above is
  the proof of that.
- A property has to be taught, once per shape, by someone who understands the shape.
