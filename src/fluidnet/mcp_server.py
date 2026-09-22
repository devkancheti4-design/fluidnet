# SPDX-License-Identifier: AGPL-3.0-or-later
"""fluidnet as an MCP server — three tools any MCP runtime can call.

    gate(root, file, patched, dictionary?)   ALLOW / WARN / BLOCK for a proposed change, with evidence
    certify(root, file, patched)             the certificate itself
    propose(root, dictionary?)               what fluidfix would repair right now, as a unified diff, tree restored

Needs the optional extra:  pip install 'fluidnet[mcp]'   then   fluidnet mcp   (stdio)."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import asdict
from pathlib import Path


def build():
    try:                                            # mcp >= 2: FastMCP was renamed
        from mcp.server.mcpserver import MCPServer as FastMCP
    except ImportError:
        try:                                        # mcp 1.x
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            raise SystemExit("the MCP server needs the optional extra:  pip install 'fluidnet[mcp]'")
    from .certify import certify as _certify
    from .gate import gate as _gate
    from .overseer import fluidfix_bin

    app = FastMCP("fluidnet")

    @app.tool()
    def gate(root: str, file: str, patched: str, dictionary: str | None = None) -> dict:
        """ALLOW, WARN or BLOCK a proposed new content for `file` under `root`, judged by the repository's
        own test suite and any taught class property. The patch is never left applied."""
        return _gate(root, file, patched, dictionary)

    @app.tool()
    def certify(root: str, file: str, patched: str) -> dict:
        """Certify a patch: red before, green after on the full suite, stable on re-check, nothing else
        broken, file restored byte-exact. Returns the certificate."""
        return asdict(_certify(root, file, patched))

    @app.tool()
    def propose(root: str, dictionary: str | None = None) -> dict:
        """What fluidfix would repair in this repository right now: the unified diff of the first
        certified candidate, with the tree restored byte-exact. Nothing is written."""
        cmd = [fluidfix_bin(), "guard", root, "--dry-run"] + (["--dictionary", dictionary] if dictionary else [])
        r = subprocess.run(cmd, capture_output=True, text=True)
        patch = Path(root) / ".fluidfix" / "proposed.patch"
        return {"exit": r.returncode, "output": (r.stdout + r.stderr).strip(),
                "diff": patch.read_text() if patch.exists() and r.returncode == 0 else ""}

    return app


def main() -> int:
    build().run()
    return 0
