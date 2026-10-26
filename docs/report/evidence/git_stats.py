"""Repository evidence for Section 7.8 of the report, straight from `git log`.

    python docs/report/evidence/git_stats.py

Writes docs/report/latex/generated/git_stats.tex and results/git.json.
Nothing is typed by hand: author counts, conventional-commit compliance, tags
and branches are all read from the repository.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT_TEX = ROOT / "docs" / "report" / "latex" / "generated" / "git_stats.tex"
OUT_JSON = Path(__file__).resolve().parent / "results" / "git.json"

# git identity -> team member. Tanvi pushed from two accounts; Miti's older commits
# used the address miti2109@gmail.com.
MEMBER = {
    "twisshashah@gmail.com": "Twissha Shah",
    "tanvisheth1964@gmail.com": "Tanvi Sheth",
    "tanvisheth1234@gmail.com": "Tanvi Sheth",
    "miti2109@gmail.com": "Miti Shah",
    "mitishah2109@gmail.com": "Miti Shah",
}
ORDER = ["Miti Shah", "Twissha Shah", "Tanvi Sheth"]  # order used throughout the report
CONVENTIONAL = re.compile(r"^(feat|fix|docs|test|chore|refactor|perf|style|build|ci)(\([^)]+\))?!?: .+")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, stdin=subprocess.DEVNULL,
                          encoding="utf-8", errors="replace").stdout


def main() -> None:
    log = [l.split("\x1f") for l in git("log", "--remotes=origin", "--format=%H\x1f%an\x1f%ae\x1f%s").splitlines() if l]
    per_member = Counter(MEMBER.get(email, name) for _, name, email, _ in log)
    per_identity = Counter(f"{name} <{email}>" for _, name, email, _ in log)
    conv = [s for _, _, _, s in log if CONVENTIONAL.match(s)]
    non_conv = [s for _, _, _, s in log if not CONVENTIONAL.match(s)]
    branches = sorted({b.strip().lstrip("*").strip().removeprefix("remotes/").removeprefix("origin/") for b in git("branch", "-r").splitlines()
                       if "HEAD" not in b}, key=lambda b: (b != "main", b))
    tags = git("tag").split()
    total = len(log)
    data = {"commits": total, "per_member": dict(per_member), "per_identity": dict(per_identity),
            "conventional": len(conv), "non_conventional": non_conv, "branches": branches, "tags": tags}
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def esc(t: str) -> str:
        return t.replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("&", r"\&").replace("%", r"\%").replace("#", r"\#")

    rows = "\n".join(f"{esc(m)} & {n} & {100 * n / total:.0f}\\,\\%\\\\" for m, n in sorted(per_member.items(), key=lambda kv: ORDER.index(kv[0]) if kv[0] in ORDER else 99))
    ident = "; ".join(esc(i) for i in per_identity)
    bad = "; ".join("``" + esc(s) + "''" for s in non_conv)
    TT = chr(92) + "texttt{"
    branch_str = ", ".join(TT + esc(b) + "}" for b in branches)
    tag_str = ", ".join(TT + esc(t) + "}" for t in tags) or "none"
    tex = f"""\\begin{{table}}[htbp]
\\caption{{Commits per team member, read from \\texttt{{git log}} over all remote branches ({total} commits)}}
\\label{{tab:commits}}
\\small
\\begin{{tabular}}{{@{{}}lrr@{{}}}}
\\toprule
\\textbf{{Member}} & \\textbf{{Commits}} & \\textbf{{Share}}\\\\ \\midrule
{rows}
\\bottomrule
\\end{{tabular}}
\\end{{table}}
\\textbf{{Conventional Commits.}} {len(conv)} of {total} commits ({100 * len(conv) / total:.0f}\\,\\%) follow the \\texttt{{type(scope): subject}} convention of \\texttt{{CONTRIBUTING.md}}.

\\textbf{{Branches:}} {branch_str}. \\textbf{{Tags:}} {tag_str}.
"""
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    OUT_TEX.write_text(tex, encoding="utf-8")
    print(json.dumps({k: v for k, v in data.items() if k != "non_conventional"}, indent=2))
    print("non-conventional:", non_conv)


if __name__ == "__main__":
    main()
