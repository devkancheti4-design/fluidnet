# Note to The Up (theup.io) — not sent; for you to send if you want to

Subject: a code-action gate that speaks Brain's verdicts

Hi — Brain's premise is the right one: don't let AI check its own work, deterministic verdict, evidence,
ledger. Your Query Gate returns ALLOW / WARN / BLOCK for actions on facts. There's one action class it
can't judge: when the agent's action is *change this file*. A knowledge graph has no opinion on a patch.

I built the judge for that, open source, AGPL: **fluidnet** — https://github.com/devkancheti4-design/fluidnet

    fluidnet gate <repo> --file <path> --patch <file>   →  ALLOW | WARN | BLOCK, with evidence
    fluidnet mcp                                        →  the same as MCP tools (gate / certify / propose)

ALLOW means: red before, green after on the full suite, stable on re-run, nothing else broken, file restored
byte-exact — and no taught property of the rewrite refutes it. No model in the loop.

Replayed on 84 patches small models wrote — correct ones by one model, adversarial ones (wrong, flaky,
collateral, overfit) generated from another: 14/14 correct ALLOWed, 29/29 adversarial BLOCKed, and the
overfit lookup tables ALLOWed — the hole any suite-only gate has, which we name rather than hide.
Where a class property applies, it BLOCKs a wrong fix a weak suite accepts, at zero test runs.

If Brain routed `write` actions on source files to this gate and ledgered the verdict, you'd have the one
action class with no deterministic judge covered. Happy to wire it against your MCP surface. Write-up:
https://github.com/devkancheti4-design/fluidnet/blob/main/docs/BRAIN.md
