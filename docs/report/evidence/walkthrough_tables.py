"""Browser-walkthrough evidence for Chapter 9 (and the abstract): the two scripted browser
tests, as LaTeX macros and a table.

    python docs/report/evidence/walkthrough_tables.py

Reads docs/testing/results/device_walkthrough.json (the device screens, the one app) and
docs/testing/results/ui_walkthrough.json (the simulation-lab website), written by the
scripts in docs/testing/. Writes docs/report/latex/generated/walkthrough_numbers.tex
(macros \\NDevChecks, \\NDevPass, \\NWebChecks, \\NWebPass) and device_walkthrough.tex
(Table "Device-screen browser checks"). Nothing is typed by hand.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GEN = ROOT / "docs" / "report" / "latex" / "generated"
RES = ROOT / "docs" / "testing" / "results"
BS = chr(92)


def esc(s: str) -> str:
    out = []
    for ch in s:
        if ch == BS:
            out.append(BS + "textbackslash{}")
        elif ch in "&%$#_{}":
            out.append(BS + ch)
        elif ch == "~":
            out.append(BS + "textasciitilde{}")
        elif ch == "^":
            out.append(BS + "textasciicircum{}")
        elif ch == "−":
            out.append("-")
        elif ord(ch) > 127:
            out.append(" ")  # the check names are plain ASCII; anything else is a typographic extra
        else:
            out.append(ch)
    return "".join(out)


def main() -> None:
    dev = json.loads((RES / "device_walkthrough.json").read_text(encoding="utf-8"))["checks"]
    web = json.loads((RES / "ui_walkthrough.json").read_text(encoding="utf-8"))["checks"]
    dev_pass = sum(1 for c in dev if c["passed"])
    web_pass = sum(1 for c in web if c["passed"])
    macros = "".join(BS + f"providecommand{{{BS}{n}}}{{{v}}}" for n, v in
                     (("NDevChecks", len(dev)), ("NDevPass", dev_pass), ("NWebChecks", len(web)), ("NWebPass", web_pass)))
    (GEN / "walkthrough_numbers.tex").write_text(macros + "\n", encoding="utf-8")

    rows = [BS + "begin{table}[!htbp]",
            BS + "caption{Browser checks of the device screens (the one app), run against five live device processes}",
            BS + "label{tab:devwalk}", BS + "scriptsize",
            BS + "begin{tabularx}{" + BS + "textwidth}{@{}p{1.0cm}X p{1.3cm}@{}}", BS + "toprule",
            BS + "textbf{ID} & " + BS + "textbf{Check} & " + BS + "textbf{Result}" + BS + BS + " " + BS + "midrule"]
    for c in dev:
        rows.append(f"{esc(c['id'])} & {esc(c['name'])} & {'Pass' if c['passed'] else 'FAIL'} " + BS + BS)
    rows += [BS + "bottomrule", BS + "end{tabularx}", BS + "end{table}"]
    (GEN / "device_walkthrough.tex").write_text("\n".join(rows) + "\n", encoding="utf-8")
    print(f"device screens: {dev_pass}/{len(dev)} checks pass; simulation-lab website: {web_pass}/{len(web)}")


if __name__ == "__main__":
    main()
