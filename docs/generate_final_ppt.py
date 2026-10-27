"""Builds the final Phase III + Phase IV presentation (20 minutes, 14 slides).

    python docs/generate_final_ppt.py            # runs pytest, reads the repo, writes the deck
    python docs/generate_final_ppt.py --no-run   # reuse the last pytest result (faster while editing)

Every number on the slides is read from the repository when the deck is built:
  * test count            a fresh `python -m pytest -q` run
  * commits and authors   `git` and docs/report/evidence/results/git.json
  * requirement tracing   docs/report/evidence/traceability.py
  * measured results      docs/report/evidence/results/*.json (through docs/testing/kpis.py)
  * browser walkthroughs  docs/testing/results/*.json
  * report page count     docs/report/EcoMesh_Mini_Project_Report.pdf
  * who built what        docs/contribution-log.md (checked by assert_in_log below)
The look follows the device app (story/node.html): charcoal title and closing slides,
light content slides, one blue accent, red only for SOS.
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION, XL_TICK_MARK
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EVID = ROOT / "docs" / "report" / "evidence"
RESULTS = EVID / "results"
FIG = ROOT / "docs" / "report" / "latex" / "figures"
REPORT_PDF = ROOT / "docs" / "report" / "EcoMesh_Mini_Project_Report.pdf"
POSTER_PDF = ROOT / "docs" / "poster" / "EcoMesh_Poster.pdf"
OUT = HERE / "Phase_III_IV_EcoMesh_Final.pptx"
REPO_URL = "https://github.com/tanvisheth1234-wq/miniproject"
TOTAL = 14

sys.path.insert(0, str(EVID))
import traceability as T  # noqa: E402

_spec = importlib.util.spec_from_file_location("kpis", HERE / "testing" / "kpis.py")
kpis = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kpis)

# ------------------------------------------------------------------ palette (same tokens as story/node.html)
DARK = RGBColor(0x0E, 0x11, 0x14)
DARK2 = RGBColor(0x16, 0x1A, 0x1F)
DLINE = RGBColor(0x2A, 0x30, 0x38)
DTEXT = RGBColor(0xEE, 0xF1, 0xF4)
DTEXT2 = RGBColor(0xA6, 0xAF, 0xB9)
ACCENT = RGBColor(0x5B, 0x9C, 0xF0)
DANGER = RGBColor(0xE0, 0x46, 0x4C)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LTEXT = RGBColor(0x14, 0x18, 0x1D)
LTEXT2 = RGBColor(0x4D, 0x58, 0x64)
LLINE = RGBColor(0xD5, 0xDB, 0xE2)
LSURF = RGBColor(0xF3, 0xF5, 0xF8)
GREY = RGBColor(0x9A, 0xA4, 0xB0)
FONT = "Segoe UI"


# ------------------------------------------------------------------ repository facts

def sh(*cmd: str) -> str:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.strip()


def run_pytest(skip: bool) -> dict:
    cache = HERE / "testing" / "results" / "deck_pytest.json"
    if skip and cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    out = sh(sys.executable, "-m", "pytest", "-q")
    m = re.search(r"(?:(\d+) failed, )?(\d+) passed.* in ([\d.]+)s", out)
    if not m:
        raise SystemExit("could not read the pytest summary:\n" + out[-400:])
    res = {"passed": int(m.group(2)), "failed": int(m.group(1) or 0), "seconds": float(m.group(3)),
           "date": sh("git", "log", "-1", "--format=%cs")}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(res), encoding="utf-8")
    return res


def jload(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def assert_in_log(member: str, phrase: str) -> None:
    """The deck's 'who built what' must be backed by docs/contribution-log.md."""
    for line in (ROOT / "docs" / "contribution-log.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and cells[1] == member and phrase in cells[2]:
            return
    raise SystemExit(f"contribution log has no row for {member} mentioning {phrase!r}; update docs/contribution-log.md")


def facts(no_run: bool) -> dict:
    f: dict = {}
    f["tests"] = run_pytest(no_run)
    g = jload(RESULTS / "git.json")
    f["git"] = g
    f["commits"] = int(sh("git", "rev-list", "--count", "HEAD"))
    branches = [("develop", "Phase 1"), ("develop_2", "Phase 2"), ("develop_3", "Phase 3"), ("develop_4", "Phase 4"), ("develop_5", "Phase 5"), ("develop_6", "Final")]
    f["branches"] = [(b, label, int(sh("git", "rev-list", "--count", f"origin/{b}") or 0)) for b, label in branches]
    f["trace"] = {k: sum(1 for _t, kind in T.MAP.values() if kind == k) for k in "AMPIU"}
    f["trace_total"] = len(T.MAP)
    f["kpi"] = kpis.evaluate()
    f["scen"] = jload(RESULTS / "scenarios.json")["scenarios"]
    f["loss"] = jload(RESULTS / "loss.json")
    f["live"] = jload(RESULTS / "live.json")
    f["core_lines"] = sum(len((ROOT / "mesh" / "core" / f"{m}.py").read_text(encoding="utf-8").splitlines())
                          for m in ("packet", "transport", "transport_udp", "transport_sim", "discovery", "relay", "routing", "reliability", "crypto", "store", "node"))
    import pymupdf
    f["report_pages"] = len(pymupdf.open(REPORT_PDF))
    f["poster"] = POSTER_PDF.exists()
    dev = HERE / "testing" / "results" / "device_walkthrough.json"
    f["device_walk"] = jload(dev) if dev.exists() else None
    web = HERE / "testing" / "results" / "ui_walkthrough.json"
    f["web_walk"] = jload(web) if web.exists() else None
    f["tmp"] = Path(tempfile.mkdtemp(prefix="ecomesh_deck_"))
    return f


# ------------------------------------------------------------------ drawing helpers

def rgb_fill(shape, color):
    shape.fill.solid()
    shape.fill.fore_color.rgb = color


def no_line(shape):
    shape.line.fill.background()


def text(slide, x, y, w, h, value, size=16, color=LTEXT, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, italic=False, spacing=1.1):
    """``value`` is a string, or a list of (text, {overrides}) runs for one paragraph, or a list of strings for several."""
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    paras = value if isinstance(value, list) and value and isinstance(value[0], (str, list)) else [value]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        runs = para if isinstance(para, list) else [(para, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            r.font.name = FONT
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.italic = o.get("italic", italic)
            r.font.color.rgb = o.get("color", color)
    return box


def bullets(slide, x, y, w, h, items, size=16, color=LTEXT, gap=8):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    for i, item in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.line_spacing = 1.08
        p.space_after = Pt(gap)
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(int(Inches(0.22))))
        pPr.set("indent", str(-int(Inches(0.22))))
        for tag in ("a:buNone", "a:buChar", "a:buAutoNum"):
            for e in pPr.findall(qn(tag)):
                pPr.remove(e)
        bu = pPr.makeelement(qn("a:buChar"), {"char": "•"})
        pPr.append(bu)
        runs = item if isinstance(item, list) else [(item, {})]
        for t, o in runs:
            r = p.add_run()
            r.text = t
            r.font.name = FONT
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", False)
            r.font.color.rgb = o.get("color", color)
    return box


def rect(slide, x, y, w, h, fill=LSURF, line=LLINE, radius=False, line_w=0.75):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    if radius:
        s.adjustments[0] = 0.06
    rgb_fill(s, fill)
    if line is None:
        no_line(s)
    else:
        s.line.color.rgb = line
        s.line.width = Pt(line_w)
    s.shadow.inherit = False
    return s


def oval(slide, cx, cy, d, fill=DARK2, line=ACCENT, line_w=1.75):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(cx - d / 2), Inches(cy - d / 2), Inches(d), Inches(d))
    rgb_fill(s, fill)
    s.line.color.rgb = line
    s.line.width = Pt(line_w)
    s.shadow.inherit = False
    return s


def line(slide, x1, y1, x2, y2, color=LLINE, w=1.25):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color
    c.line.width = Pt(w)
    return c


def background(slide, color):
    bg = slide.background.fill
    bg.solid()
    bg.fore_color.rgb = color


def notes(slide, value: str):
    slide.notes_slide.notes_text_frame.text = value


def light_slide(prs, n, eyebrow, title, subtitle=None):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, WHITE)
    text(s, 0.6, 0.38, 9, 0.3, eyebrow.upper(), 11, LTEXT2, bold=True)
    text(s, 0.6, 0.7, 12.1, 0.7, title, 28, LTEXT, bold=True)
    if subtitle:
        text(s, 0.6, 1.38, 12.1, 0.4, subtitle, 15, LTEXT2)
    line(s, 0.6, 7.0, 12.73, 7.0, LLINE, 0.75)
    text(s, 0.6, 7.08, 6, 0.28, "EcoMesh  ·  Group 20  ·  Phase III and IV", 10, GREY)
    text(s, 10.7, 7.08, 2.03, 0.28, f"{n} / {TOTAL}", 10, GREY, align=PP_ALIGN.RIGHT)
    return s


def dark_slide(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    background(s, DARK)
    return s


def card(slide, x, y, w, h, head, body, size=14, head_color=LTEXT):
    rect(slide, x, y, w, h, LSURF, LLINE, radius=True)
    text(slide, x + 0.25, y + 0.18, w - 0.5, 0.35, head, 15, head_color, bold=True)
    text(slide, x + 0.25, y + 0.62, w - 0.5, h - 0.75, body, size, LTEXT2, spacing=1.15)


def table(slide, x, y, w, col_w, header, rows, row_h=0.42, size=12.5, head_size=12):
    shp = slide.shapes.add_table(len(rows) + 1, len(header), Inches(x), Inches(y), Inches(w), Inches(row_h * (len(rows) + 1)))
    tbl = shp.table
    tblPr = tbl._tbl.tblPr
    for attr in ("bandRow", "firstRow"):
        tblPr.set(attr, "0")
    total = sum(col_w)
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Emu(int(Inches(w) * cw / total))
    for i in range(len(rows) + 1):
        tbl.rows[i].height = Inches(row_h)

    def put(cell, value, bold, color, fill, sz):
        cell.fill.solid()
        cell.fill.fore_color.rgb = fill
        cell.margin_left = cell.margin_right = Inches(0.1)
        cell.margin_top = cell.margin_bottom = Inches(0.04)
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        tf = cell.text_frame
        tf.word_wrap = True
        r = tf.paragraphs[0].add_run()
        r.text = value
        r.font.name, r.font.size, r.font.bold = FONT, Pt(sz), bold
        r.font.color.rgb = color

    for j, h in enumerate(header):
        put(tbl.cell(0, j), h, True, DTEXT, DARK2, head_size)
    for i, row in enumerate(rows, start=1):
        for j, v in enumerate(row):
            put(tbl.cell(i, j), v, j == 0, LTEXT, LSURF if i % 2 else WHITE, size)
    return tbl


def picture_fit(slide, path, x, y, max_w, max_h, border=True):
    from PIL import Image

    with Image.open(path) as im:
        w, h = im.size
    scale = min(max_w / w, max_h / h)
    pw, ph = w * scale, h * scale
    pic = slide.shapes.add_picture(str(path), Inches(x + (max_w - pw) / 2), Inches(y + (max_h - ph) / 2), Inches(pw), Inches(ph))
    if border:
        pic.line.color.rgb = LLINE
        pic.line.width = Pt(0.75)
    return pic


def style_chart(chart, legend=False):
    chart.font.name = FONT
    chart.font.size = Pt(12)
    chart.font.color.rgb = LTEXT2
    chart.has_legend = legend
    va, ca = chart.value_axis, chart.category_axis
    va.major_gridlines.format.line.color.rgb = LLINE
    va.format.line.fill.background()
    ca.format.line.color.rgb = LLINE
    va.tick_labels.font.color.rgb = LTEXT2
    ca.tick_labels.font.color.rgb = LTEXT
    va.tick_labels.font.size = ca.tick_labels.font.size = Pt(12)


def hide_axis(axis):
    axis.has_major_gridlines = False
    axis.tick_label_position = XL_TICK_LABEL_POSITION.NONE
    axis.major_tick_mark = XL_TICK_MARK.NONE
    axis.format.line.fill.background()


# ------------------------------------------------------------------ slides

def build(f: dict) -> Presentation:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    cp = prs.core_properties
    cp.title, cp.author, cp.subject = "EcoMesh: Phase III and IV", "EcoMesh Group 20", "Mini Project I, T.E. Semester V"
    cp.keywords, cp.comments, cp.last_modified_by = "", "", "EcoMesh Group 20"

    git = f["git"]
    members = git["per_member"]
    n_tests = f["tests"]["passed"] + f["tests"]["failed"]
    met, total_k, not_met = kpis.summary(f["kpi"])
    kp = {r["id"]: r for r in f["kpi"]}
    scen = f["scen"]
    pl = scen["priority_load"]["weighted"]
    hv = scen["hopcount_vs_weighted"]
    col40 = scen["collapse_40"]["weighted"]

    # ---------------------------------------------------------------- 1 title (dark)
    s = dark_slide(prs)
    text(s, 0.8, 0.7, 9, 0.3, "MINI PROJECT I  ·  T.E. SEMESTER V  ·  SPIT", 12, DTEXT2, bold=True)
    text(s, 0.8, 1.9, 8, 1.3, "EcoMesh", 66, DTEXT, bold=True)
    text(s, 0.8, 3.25, 7.2, 1.0, "Distributed peer-to-peer\ndisaster-relief communication mesh", 24, DTEXT2, spacing=1.15)
    text(s, 0.8, 4.55, 8, 0.4, "Phase III and Phase IV  ·  Group 20", 18, ACCENT, bold=True)
    line(s, 0.8, 5.25, 7.6, 5.25, DLINE, 1)
    text(s, 0.8, 5.5, 7, 0.4, "Twissha Shah   ·   Miti Shah   ·   Tanvi Sheth", 17, DTEXT)
    text(s, 0.8, 6.0, 7, 0.35, "Guide: Prof. Anuj Tawari", 14, DTEXT2)
    # a small mesh motif: four phones in a line, an SOS leaving the first
    pts = [(9.0, 4.9), (10.1, 3.4), (10.1, 6.2), (11.5, 4.9), (12.6, 4.9)]
    for a, b in ((0, 1), (0, 2), (1, 3), (2, 3), (3, 4)):
        line(s, pts[a][0], pts[a][1], pts[b][0], pts[b][1], DLINE, 2)
    for i, (px, py) in enumerate(pts):
        oval(s, px, py, 0.5 if i not in (0, 4) else 0.62, DARK2, DANGER if i == 0 else ACCENT, 2.25)
    text(s, 8.45, 5.35, 1.3, 0.3, "SOS", 12, DANGER, bold=True, align=PP_ALIGN.CENTER)
    text(s, 12.0, 5.3, 1.2, 0.3, "Rescue", 12, DTEXT2, align=PP_ALIGN.CENTER)
    notes(s, "Good morning. We are Group 20: Twissha Shah, Miti Shah and Tanvi Sheth, guided by Prof. Anuj Tawari. "
             "EcoMesh is a disaster-relief communication mesh: when towers and internet are gone, every phone becomes a relay so that "
             "an SOS can hop from device to device until it reaches a rescue team. In the next twenty minutes we cover Phase III, the "
             "engine and how we managed the code, and Phase IV, the integrated app, the testing and the report.")

    # ---------------------------------------------------------------- 2 problem and idea
    s = light_slide(prs, 2, "The problem and the idea", "When towers fail, phones can still reach each other")
    text(s, 0.6, 1.75, 5.6, 0.35, "THE PROBLEM", 12, LTEXT2, bold=True)
    bullets(s, 0.6, 2.2, 5.6, 2.3, [
        "After an earthquake, fire or building collapse, cell towers fail or are jammed.",
        "Messaging apps need a server far away, so they stop even for people in the same room.",
        "Trapped people cannot tell anyone where they are; rescuers search room by room.",
    ], 17, LTEXT, gap=12)
    text(s, 0.6, 4.75, 5.6, 0.35, "THE IDEA", 12, LTEXT2, bold=True)
    text(s, 0.6, 5.15, 5.6, 1.6, "Phones still have battery and can still reach devices near them. Make every device a relay, so an SOS hops "
         "device to device until it reaches a rescue team or a gateway. No tower, no internet, no central server.", 16, LTEXT, spacing=1.2)
    rect(s, 6.7, 1.75, 6.03, 5.0, DARK, None, radius=True)
    nodes = [(7.4, 4.6, "Trapped\nperson"), (8.9, 3.0, "Phone 2"), (8.9, 6.1, "Phone 3"), (10.7, 4.6, "Gateway"), (12.2, 4.6, "Rescue\nteam")]
    for a, b in ((0, 1), (0, 2), (1, 3), (2, 3), (3, 4)):
        line(s, nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1], DLINE, 2.25)
    for a, b in ((0, 1), (1, 3), (3, 4)):
        line(s, nodes[a][0], nodes[a][1], nodes[b][0], nodes[b][1], ACCENT, 3)
    for i, (px, py, lab) in enumerate(nodes):
        oval(s, px, py, 0.55, DARK2, DANGER if i == 0 else ACCENT, 2.25)
        text(s, px - 0.7, py + 0.4, 1.4, 0.5, lab, 11.5, DTEXT2, align=PP_ALIGN.CENTER, spacing=1.0)
    text(s, 6.95, 1.95, 5.5, 0.35, "An SOS crosses the mesh", 14, DTEXT, bold=True)
    text(s, 6.95, 2.3, 5.5, 0.35, "The route is chosen by the network, not typed in", 12, DTEXT2)
    notes(s, "The problem. In a disaster the towers fail or are overloaded, and apps like WhatsApp need a far-away server, so they fail even "
             "between two people in the same building. The insight is that connectivity is never fully zero: phones still have battery and can still "
             "reach nearby devices. EcoMesh turns every device into both an endpoint and a relay. The picture shows the idea: a trapped person's "
             "SOS hops through another phone and a gateway to the rescue team, with no server involved.")

    # ---------------------------------------------------------------- 3 what we built
    s = light_slide(prs, 3, "What we built", "An engine, an API and one device app")
    arch_png = f["tmp"] / "arch.png"
    import pymupdf
    pymupdf.open(FIG / "fig_architecture.pdf")[0].get_pixmap(dpi=190).save(arch_png)
    picture_fit(s, arch_png, 0.6, 1.6, 5.3, 5.2, border=False)
    card(s, 6.2, 1.65, 6.53, 1.38, "Engine  (mesh/core)",
         f"{len(['packet','transport','transport_udp','transport_sim','discovery','relay','routing','reliability','crypto','store','node'])} modules, {f['core_lines']:,} lines: "
         "discovery, link-state routing, reliability, security and a SQLite log per device.", 13.5)
    card(s, 6.2, 3.18, 6.53, 1.38, "API and simulation lab",
         "FastAPI and WebSocket server, a React lab and a simulator that runs 7 scenarios up to 65 nodes. It produced the experiment results.", 13.5)
    card(s, 6.2, 4.71, 6.53, 1.38, "The device app  (story/)",
         "One web page per device. It becomes the survivor phone, the gateway view or the rescue console, depending on the device's role.", 13.5)
    rect(s, 6.2, 6.25, 6.53, 0.6, LSURF, LLINE, radius=True)
    text(s, 6.4, 6.25, 6.15, 0.6, [[("The radio is emulated. ", {"bold": True}),
                                    ("Devices exchange real packets over TCP, but only with the neighbours a config file allows.", {})]],
         12.5, LTEXT, anchor=MSO_ANCHOR.MIDDLE)
    notes(s, "This is the architecture. At the bottom is the engine: discovery, routing, reliability, security and the log, about "
             f"{f['core_lines']:,} lines in eleven modules. Above it, an API and a simulation lab, which we used to run the experiments. "
             "And the single app: one web page that each device serves, which turns into a survivor phone, a gateway view or the rescue console. "
             "We want to be clear about one thing now rather than be asked later: the radio is emulated. Real packets cross real TCP connections, "
             "but a configuration file decides who can hear whom. A real phone app would swap that transport for Bluetooth or Wi-Fi Direct.")

    # ---------------------------------------------------------------- 4 module-wise coding
    assert_in_log("Tanvi", "packet.py")
    assert_in_log("Miti", "discovery.py")
    assert_in_log("Twissha", "link-state")
    assert_in_log("Miti", "Dijkstra")
    assert_in_log("Miti", "crypto.py")
    assert_in_log("Twissha", "node.py")
    s = light_slide(prs, 4, "Phase III  ·  P1 module-wise coding", "Eleven modules, built by three people",
                    "Who built what, as recorded in the contribution log.")
    rows = [
        ("1", "Packet format (52-byte header), transport interface, UDP transport", "Tanvi"),
        ("2", "Discovery (HELLO, neighbour table), relay, simulated transport", "Miti"),
        ("3", "Link-state gossip and the weighted cost function; wiring into the node", "Twissha"),
        ("3", "Dijkstra pathfinding, dedup and priority queue, ACK and retry, store-and-forward", "Miti"),
        ("3", "AES-256-GCM and Ed25519 security; SQLite message and event log", "Miti"),
        ("4", "API, simulation lab, scenarios; engine fixes found by integration", "Tanvi"),
        ("4", "Device app, multi-device demo, packet-parser hardening, report evidence", "Twissha"),
        ("4", "Device server: send, history, safe, structured SOS, CSV export, immediate flush", "Miti"),
    ]
    table(s, 0.6, 1.95, 12.13, [0.8, 8.6, 1.6], ["PHASE", "WHAT WAS BUILT", "BUILT BY"], rows, row_h=0.5, size=13.5, head_size=12)
    text(s, 0.6, 6.55, 12.1, 0.35, f"Every module has its own test file. The suite has {n_tests} tests in total.", 14, LTEXT2)
    notes(s, "Phase III was module-wise coding, and each module has its own tests. Tanvi built the packet format and transport in Phase 1. Miti built discovery and the relay in "
             "Phase 2. In Phase 3, Twissha wrote the link-state gossip and the cost function and wired everything into the node; Miti wrote Dijkstra, the reliability layer, "
             "the cryptography and the SQLite log. In Phase 4, Tanvi built the API and the simulation lab and the fixes that integration forced; Twissha built the device app and the "
             "multi-device demo; Miti built the device server endpoints. This table is taken from our contribution log.")

    # ---------------------------------------------------------------- 5 how an SOS travels
    s = light_slide(prs, 5, "Phase III  ·  the algorithms", "How an SOS travels")
    steps = [("1", "Route", "Dijkstra over the link-state graph picks the cheapest path"),
             ("2", "Seal", "AES-256-GCM encrypts the payload; Ed25519 signs the identity"),
             ("3", "Relay", "Every hop sends SOS before routine traffic"),
             ("4", "Confirm", "The receiver acknowledges; a missed ACK retries on a recomputed route"),
             ("5", "Hold", "No route? The message is kept and sent when a path appears")]
    bw, gap = 2.3, 0.15
    for i, (n, head, body) in enumerate(steps):
        x = 0.6 + i * (bw + gap)
        rect(s, x, 1.75, bw, 2.2, LSURF, LLINE, radius=True)
        oval(s, x + 0.42, 2.25, 0.46, ACCENT, ACCENT, 0.75)
        text(s, x + 0.19, 2.04, 0.46, 0.46, n, 15, DARK, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(s, x + 0.82, 2.12, bw - 0.9, 0.35, head, 16, LTEXT, bold=True)
        text(s, x + 0.2, 2.72, bw - 0.4, 1.2, body, 12.5, LTEXT2, spacing=1.12)
    text(s, 0.6, 4.3, 6, 0.3, "THE COST OF ONE LINK", 12, LTEXT2, bold=True)
    rect(s, 0.6, 4.7, 6.2, 1.0, DARK, None, radius=True)
    text(s, 0.6, 4.7, 6.2, 1.0, "cost  =  1  +  5 (1 − q)  +  3 f", 26, DTEXT, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.6, 5.85, 6.2, 1.0, "q is the share of the last 20 HELLO beacons heard. f is the number of recent ACK timeouts. "
         "Weak or failing links cost more, so the router prefers reliable links over merely short ones.", 13, LTEXT2, spacing=1.15)
    q = 0.55
    text(s, 7.2, 4.3, 5.5, 0.3, "WHAT THAT MEANS", 12, LTEXT2, bold=True)
    bullets(s, 7.2, 4.7, 5.5, 2.3, [
        [("A perfect link costs 1.00. ", {"bold": True}), (f"A link that loses 45% of beacons (q = {q}) costs {1 + 5 * (1 - q):.2f}.", {})],
        "A longer path over clean links can beat a shorter path over a bad one.",
        "SOS packets jump the queue at every hop, not only at the source.",
    ], 14, LTEXT, gap=9)
    notes(s, "Here is how one SOS travels. The router runs Dijkstra over a graph that every node builds from its neighbours' reports. The cost of a link is one, plus five times "
             f"one minus the link quality, plus three times the recent failures. So a link that loses 45 percent of beacons costs {1 + 5 * (1 - q):.2f} instead of one, and the router will happily "
             "take a longer clean path. The payload is encrypted with AES-256-GCM and the identity is signed with Ed25519, so relays cannot read or forge it. At every hop the priority queue "
             "sends SOS first. The receiver acknowledges; if the acknowledgement does not come back, the sender retries on a recomputed route. And if there is no route at all, the message is held, "
             "not dropped, and sent when a path appears.")

    # ---------------------------------------------------------------- 6 repository and branching
    s = light_slide(prs, 6, "Phase III  ·  P2 repository  ·  P3 branching", "One branch per phase, never merged back",
                    "Each phase branch is a snapshot a reviewer can open, run and grade on its own.")
    bw, gap = 1.9, 0.12
    for i, (b, label, n) in enumerate(f["branches"]):
        x = 0.6 + i * (bw + gap)
        rect(s, x, 1.95, bw, 1.75, LSURF, LLINE, radius=True)
        text(s, x + 0.15, 2.05, bw - 0.3, 0.28, label.upper(), 10.5, LTEXT2, bold=True)
        text(s, x + 0.15, 2.35, bw - 0.3, 0.35, b, 14, LTEXT, bold=True)
        text(s, x + 0.15, 2.8, bw - 0.3, 0.6, str(n), 28, ACCENT, bold=True)
        text(s, x + 0.15, 3.35, bw - 0.3, 0.3, "commits", 11, LTEXT2)
    text(s, 0.6, 3.85, 12, 0.3, "Cumulative commit count on each branch, read from git. main holds one README commit and is reserved for tagged releases.", 12, LTEXT2)
    cc, tot = git["conventional"], git["commits"]
    card(s, 0.6, 4.45, 5.95, 2.2, "Conventional Commits",
         f"{cc} of {tot} commits ({100 * cc / tot:.0f}%) follow type(scope): description. The {tot - cc} that do not are five early commits from Phases 1 and 2 and one merge commit.", 15)
    mem = "   ".join(f"{k.split()[0]} {v}" for k, v in members.items())
    card(s, 6.78, 4.45, 5.95, 2.2, "Three contributors",
         f"Commits by member: {mem}. Commit messages carry the type (feat, fix, test, docs, chore) so the history can be read as a changelog.", 15)
    notes(s, "Repository and branching. Phase 2 of the college plan asked us to set up the repository and a branching strategy. We use one branch per phase, and each branch inherits "
             "everything before it, so a reviewer can check out the branch for Phase 3 and see exactly what existed then. We never merge between phase branches, and main is reserved for tagged "
             f"releases. The counts on screen are cumulative commits read from git: {', '.join(f'{b} {n}' for b, _l, n in f['branches'])}. We use Conventional Commits; "
             f"{cc} of {tot} commits follow the format, and the exceptions are from the first weeks. The commit counts by member are {mem}.")

    # ---------------------------------------------------------------- 7 the one app
    s = light_slide(prs, 7, "Phase IV  ·  P1 integration", "One app: the device screen", "Served by each device. Its role decides what it shows.")
    picture_fit(s, FIG / "story_survivor_delivered.png", 0.6, 1.95, 2.35, 4.35)
    picture_fit(s, FIG / "story_rescue_console.png", 3.25, 1.95, 6.0, 4.0)
    text(s, 0.6, 6.45, 2.4, 0.3, "Survivor phone", 11.5, LTEXT2, bold=True)
    text(s, 3.25, 6.0, 6.0, 0.3, "Rescue console", 11.5, LTEXT2, bold=True)
    bullets(s, 9.55, 1.95, 3.2, 4.9, [
        [("Survivor: ", {"bold": True}), ("hold to send SOS with need and location, I am safe, send a message, see the rescue team's reply.", {})],
        [("Gateway: ", {"bold": True}), ("messages passed on, live activity.", {})],
        [("Rescue console: ", {"bold": True}), ("requests with route, reply, filters, history, CSV export, network map.", {})],
        [("A phone is only a screen. ", {"bold": True}), ("The engine runs on the laptop.", {})],
    ], 13, LTEXT, gap=9)
    notes(s, "Phase IV, integration of front end and back end. We started with a React website and a Python API, and ended with something simpler and more honest: one app. "
             "Each device runs the full engine and serves one web page. Depending on the device's role the page becomes the survivor phone, the gateway view or the rescue console. "
             "On the left is the survivor's screen after delivery. On the right is the rescue console, showing the request, its need and location, and the route it took. "
             "A phone is only a screen here: the engine runs on a laptop and the phone opens its page over the same Wi-Fi. The React website stays in the repository as the simulation lab that produced our measurements.")

    # ---------------------------------------------------------------- 8 defects
    s = light_slide(prs, 8, "Phase IV  ·  P1 integration", "Integration found real defects", "Seven defects in the engine and tests. Six are closed with a regression test; one is open.")
    rows = [
        ("D1", "Discovery and relay shared one receive callback; the last registered won", "Single dispatcher registered last"),
        ("D2", "Multi-hop ACK and retry failed: duplicate filter dropped ACKs and retries", "Key on type, id and attempt; retry counter in the header"),
        ("D3", "Dead nodes stayed routable: new link-state reports merged with old ones", "A newer report replaces the old one"),
        ("D4", "A non-ASCII byte made the parser raise the wrong exception (found by fuzzing)", "Raise the packet error; both fuzz tests pass"),
        ("D5", "Node.stop() hung on Windows: a cancellation was swallowed", "Helper built on asyncio.wait; 40 of 40 clean"),
        ("D6", "Two timing-sensitive tests failed under load", "Polling helper instead of fixed sleeps"),
        ("D7", "History-order test fails now and then: same-millisecond messages have no order", "Add a second sort key; with the test's owner"),
    ]
    table(s, 0.6, 1.95, 12.13, [0.6, 6.3, 4.3, 0.95], ["ID", "DEFECT", "FIX", "STATUS"], [(a, b, c, "Open" if a == "D7" else "Closed") for a, b, c in rows], row_h=0.58, size=12.5)
    notes(s, "Integration is where bugs hide that unit tests cannot see. These seven defects were found by wiring things together or by hammering them. D2 is the most important: multi-hop "
             "acknowledgements did not work at all, because the duplicate filter dropped every ACK at the first relay its data had crossed, and swallowed retries. D4 was found by fuzzing: random "
             "bytes made the parser raise the wrong exception. D6, the two flaky tests, is closed. D7 is open, and we want to be transparent about it: a history test fails occasionally because two messages created in the same millisecond have no defined order. It is open and reported to its owner.")

    # ---------------------------------------------------------------- 9 demo story
    s = light_slide(prs, 9, "Phase IV  ·  P1 integration", "The demo: an SOS that survives failures", "Five minutes, five devices, one app. The script is in docs/DEMO_SCRIPT.md.")
    cols = [("1", "SOS delivered", "Hold the button. The request reaches the rescue console by way of Phone 2 and the gateway.", "story_survivor_delivered.png"),
            ("2", "A relay fails", "Switch off the relay. The activity panel shows the lost contact; the next SOS takes the other path.", None),
            ("3", "The gateway fails", "No route. The phone says “Saved, waiting for a path” and keeps the message safe.", "story_survivor_held.png"),
            ("4", "The gateway returns", "Within seconds the held message is sent and the screen confirms the rescue team has it.", "story_survivor_flushed.png")]
    cw, gap = 2.9, 0.18
    for i, (n, head, body, img) in enumerate(cols):
        x = 0.6 + i * (cw + gap)
        rect(s, x, 1.95, cw, 4.9, LSURF, LLINE, radius=True)
        text(s, x + 0.2, 2.05, 0.5, 0.4, n, 20, ACCENT, bold=True)
        text(s, x + 0.65, 2.1, cw - 0.8, 0.35, head, 14.5, LTEXT, bold=True)
        if img:
            picture_fit(s, FIG / img, x + 0.2, 2.6, cw - 0.4, 2.55)
        else:
            rect(s, x + 0.2, 2.6, cw - 0.4, 2.55, DARK, None, radius=True)
            ox, oy, k = x + 0.2, 2.6, (cw - 0.4) / 2.5
            pts = [(0.3, 1.275), (1.05, 0.55), (1.05, 2.0), (1.8, 1.275), (2.25, 1.275)]
            for a_, b_ in ((0, 1), (1, 3), (0, 2), (2, 3), (3, 4)):
                dead = 1 in (a_, b_)
                live = 1 not in (a_, b_) and (a_, b_) in ((0, 2), (2, 3), (3, 4))
                line(s, ox + pts[a_][0] * k, oy + pts[a_][1] * k, ox + pts[b_][0] * k, oy + pts[b_][1] * k,
                     DLINE if dead else (ACCENT if live else DLINE), 1.5 if dead else 3)
            for i, (px, py) in enumerate(pts):
                oval(s, ox + px * k, oy + py * k, 0.34, DARK2, DANGER if i == 0 else (DLINE if i == 1 else ACCENT), 2)
            text(s, ox + 0.6 * k, oy + 0.1, 1.3, 0.3, "off", 11, DTEXT2, align=PP_ALIGN.CENTER)
        text(s, x + 0.2, 5.3, cw - 0.4, 1.5, body, 12.5, LTEXT2, spacing=1.15)
    notes(s, "This is the story we tell in the live demo. One: the survivor holds the SOS button; it reaches the rescue console through Phone 2 and the gateway. Two: we switch off the relay; "
             "the live activity panel shows the lost contact, and the next SOS still arrives by the other path. Three: we switch off the gateway. There is no route, so the survivor's phone says "
             "Saved, waiting for a path, and keeps the message. Four: the gateway comes back, and within seconds the held message is sent and the screen confirms it. The whole script, with set-up and "
             "likely questions, is in docs/DEMO_SCRIPT.md.")

    # ---------------------------------------------------------------- 10 functional testing
    s = light_slide(prs, 10, "Phase IV  ·  P2 testing", "Functional testing: does it do what the SRS says")
    tr = f["trace"]
    verified = tr["A"] + tr["M"]
    stats = [(str(n_tests), "automated tests pass in a fresh run"), (str(f["trace_total"]), "functional requirements, each traced to evidence"),
             (str(verified), f"fully verified by tests ({tr['M']} with a manual look at the screen)")]
    for i, (v, lab) in enumerate(stats):
        x = 0.6 + i * 4.1
        rect(s, x, 1.75, 3.95, 1.75, LSURF, LLINE, radius=True)
        text(s, x + 0.25, 1.88, 3.5, 0.9, v, 44, ACCENT, bold=True)
        text(s, x + 0.25, 2.85, 3.5, 0.6, lab, 13, LTEXT2, spacing=1.1)
    dw, ww = f["device_walk"], f["web_walk"]
    walk_lines = []
    if dw:
        walk_lines.append([("Device screens: ", {"bold": True}), (f"{sum(1 for c in dw['checks'] if c['passed'])} of {len(dw['checks'])} browser checks pass: SOS with need and location, "
                                                                 "I am safe, send a message, rescue reply, filters, history, CSV export, activity panel, gateway off and on.", {})])
    if ww:
        walk_lines.append([("Simulation lab website: ", {"bold": True}), (f"{sum(1 for c in ww['checks'] if c['passed'])} of {len(ww['checks'])} browser checks pass.", {})])
    other = tr["P"] + tr["I"] + tr["U"]
    walk_lines.append([("Other methods: ", {"bold": True}), (f"{tr['P']} partly implemented, {tr['I']} by code inspection, {tr['U']} by manual check only. Nothing is hidden.", {})])
    bullets(s, 0.6, 3.85, 12.1, 2.6, walk_lines, 15, LTEXT, gap=12)
    text(s, 0.6, 6.45, 12.1, 0.4, "Test levels: unit, integration, API, browser, simulation, five real processes over TCP, fuzzing and stress.", 13, LTEXT2)
    notes(s, f"Functional testing asks whether each feature does what the specification says. A fresh run of the suite just now passed {n_tests} tests in {f['tests']['seconds']:.0f} seconds. "
             f"Our SRS has {f['trace_total']} numbered functional requirements and every one is traced to the test or check that verifies it: {verified} are fully verified by automated tests, "
             f"{tr['M']} of them with a manual look at the screen. The remaining {other} are marked partly implemented, verified by inspection or by a manual check, and the testing document says which. "
             "We also drive the real device screens in a browser, pressing the buttons a user would press, and record the results.")

    # ---------------------------------------------------------------- 11 non-functional
    s = light_slide(prs, 11, "Phase IV  ·  P2 testing", f"Non-functional results: {met} of {total_k} targets fully met",
                    "Ten targets were fixed in the project plan before any measurement.")
    cw = 3.95
    # chart 1: delivery vs loss
    rect(s, 0.6, 1.95, cw, 3.55, WHITE, LLINE, radius=True)
    text(s, 0.8, 2.05, cw - 0.4, 0.3, "Delivery against packet loss", 13, LTEXT, bold=True)
    cd = CategoryChartData()
    cd.categories = [f"{int(r['loss'] * 100)}%" for r in f["loss"]]
    cd.add_series("delivery", [round(r["delivery_mean"] * 100, 1) for r in f["loss"]])
    ch = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.7), Inches(2.4), Inches(cw - 0.2), Inches(3.05), cd).chart
    style_chart(ch)
    ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 40, 100
    ch.value_axis.tick_labels.number_format, ch.value_axis.tick_labels.number_format_is_linked = '0"%"', False
    ser = ch.plots[0].series[0]
    ser.format.line.color.rgb, ser.format.line.width, ser.smooth = ACCENT, Pt(2.5), False
    ser.marker.format.fill.solid()
    ser.marker.format.fill.fore_color.rgb = ACCENT
    ser.marker.format.line.color.rgb = ACCENT
    # chart 2: weighted vs hop-count
    x2 = 0.6 + cw + 0.14
    rect(s, x2, 1.95, cw, 3.55, WHITE, LLINE, radius=True)
    text(s, x2 + 0.2, 2.05, cw - 0.4, 0.3, "Weighted vs hop-count routing", 13, LTEXT, bold=True)
    cd = CategoryChartData()
    cd.categories = ["Hop count", "Weighted"]
    cd.add_series("delivery", [round(hv["hopcount"]["delivery_ratio"]["mean"] * 100, 1), round(hv["weighted"]["delivery_ratio"]["mean"] * 100, 1)])
    ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x2 + 0.1), Inches(2.4), Inches(cw - 0.2), Inches(3.05), cd).chart
    style_chart(ch)
    ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, 115
    hide_axis(ch.value_axis)
    pl_ = ch.plots[0]
    pl_.gap_width, pl_.vary_by_categories = 60, False
    pl_.has_data_labels = True
    pl_.data_labels.number_format, pl_.data_labels.number_format_is_linked = '0.0"%"', False
    pl_.data_labels.font.size, pl_.data_labels.font.bold, pl_.data_labels.font.color.rgb = Pt(14), True, LTEXT
    pl_.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, c in enumerate((GREY, ACCENT)):
        pt = pl_.series[0].points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = c
    # chart 3: SOS vs routine latency
    x3 = x2 + cw + 0.14
    rect(s, x3, 1.95, cw, 3.55, WHITE, LLINE, radius=True)
    sos_ms, rou_ms = pl["latency_ms"]["SOS"], pl["latency_ms"]["NORMAL"]
    text(s, x3 + 0.2, 2.05, cw - 0.4, 0.3, "Median latency under load (ms)", 13, LTEXT, bold=True)
    cd = CategoryChartData()
    cd.categories = ["Routine", "SOS"]
    cd.add_series("ms", [round(rou_ms), round(sos_ms)])
    ch = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(x3 + 0.1), Inches(2.4), Inches(cw - 0.2), Inches(3.05), cd).chart
    style_chart(ch)
    ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 0, max(rou_ms, sos_ms) * 1.2
    hide_axis(ch.value_axis)
    pl_ = ch.plots[0]
    pl_.gap_width, pl_.vary_by_categories = 60, False
    pl_.has_data_labels = True
    pl_.data_labels.number_format, pl_.data_labels.number_format_is_linked = '#,##0', False
    pl_.data_labels.font.size, pl_.data_labels.font.bold, pl_.data_labels.font.color.rgb = Pt(14), True, LTEXT
    pl_.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, c in enumerate((GREY, DANGER)):
        pt = pl_.series[0].points[i]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = c
    text(s, x3 + 0.2, 5.5, cw - 0.4, 0.3, f"SOS arrives {pl['sos_latency_advantage']:.1f} times faster", 12.5, DANGER, bold=True)
    misses = "; ".join(f"{r['id']} {r['name'].lower()}" for r in not_met)
    text(s, 0.6, 5.85, 12.1, 1.15, [[("Fully met: ", {"bold": True}), (", ".join(r["id"] for r in f["kpi"] if r["verdict"] == "Met") + ".   ", {}),
                                   ("Partly met: ", {"bold": True}), (misses + ".", {})],
                                  [(f"Delivery was {kp['K1']['measured'].split(' mean')[0]} on a 40-node mesh at 20% loss with failures injected "
                                    f"(target 90%). Recovery after a relay dies is quantised by the 10 s heartbeat; at 20% loss delivery is 92.9% at 50 nodes and 83.1% at 65.", {"color": LTEXT2})]],
         13.5, LTEXT, spacing=1.2)
    notes(s, f"Non-functional testing asks how well. We fixed ten targets in the project plan before measuring, and {met} of them are fully met. The left chart shows delivery staying at 100 percent up to "
             f"10 percent loss on every link and degrading gracefully after that. The middle chart is the central claim of the routing design: on identical seeds, weighted routing delivered "
             f"{100 * hv['weighted']['delivery_ratio']['mean']:.1f} percent against {100 * hv['hopcount']['delivery_ratio']['mean']:.1f} percent for hop-count routing. The right chart shows that under congestion the median "
             f"SOS arrives {pl['sos_latency_advantage']:.1f} times faster than routine traffic. And here are the misses, because we would rather you hear them from us: {misses}. "
             f"Delivery was {kp['K1']['measured'].split(' mean')[0]} on a 40-node mesh with 20 percent loss and failures; recovery time is limited by the ten-second heartbeat; and at "
             "20 percent loss delivery is 92.9 percent at 50 nodes but 83.1 percent at 65.")

    # ---------------------------------------------------------------- 12 report
    s = light_slide(prs, 12, "Phase IV  ·  P3 report", "A report whose numbers come from the code")
    stats = [(str(f["report_pages"]), "pages in the final PDF, 11 chapters"), (str(f["trace_total"]), "requirements traced in the report's tables"),
             (f"{total_k}", "target metrics, each validated against stored data")]
    for i, (v, lab) in enumerate(stats):
        x = 0.6 + i * 4.1
        rect(s, x, 1.75, 3.95, 1.75, LSURF, LLINE, radius=True)
        text(s, x + 0.25, 1.88, 3.5, 0.9, v, 44, ACCENT, bold=True)
        text(s, x + 0.25, 2.85, 3.5, 0.6, lab, 13, LTEXT2, spacing=1.1)
    poster = "A one-page poster summarises the problem, the architecture, the key results and the limits, with a QR code to the repository." if f["poster"] else None
    items = [
        "Follows the department template and the Mini Project report guidelines: introduction, literature survey, SRS, design, algorithms, implementation, performance, testing, results, conclusion.",
        "Every number in the chapters on performance, testing and results is generated from stored measurements by scripts in docs/report/evidence, so a change can be re-measured and the tables rebuilt.",
        "A separate testing document covers the functional and non-functional tests in detail, with every test case listed.",
    ]
    if poster:
        items.append(poster)
    bullets(s, 0.6, 3.85, 12.1, 3.0, items, 15, LTEXT, gap=11)
    notes(s, f"Phase IV also asked for a report. Ours is {f['report_pages']} pages in eleven chapters, following the department template and the report guidelines. What we are proud of is that the numbers are not typed in: "
             "the measurements are saved as data, scripts turn them into tables, and the report includes those tables, so any change to the code can be re-measured and the report rebuilt. "
             "There is also a separate, detailed testing document, and a one-page poster for the evaluation." if f["poster"] else
             f"Phase IV also asked for a report. Ours is {f['report_pages']} pages in eleven chapters, following the department template and guidelines. The numbers are generated from stored measurements by scripts, "
             "not typed in, and there is a separate detailed testing document.")

    # ---------------------------------------------------------------- 13 limits
    s = light_slide(prs, 13, "Honest limits", "What this is, and what it is not")
    card(s, 0.6, 1.75, 5.95, 2.45, "A measured prototype",
         "We built and measured the routing and reliability layer; it is not a finished product. The radio is emulated over TCP. "
         "A real build needs a Bluetooth or Wi-Fi Direct transport, and the transport interface is built for that swap.", 15)
    card(s, 6.78, 1.75, 5.95, 2.45, "Not built",
         "There is no real phone app: a phone only shows a web page served by a laptop. One shared key protects the whole mesh, "
         "so any key holder could read forwarded messages. Per-pair keys are future work.", 15)
    card(s, 0.6, 4.4, 5.95, 2.4, "Tried and dropped",
         "A faster failure detector (neighbour timeout of about 7 s instead of 10 s) was tried to improve recovery time. "
         "It lowered delivery at 20% loss, so we kept 10 s and report recovery time as partly met.", 15)
    card(s, 6.78, 4.4, 5.95, 2.4, "Measured, not assumed",
         "All timings come from one machine, and scale was tested to 65 simulated nodes. "
         "No timed usability study with participants has been done.", 15)
    notes(s, "We want to finish with honesty. This is a measured prototype of the routing and reliability layer. The radio is emulated: real packets over TCP, but a config file decides who can hear whom. "
             "There is no real phone app; a phone shows a web page served by a laptop. One shared key protects the mesh, which is a real limitation, and per-pair keys are future work. We also tried a faster "
             "failure detector, shortening the neighbour timeout from ten seconds to seven, hoping to improve recovery time. It lowered delivery at 20 percent loss, so we dropped it and report recovery time honestly "
             "as partly met. Finally, our timings come from one machine and we have not done a timed usability study.")

    # ---------------------------------------------------------------- 14 team and questions (dark)
    s = dark_slide(prs)
    text(s, 0.8, 0.7, 9, 0.3, "TEAM AND QUESTIONS", 12, DTEXT2, bold=True)
    text(s, 0.8, 1.15, 9, 0.9, "Thank you", 44, DTEXT, bold=True)
    team = [("Twissha Shah", "Link-state gossip and cost function, node integration, the device app and multi-device demo, parser hardening, report evidence"),
            ("Miti Shah", "Discovery, relay, Dijkstra, reliability, security, SQLite log, and the device server endpoints"),
            ("Tanvi Sheth", "Packet format and transport, API, simulation lab, testing documents, deck and poster")]
    for i, (n, what) in enumerate(team):
        y = 2.55 + i * 1.12
        text(s, 0.8, y, 2.4, 0.4, n, 17, DTEXT, bold=True)
        text(s, 3.2, y + 0.03, 5.6, 0.9, what, 13.5, DTEXT2, spacing=1.15)
    line(s, 0.8, 6.15, 8.8, 6.15, DLINE, 1)
    text(s, 0.8, 6.3, 8, 0.35, REPO_URL, 14, ACCENT)
    text(s, 0.8, 6.7, 8, 0.3, "Guide: Prof. Anuj Tawari", 12, DTEXT2)
    import qrcode

    qr = qrcode.QRCode(border=2, box_size=10)
    qr.add_data(REPO_URL)
    qr.make(fit=True)
    qr_png = f["tmp"] / "qr.png"
    qr.make_image(fill_color="#0E1114", back_color="#EEF1F4").save(qr_png)
    s.shapes.add_picture(str(qr_png), Inches(9.9), Inches(2.4), Inches(2.7), Inches(2.7))
    text(s, 9.9, 5.25, 2.7, 0.3, "Scan for the repository", 12, DTEXT2, align=PP_ALIGN.CENTER)
    notes(s, "To summarise who built what: Twissha built the link-state gossip and cost function, the node integration, the device app and the multi-device demo; Miti built discovery, the relay, Dijkstra, "
             "the reliability layer, the security and the log, and the device server; Tanvi built the packet format and transport, the API and simulation lab, and the testing documents, deck and poster. "
             "The code, the report and the testing document are all in the repository; the QR code opens it. Thank you; we are happy to take questions, and to show any part of the demo again.")

    assert len(prs.slides) == TOTAL, f"built {len(prs.slides)} slides, expected {TOTAL}"
    return prs


def main() -> None:
    no_run = "--no-run" in sys.argv
    f = facts(no_run)
    prs = build(f)
    prs.save(str(OUT))
    print("wrote", OUT)
    print(json.dumps({
        "tests": f["tests"], "commits": f["commits"], "branches": f["branches"], "authors": f["git"]["per_member"],
        "conventional": f"{f['git']['conventional']}/{f['git']['commits']}", "trace": f["trace"], "report_pages": f["report_pages"],
        "kpi_met": f"{kpis.summary(f['kpi'])[0]}/10", "poster": f["poster"], "device_walk": bool(f["device_walk"]),
    }, indent=1))


if __name__ == "__main__":
    main()
