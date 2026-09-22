"""The MCP server, spoken to over stdio as a real client would: initialize, list tools, call gate."""
import json, subprocess, sys, textwrap
import pytest
pytest.importorskip("mcp")


def rpc(proc, msg):
    proc.stdin.write(json.dumps(msg) + "\n"); proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise RuntimeError("server closed")
        if line.startswith("{"):
            d = json.loads(line)
            if "id" in d and d["id"] == msg.get("id"):
                return d


def test_tools_over_stdio(repo_factory):
    root = repo_factory("def f(x):\n    return x + 2\n", "from pkg.mod import f\n\ndef test_f():\n    assert f(1) == 2\n")
    proc = subprocess.Popen([sys.executable, "-m", "fluidnet.cli", "mcp"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        r = rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        assert r["result"]["serverInfo"]["name"] == "fluidnet"
        proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); proc.stdin.flush()
        r = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert {t["name"] for t in r["result"]["tools"]} == {"gate", "certify", "propose"}
        r = rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {
            "name": "gate", "arguments": {"root": str(root), "file": "pkg/mod.py", "patched": "def f(x):\n    return x + 1\n"}}})
        text = r["result"]["content"][0]["text"]
        assert '"verdict": "ALLOW"' in text or "'verdict': 'ALLOW'" in text
    finally:
        proc.kill()
