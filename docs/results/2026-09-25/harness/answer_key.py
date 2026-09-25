"""The maintainers' commit 08a0d69 as an answer key: {(file, old line): set of lines added in that hunk}."""
import re, subprocess
def answer_key(repo, a="08a0d69^", b="08a0d69", path="src/click"):
    diff = subprocess.run(["git", "-C", repo, "diff", "-U0", a, b, "--", path], capture_output=True, text=True).stdout
    key, f, hunk = {}, None, None
    for l in diff.splitlines():
        if l.startswith("--- a/"): f = l[6:]
        elif l.startswith("@@"):
            ln = int(re.match(r"@@ -(\d+)", l).group(1)); hunk = {"removed": [], "added": set()}
        elif l.startswith("-") and not l.startswith("---"):
            hunk["removed"].append(ln); key[(f, ln)] = hunk; ln += 1
        elif l.startswith("+") and not l.startswith("+++"):
            hunk["added"].add(l[1:].strip())
    return key
