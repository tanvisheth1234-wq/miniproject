# EcoMesh mini-project report

Report for the T.E. Computer Engineering mini project (SPIT, AY 2026-27), written to the
*Mini Project Report Preparation Guidelines* (11 chapters) with the cover, certificates and
declaration taken from the department's Overleaf template.

## Where things are

| Path | What it is |
|---|---|
| `latex/main.tex` | The report. Compile with `pdflatex main.tex` (twice) or upload `latex/` to Overleaf. |
| `latex/students.tex` | **One place** for names, UIDs, guide and HoD. Edit here, not in the chapters. |
| `latex/chapters/` | One file per chapter, plus abstract, acknowledgement, abbreviations and references. |
| `latex/figures/` | UML diagrams (Phase 2), generated diagrams and charts, screenshots. |
| `latex/generated/` | LaTeX tables and number macros **generated from measured data** - do not edit by hand. |
| `evidence/` | Scripts that measure and generate: `collect.py`, `live_test.py`, `make_tables.py`, `traceability.py`, `fr_table.py`, `git_stats.py`, `sample_data.py`. |
| `evidence/results/` | The raw measurements (JSON, pytest XML) every number in Chapters 8-10 comes from. |
| `make_diagrams.py` | Architecture, DFD, ER, UML and flowchart diagrams (Graphviz; set `DOT` to the `dot` executable). |
| `make_figures.py`, `make_charts.py` | Cost-function figure and result charts. |

## Regenerating the numbers

```
python docs/report/evidence/collect.py all
python docs/report/evidence/live_test.py
python docs/report/evidence/git_stats.py
python docs/report/evidence/sample_data.py
python docs/report/evidence/make_tables.py
python docs/report/evidence/traceability.py
python docs/report/evidence/fr_table.py
python docs/report/make_diagrams.py
python docs/report/make_figures.py
python docs/report/make_charts.py
```

## To add outside the report

1. A photo or screen capture of the two-laptop run (Chapter 10).
2. The research paper or poster for the end-semester evaluation, and the plagiarism report.
3. Each member to confirm the contribution log (Section 7.8); date and place on the declaration; guide's review.
4. A usability test with five people, if wanted (the report states that none was performed).

Build: `cd docs/report/latex && tectonic -X compile main.tex --outdir build` (or upload `latex/` to Overleaf).

## Honest limits stated in the report

No radio hardware (LAN emulation); live timings on loopback; no usability study; no automated UI tests;
SNF-3 (immediate flush on new neighbour) and LOG-5 (history filter) not fully implemented; scale tested to
65 simulated nodes; delivery below 90 % above ~43 nodes at 20 % loss; recovery time just over the 10 s
target in 27 of 50 trials (bounded by the heartbeat timeout).
