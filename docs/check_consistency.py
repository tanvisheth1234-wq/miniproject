"""Cross-checks that the project's documents agree with each other and with the code.

    python docs/check_consistency.py

Compares, against one source of truth each:
  * the automated test count         the last fresh pytest run (docs/testing/results/deck_pytest.json)
  * the number of targets met        docs/testing/kpis.py
  * the team's names                 docs/report/latex/students.tex
  * the commit count                 docs/report/evidence/results/git.json
in the README, the contribution log, the report (generated tables and the built PDF), the final deck,
the poster and the testing document. Prints OK / MISMATCH / STALE for each, and exits 1 on any
MISMATCH. STALE means a built file (a PDF) was produced before the numbers it quotes last changed:
rebuild it.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

spec = importlib.util.spec_from_file_location("kpis", DOCS / "testing" / "kpis.py")
kpis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kpis)

results: list[tuple[str, str, str]] = []


def record(status: str, where: str, what: str) -> None:
    results.append((status, where, what))


def pdf_text(path: Path) -> str:
    import pymupdf

    return " ".join(" ".join(p.get_text().split()) for p in pymupdf.open(path))


def pptx_text(path: Path) -> str:
    from pptx import Presentation

    out = []
    for slide in Presentation(path).slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                out.append(shape.text_frame.text)
            if getattr(shape, "has_table", False) and shape.has_table:
                out += [c.text for r in shape.table.rows for c in r.cells]
        out.append(slide.notes_slide.notes_text_frame.text)
    return " ".join(out)


def read(path: Path) -> str | None:
    if not path.exists():
        return None
    if path.suffix == ".pdf":
        return pdf_text(path)
    if path.suffix == ".pptx":
        return pptx_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def main() -> int:
    pytest_json = DOCS / "testing" / "results" / "deck_pytest.json"
    if not pytest_json.exists():
        print("run `python docs/generate_final_ppt.py` first: it records the fresh pytest result")
        return 2
    n_tests = json.loads(pytest_json.read_text(encoding="utf-8"))["passed"]
    met, total, _ = kpis.summary()
    git = json.loads((DOCS / "report" / "evidence" / "results" / "git.json").read_text(encoding="utf-8"))
    students = (DOCS / "report" / "latex" / "students.tex").read_text(encoding="utf-8")
    names = [m for m in re.findall(r"newcommand\{\\Student[ABC]\}\{([^}]+)\}", students)]

    docs = {
        "README": ROOT / "README.md",
        "contribution log": DOCS / "contribution-log.md",
        "report tables": DOCS / "report" / "latex" / "generated" / "tests_numbers.tex",
        "report PDF": DOCS / "report" / "EcoMesh_Mini_Project_Report.pdf",
        "final deck": DOCS / "Phase_III_IV_EcoMesh_Final.pptx",
        "poster": DOCS / "poster" / "EcoMesh_Poster.pdf",
        "testing document": DOCS / "testing" / "EcoMesh_Phase4_P2_Functional_and_NonFunctional_Testing.pdf",
    }
    texts = {k: read(v) for k, v in docs.items()}

    # ---- test count
    for name, t in texts.items():
        if t is None:
            record("MISSING", name, "file not found")
            continue
        counts = set(re.findall(r"(\d{3})\s+(?:automated\s+)?tests", t)) | set(re.findall(r"providecommand\{\\NTests\}\{(\d+)\}", t))
        if not counts:
            continue
        wrong = sorted(c for c in counts if c != str(n_tests))
        if not wrong:
            record("OK", name, f"test count {n_tests}")
        else:
            kind = "STALE" if str(docs[name]).endswith(".pdf") else "MISMATCH"
            record(kind, name, f"says {', '.join(wrong)} tests; the fresh run has {n_tests}")

    # ---- targets met
    for name in ("final deck", "poster", "testing document"):
        t = texts[name]
        if t is None:
            continue
        found = set(re.findall(r"(\d+)\s+of\s+(?:the\s+)?10\s+(?:target|targets)", t)) | set(re.findall(r"(\d+)\s+of\s+10\s+targets", t))
        if found and found != {str(met)}:
            record("MISMATCH", name, f"says {sorted(found)} of 10 targets met; kpis.py says {met}")
        elif found:
            record("OK", name, f"{met} of 10 targets fully met")

    # ---- names
    for name in ("README", "final deck", "poster", "testing document"):
        t = texts[name]
        if t is None:
            continue
        missing = [n for n in names if n not in t and n.split()[0] not in t]
        record("OK" if not missing else "MISMATCH", name, "all three team names present" if not missing else f"missing {missing}")

    # ---- commit count quoted next to 'commits'
    for name in ("README", "final deck", "poster", "contribution log"):
        t = texts[name]
        if t is None:
            continue
        counts = set(re.findall(r"(\d{2,3}) commits", t))
        if counts and counts - {str(git["commits"])}:
            record("WARN", name, f"quotes {sorted(counts)} commits; git.json (last run) has {git['commits']}")

    width = max(len(w) for _s, w, _x in results) if results else 10
    for status, where, what in results:
        print(f"{status:9} {where:<{width}}  {what}")
    bad = sum(1 for s, *_ in results if s == "MISMATCH")
    print(f"\n{len(results)} checks, {bad} mismatches, {sum(1 for s, *_ in results if s in ('STALE', 'MISSING'))} stale or missing")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
