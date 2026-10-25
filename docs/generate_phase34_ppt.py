"""Generates the combined Phase III + Phase IV presentation for EcoMesh.

It reuses the helpers of ``generate_phase3_ppt.py`` so the deck keeps the same
template as the Phase II and Phase III decks (dark background, coral titles,
cyan highlights, numbered eyebrows, card and table layouts, footer with the
slide number). Every figure on the slides comes from the repository: the test
run, ``docs/report/evidence/results/*.json`` and ``git log``.

    python docs/generate_phase34_ppt.py
"""

from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import generate_phase3_ppt as t  # noqa: E402  (the template helpers)
from pptx.chart.data import CategoryChartData  # noqa: E402
from pptx.dml.color import RGBColor  # noqa: E402
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION, XL_TICK_LABEL_POSITION, XL_TICK_MARK  # noqa: E402
from pptx.enum.shapes import MSO_SHAPE  # noqa: E402
from pptx.enum.text import PP_ALIGN  # noqa: E402
from pptx.util import Emu, Inches, Pt  # noqa: E402

OUT = HERE / "Phase_III_IV_EcoMesh_Group20.pptx"
ASSETS = HERE / "ppt_assets"
TOTAL = 19
t.TOTAL_SLIDES = TOTAL

BG, CARD_BG, BORDER = t.BG, t.CARD_BG, t.CARD_BORDER
CORAL, CYAN, WHITE, GREY = t.CORAL, t.CYAN, t.WHITE, t.GREY
GREEN = RGBColor(0x5E, 0xEA, 0xA0)
AMBER = RGBColor(0xFF, 0xC8, 0x5C)

I = Inches


# ---------------------------------------------------------------- small helpers

def text(s, x, y, w, h, value, size, color=WHITE, **kw):
    return t.add_text(s, I(x), I(y), I(w), I(h), value, size, color, **kw)


def lines(s, x, y, w, h, items, size, color=WHITE, **kw):
    return t.add_multiline(s, I(x), I(y), I(w), I(h), items, size, color, **kw)


def card(s, x, y, w, h):
    return t.card(s, I(x), I(y), I(w), I(h))


def titled_card(s, x, y, w, h, head, body, head_color=CORAL, size=12, head_size=12.5):
    card(s, x, y, w, h)
    text(s, x + 0.28, y + 0.2, w - 0.56, 0.4, head, head_size, head_color, bold=True)
    text(s, x + 0.28, y + 0.68, w - 0.56, h - 0.85, body, size, WHITE, line_spacing=1.2)


def stat(s, x, y, w, h, value, label, color=CYAN, value_size=34):
    card(s, x, y, w, h)
    text(s, x + 0.2, y + 0.18, w - 0.4, 0.8, value, value_size, color, bold=True)
    text(s, x + 0.2, y + h - 0.85, w - 0.4, 0.75, label, 11.5, GREY, line_spacing=1.15)


def table(s, x, y, w, col_w, header, rows, row_h=0.46, size=11, head_size=11, colors=None):
    """Same look as the Phase III deck's table: cyan header, card-coloured body.
    ``colors`` maps (row, col) -> RGB for the cells that carry a verdict."""
    shape = s.shapes.add_table(len(rows) + 1, len(header), I(x), I(y), I(w), I(row_h * (len(rows) + 1)))
    tbl = shape.table
    total = sum(col_w)
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Emu(int(I(w) * cw / total))
    for r in range(len(rows) + 1):
        tbl.rows[r].height = I(row_h)
    for j, h in enumerate(header):
        c = tbl.cell(0, j)
        c.text = h
        c.fill.solid()
        c.fill.fore_color.rgb = t.TABLE_HEAD
        run = c.text_frame.paragraphs[0].runs[0]
        run.font.bold, run.font.size, run.font.name = True, Pt(head_size), "Arial"
        run.font.color.rgb = t.TABLE_HEAD_TEXT
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            c = tbl.cell(i + 1, j)
            c.text = str(val)
            c.fill.solid()
            c.fill.fore_color.rgb = CARD_BG
            c.vertical_anchor = 1
            run = c.text_frame.paragraphs[0].runs[0]
            run.font.size, run.font.name = Pt(size), "Arial"
            run.font.color.rgb = (colors or {}).get((i, j), WHITE)
            run.font.bold = (i, j) in (colors or {})
    return tbl


def arrow(s, x, y, w=0.45, h=0.3):
    a = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, I(x), I(y), I(w), I(h))
    a.fill.solid()
    a.fill.fore_color.rgb = CYAN
    a.line.fill.background()
    a.shadow.inherit = False
    return a


def style_chart(chart, legend=True):
    chart.font.size = Pt(11)
    chart.font.color.rgb = WHITE
    chart.font.name = "Arial"
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.BOTTOM
        chart.legend.include_in_layout = False
        chart.legend.font.color.rgb = WHITE
        chart.legend.font.size = Pt(11)
    va, ca = chart.value_axis, chart.category_axis
    va.major_gridlines.format.line.color.rgb = BORDER
    va.format.line.fill.background()
    ca.format.line.color.rgb = BORDER
    va.tick_labels.font.color.rgb = GREY
    ca.tick_labels.font.color.rgb = WHITE


def hide_value_axis(chart):
    va = chart.value_axis
    va.has_major_gridlines = False
    va.tick_label_position = XL_TICK_LABEL_POSITION.NONE
    va.major_tick_mark = XL_TICK_MARK.NONE
    va.format.line.fill.background()


def header(s, n, label, title, subtitle=None):
    return t.chrome(s, t.eyebrow_label(n, label), title, n, subtitle=subtitle)


# ---------------------------------------------------------------- the deck

def build():
    prs = t.new_presentation()

    # ======================================================= 1 title
    s = t.blank_slide(prs)
    text(s, 0.7, 0.6, 8, 0.4, "MINI PROJECT I · GROUP 20", 13, WHITE, bold=True)
    text(s, 0.68, 1.5, 10, 1.3, "EcoMesh", 60, CORAL, bold=True)
    text(s, 0.7, 2.75, 10.5, 0.9, "Distributed Peer-to-Peer Disaster\nRelief Communication Mesh", 22, WHITE, line_spacing=1.15)
    text(s, 0.7, 3.95, 11.5, 0.4, "PHASE III & IV — MODULE-WISE CODING TO A TESTED, INTEGRATED SYSTEM", 15, CORAL, bold=True)
    ln = s.shapes.add_connector(1, I(0.7), I(4.5), I(12.6), I(4.5))
    ln.line.color.rgb, ln.line.width = BORDER, Pt(1)
    text(s, 0.7, 4.75, 3, 0.3, "TEAM", 11, GREY, bold=True)
    text(s, 0.7, 5.05, 10, 0.4, "Miti Shah  ·  Twissha Shah  ·  Tanvi Sheth", 16, WHITE)
    text(s, 0.7, 5.6, 3, 0.3, "GUIDE", 11, GREY, bold=True)
    text(s, 1.65, 5.57, 6, 0.4, "Prof. Anuj Tawari", 16, WHITE)

    # ======================================================= 2 agenda
    s = t.blank_slide(prs)
    header(s, 2, "AGENDA", "Two phases, six deliverables")
    cols = [
        ("PHASE III", CORAL, ["Module-wise coding", "Git repository setup", "Git branching strategy and commit conventions"]),
        ("PHASE IV", CYAN, ["Integration of front-end and back-end", "Functional and non-functional testing", "Report"]),
    ]
    for c, (name, color, items) in enumerate(cols):
        x = 0.55 + c * 6.25
        card(s, x, 1.6, 5.95, 4.9)
        text(s, x + 0.35, 1.85, 5, 0.4, name, 14, color, bold=True)
        for i, item in enumerate(items):
            y = 2.55 + i * 1.3
            text(s, x + 0.35, y, 0.9, 0.7, f"P{i + 1}", 26, color, bold=True)
            text(s, x + 1.3, y + 0.05, 4.3, 0.9, item, 17, WHITE, line_spacing=1.1)

    # ======================================================= 3 modules table
    s = t.blank_slide(prs)
    header(s, 3, "PHASE III · P1 MODULE-WISE CODING", "Eleven modules, each with its own tests",
           subtitle="One module per concern in mesh/core/, written and tested in isolation before being wired together.")
    rows = [
        ("packet.py", "362", "52-byte binary header, path, payload, signature", "47"),
        ("transport · udp · sim", "327", "One interface; real sockets or an in-memory radio", "21"),
        ("discovery.py", "292", "HELLO beacons, neighbour table, death detection", "15"),
        ("relay.py", "153", "Forward, deliver, TTL, loop check, priority queue", "18"),
        ("routing.py", "546", "Link-state gossip, weighted cost, Dijkstra", "61"),
        ("reliability.py", "240", "Dedup, priority queue, ACK + retry, store-and-forward", "38"),
        ("crypto.py", "131", "AES-256-GCM payloads, Ed25519 signatures", "19"),
        ("store.py", "258", "SQLite (WAL) message, event and peer log", "23"),
        ("node.py", "513", "Wires every layer into one asyncio node", "27"),
    ]
    table(s, 0.55, 2.05, 12.2, [2.3, 0.8, 6.6, 0.8], ["MODULE", "LINES", "WHAT IT DOES", "TESTS"], rows, row_h=0.42, size=11.5)
    text(s, 0.55, 6.5, 12.2, 0.4, "2,822 lines of engine code  ·  4,547 lines of tests  ·  a test file for every module", 13, CYAN, bold=True)

    # ======================================================= 4 one message
    s = t.blank_slide(prs)
    header(s, 4, "PHASE III · P1 MODULE-WISE CODING", "One message, six modules",
           subtitle="How the modules cooperate when someone sends an SOS.")
    steps = [
        ("01", "PACKET", "Builds the 52-byte header: priority 0 (SOS), ttl 10, a random msg_id."),
        ("02", "ROUTING", "Dijkstra over the link-state graph picks the cheapest next hop. RESCUE__ means any gateway."),
        ("03", "SECURITY", "Payload sealed with AES-256-GCM; identity fields signed with Ed25519."),
        ("04", "RELAY", "Each hop decrements ttl, appends itself to the path and sends SOS before routine traffic."),
        ("05", "RELIABILITY", "Destination ACKs. A missed ACK retries on a recomputed route; no route means it is held."),
        ("06", "STORE", "Every send, forward, retry and drop is logged in SQLite. Metrics are queries over it."),
    ]
    for i, (num, head, body) in enumerate(steps):
        col, row = i % 3, i // 3
        x, y = 0.55 + col * 4.12, 2.1 + row * 2.45
        card(s, x, y, 3.95, 2.25)
        text(s, x + 0.25, y + 0.15, 1, 0.5, num, 22, CORAL, bold=True)
        text(s, x + 1.05, y + 0.25, 2.8, 0.4, head, 13, CYAN, bold=True)
        text(s, x + 0.25, y + 0.8, 3.45, 1.4, body, 12, WHITE, line_spacing=1.2)

    # ======================================================= 5 bugs
    s = t.blank_slide(prs)
    header(s, 5, "PHASE III · P1 MODULE-WISE CODING", "Four bugs that would have failed silently",
           subtitle="Found by writing the tests, not by guessing. Each one is now a regression test.")
    fixes = [
        ("GRAPH STUCK AT TWO HOPS", "Link-state reports weren't re-flooded past the first neighbour, so no node could learn a route beyond 2 hops. Fixed with origin + sequence numbers."),
        ("FAILURES NEVER PENALISED", "Retry logic never told routing about a timed-out link, so the cost function's failure term was always zero. Now every ACK timeout updates the cost at once."),
        ("RETENTION QUEUE UNBOUNDED", "Store-and-forward had no limit. It now holds 500 messages for 30 minutes and evicts the lowest-priority first, so an SOS is never displaced."),
        ("SIGNATURES BREAK AT HOP 1", "ttl, hop_count and path change at every relay, so signing them invalidates the signature after one hop. Now only fields that never change are signed."),
    ]
    for i, (head, body) in enumerate(fixes):
        titled_card(s, 0.55 + (i % 2) * 6.25, 2.1 + (i // 2) * 2.45, 5.95, 2.25, head, body, size=13)

    # ======================================================= 6 repository
    s = t.blank_slide(prs)
    header(s, 6, "PHASE III · P2 GIT REPOSITORY SETUP", "One repository, laid out so each concern has a home")
    card(s, 0.55, 1.6, 5.9, 5.1)
    text(s, 0.85, 1.8, 5, 0.35, "REPOSITORY LAYOUT", 12, CYAN, bold=True)
    tree = [
        ("mesh/core/", "the engine: 11 modules"),
        ("api/", "FastAPI + WebSocket server, mesh lab"),
        ("sim/", "simulator runner and scenarios"),
        ("story/", "real-socket multi-device demo"),
        ("ui/", "React website (PWA)"),
        ("tests/", "18 test files, 312 test cases"),
        ("docs/", "plan, SRS, algorithms, report"),
        ("Phase-2/", "UML diagrams"),
        ("config/", "node configuration"),
    ]
    for i, (name, desc) in enumerate(tree):
        y = 2.3 + i * 0.47
        text(s, 0.85, y, 1.9, 0.4, name, 12.5, CORAL, bold=True, font="Consolas")
        text(s, 2.75, y, 3.6, 0.4, desc, 12, WHITE)
    card(s, 6.8, 1.6, 5.95, 5.1)
    text(s, 7.1, 1.8, 5, 0.35, "WHAT WAS SET UP", 12, CORAL, bold=True)
    lines(s, 7.1, 2.3, 5.4, 4.3, [
        "Hosted on GitHub as a public repository, with all three members as contributors.",
        "README, CONTRIBUTING.md (branches and commit style) and a .gitignore from the first day.",
        "requirements.txt and pytest.ini so a fresh clone installs and tests in two commands.",
        "docs/ holds the master project plan, SRS, algorithm design, contribution log and the report.",
        "Tag v0.3-phase3 marks the end of Phase III.",
    ], 12.5, WHITE, space_after=12, line_spacing=1.15)

    # ======================================================= 7 branching
    s = t.blank_slide(prs)
    header(s, 7, "PHASE III · P3 BRANCHING STRATEGY", "One branch per phase, each inheriting the last",
           subtitle="A phase branch is a snapshot a reviewer can open, run and grade on its own.")
    branches = [
        ("develop", "Phase 1", "14", "packet, transport"),
        ("develop_2", "Phase 2", "16", "discovery, relay, simulator"),
        ("develop_3", "Phase 3", "39", "routing, reliability, crypto, store"),
        ("develop_4", "Phase 4", "48", "API, website, tests, devices"),
        ("develop_5", "Phase 5", "49", "report and evaluation"),
    ]
    bw, gap = 2.2, 0.3
    for i, (name, phase, n, what) in enumerate(branches):
        x = 0.55 + i * (bw + gap)
        card(s, x, 2.15, bw, 2.3)
        text(s, x + 0.2, 2.3, bw - 0.4, 0.3, phase.upper(), 10.5, GREY, bold=True)
        text(s, x + 0.2, 2.62, bw - 0.4, 0.4, name, 15, CYAN, bold=True, font="Consolas")
        text(s, x + 0.2, 3.1, bw - 0.4, 0.55, n, 28, CORAL, bold=True)
        text(s, x + 0.2, 3.65, bw - 0.4, 0.7, f"commits · {what}", 10.5, WHITE, line_spacing=1.1)
        if i < len(branches) - 1:
            arrow(s, x + bw + 0.0, 3.15, 0.3, 0.26)
    card(s, 0.55, 4.8, 5.95, 1.95)
    text(s, 0.85, 4.95, 5.4, 0.35, "RULES WE AGREED", 12, CORAL, bold=True)
    lines(s, 0.85, 5.35, 5.4, 1.4, [
        "Never merge between phase branches.",
        "Each member runs their own git commands.",
        "No force-pushes (one agreed exception, below).",
    ], 12.5, WHITE, space_after=6)
    card(s, 6.8, 4.8, 5.95, 1.95)
    text(s, 7.1, 4.95, 5.4, 0.35, "MAIN AND TAGS", 12, CYAN, bold=True)
    text(s, 7.1, 5.35, 5.4, 1.35, "main is reserved for tagged releases and holds one README commit today. "
         "Once, the history of develop_2 to develop_5 was rewritten to correct author names; file contents were identical.",
         12.5, WHITE, line_spacing=1.2)

    # ======================================================= 8 commit conventions
    s = t.blank_slide(prs)
    header(s, 8, "PHASE III · P3 COMMIT CONVENTIONS", "Conventional Commits, small and often")
    card(s, 0.55, 1.6, 6.0, 5.1)
    text(s, 0.85, 1.8, 5.4, 0.35, "FORMAT", 12, CORAL, bold=True)
    text(s, 0.85, 2.2, 5.4, 0.5, "type(scope): short description", 17, CYAN, bold=True, font="Consolas")
    text(s, 0.85, 2.85, 5.4, 0.35, "REAL EXAMPLES FROM THE LOG", 12, CORAL, bold=True)
    lines(s, 0.85, 3.25, 5.5, 3.4, [
        "feat(api): FastAPI + WebSocket server, mesh lab and virtual-time simulator",
        "fix(reliability): make multi-hop ACK and retry actually work",
        "test: configure pytest import path",
        "docs: add Phase III presentation deck",
        "chore: initialize mesh packages",
    ], 11.5, WHITE, space_after=9, font="Consolas", line_spacing=1.1)
    card(s, 6.8, 1.6, 5.95, 3.3)
    text(s, 7.1, 1.75, 5.4, 0.35, "COMMITS BY TYPE (49 ON develop_5)", 12, CYAN, bold=True)
    cd = CategoryChartData()
    cd.categories = ["feat", "docs", "chore", "fix", "test", "other"]
    cd.add_series("commits", (25, 10, 4, 3, 2, 5))
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, I(6.95), I(2.1), I(5.7), I(2.75), cd)
    ch = gf.chart
    style_chart(ch, legend=False)
    ch.category_axis.reverse_order = True
    hide_value_axis(ch)
    pl = ch.plots[0]
    pl.gap_width = 45
    pl.has_data_labels = True
    pl.data_labels.font.color.rgb, pl.data_labels.font.size = WHITE, Pt(11)
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.series[0].format.fill.solid()
    pl.series[0].format.fill.fore_color.rgb = CORAL
    card(s, 6.8, 5.1, 5.95, 1.6)
    text(s, 7.1, 5.22, 5.4, 0.35, "WHO COMMITTED", 12, CORAL, bold=True)
    text(s, 7.1, 5.6, 5.5, 1.1, "Tanvi 19  ·  Twissha 18  ·  Miti 12\nAll 5 \"other\" commits are from Phases 1 and 2; every commit since follows the convention.",
         12, WHITE, line_spacing=1.2)

    # ======================================================= 9 architecture
    s = t.blank_slide(prs)
    header(s, 9, "PHASE IV · P1 FRONT-END + BACK-END", "The website is a window onto the real engine",
           subtitle="No mock data anywhere: every number on screen is read from a running Node and its SQLite log.")
    boxes = [
        ("WEBSITE", "React PWA, 9 pages", "ui/"),
        ("API", "FastAPI: REST + WebSocket", "api/server.py"),
        ("MESH LAB", "Real Node objects, one process", "api/lab.py"),
        ("TRANSPORT", "Simulated radio or real TCP", "transport_sim.py · story/"),
    ]
    bw = 2.75
    for i, (head, body, path) in enumerate(boxes):
        x = 0.55 + i * (bw + 0.4)
        card(s, x, 2.3, bw, 2.1)
        text(s, x + 0.2, 2.45, bw - 0.4, 0.35, head, 13, CYAN, bold=True)
        text(s, x + 0.2, 2.9, bw - 0.4, 0.7, body, 13, WHITE, line_spacing=1.15)
        text(s, x + 0.2, 3.85, bw - 0.4, 0.4, path, 10.5, GREY, font="Consolas")
        if i < 3:
            arrow(s, x + bw + 0.02, 3.2, 0.36, 0.28)
    titled_card(s, 0.55, 4.75, 3.95, 1.95, "REST", "Send a message or SOS, list peers, route and path costs, message history, statistics, switch nodes on and off.", size=11.5)
    titled_card(s, 4.7, 4.75, 3.95, 1.95, "WEBSOCKET", "Every engine event is pushed as it is logged: sent, forwarded, received, retried, held. The screen animates from it.", size=11.5)
    titled_card(s, 8.85, 4.75, 3.9, 1.95, "SIMULATOR", "The same engine runs headless on a virtual clock, so 50 simulated mesh lifetimes take seconds.", size=11.5)

    # ======================================================= 10 screens
    s = t.blank_slide(prs)
    header(s, 10, "PHASE IV · P1 FRONT-END + BACK-END", "Two views, built for two kinds of user")
    node_img = s.shapes.add_picture(str(ASSETS / "node.png"), I(0.55), I(1.5), height=I(4.95))
    rescue_img = s.shapes.add_picture(str(ASSETS / "rescue.png"), I(3.75), I(1.5), width=I(6.1))
    for pic in (node_img, rescue_img):
        pic.line.color.rgb = BORDER
        pic.line.width = Pt(1)
    text(s, 0.55, 6.55, 3.0, 0.3, "NODE VIEW", 11, CYAN, bold=True)
    text(s, 3.75, 5.5, 6.0, 0.3, "RESCUE DASHBOARD", 11, CYAN, bold=True)
    text(s, 3.75, 5.85, 6.1, 0.9, "Both read the same running mesh. Send an SOS on the left and it appears in the queue on the right with the route it took.",
         12, WHITE, line_spacing=1.2)
    lines(s, 10.15, 1.6, 2.65, 5.2, [
        ("NODE VIEW", True),
        "Long-press to arm the SOS button.",
        "Who is reachable and how many hops.",
        "Each message: sending, relayed via N nodes, delivered.",
        ("", False),
        ("RESCUE DASHBOARD", True),
        "Live mesh graph.",
        "SOS queue with sender, route and time since sent.",
        "Delivery log and live statistics.",
    ], 11.5, WHITE, space_after=5, line_spacing=1.1)

    # ======================================================= 11 integration found
    s = t.blank_slide(prs)
    header(s, 11, "PHASE IV · P1 FRONT-END + BACK-END", "Integration found what unit tests could not",
           subtitle="Wiring the screens to the engine exposed four defects. Each is fixed and has a regression test.")
    found = [
        ("MULTI-HOP ACKS WERE DROPPED", "Duplicate filtering keyed on msg_id alone dropped an ACK at the first relay its DATA had crossed, and swallowed retries. Fixed with a (type, msg_id, attempt) key and a retry counter in the header."),
        ("LINK QUALITY WAS NEVER MEASURED", "Nothing fed the cost function, so every link looked perfect. It is now measured from HELLO reception, which is what makes weighted routing win."),
        ("DEAD NODES STAYED ROUTABLE", "A newer link-state report added edges but never removed them, so distant nodes kept routing through a dead one. A report now replaces the old one."),
        ("FUZZING AND SHUTDOWN", "Random bytes showed a parser raising the wrong exception on non-ASCII node ids, and Node.stop() could hang on Windows. Both fixed."),
    ]
    for i, (head, body) in enumerate(found):
        titled_card(s, 0.55 + (i % 2) * 6.25, 2.1 + (i // 2) * 2.45, 5.95, 2.25, head, body, size=12.5)

    # ======================================================= 12 real devices
    s = t.blank_slide(prs)
    header(s, 12, "PHASE IV · P1 FRONT-END + BACK-END", "From the simulator to real sockets",
           subtitle="story/ runs each device as its own process with its own TCP port and web page.")
    stats = [("47 ms", "median SOS latency to the rescue node (p95 102 ms, 30 of 30 acknowledged)"),
             ("~4 s", "average reroute after a relay is killed; all 8 trials still delivered"),
             ("4.2 s", "average to flush 5 held SOS messages once the gateway returns (4 of 4 trials)"),
             ("3.8 s", "from starting 5 processes to every node knowing the whole mesh")]
    for i, (v, lab) in enumerate(stats):
        stat(s, 0.55 + i * 3.1, 2.1, 2.95, 2.2, v, lab)
    card(s, 0.55, 4.6, 12.2, 2.1)
    text(s, 0.85, 4.75, 5, 0.35, "HOW IT RUNS", 12, CORAL, bold=True)
    lines(s, 0.85, 5.15, 11.6, 1.5, [
        "python -m story.local starts all five devices on one machine; python -m story.node --id L1 starts one per laptop.",
        "A topology file decides who can hear whom, which emulates radio range on a flat Wi-Fi network.",
        "The two-laptop split worked over a phone hotspot with three devices on one laptop and two on the other.",
    ], 12.5, WHITE, space_after=8, line_spacing=1.15)

    # ======================================================= 13 testing strategy
    s = t.blank_slide(prs)
    header(s, 13, "PHASE IV · P2 FUNCTIONAL AND NON-FUNCTIONAL TESTING", "Two questions: does it work, and how well")
    stat(s, 0.55, 1.6, 2.9, 1.9, "312", "automated test cases across 18 files; all pass on the latest run")
    stat(s, 3.65, 1.6, 2.9, 1.9, "68", "functional requirements, each traced to the test or check that verifies it")
    stat(s, 6.75, 1.6, 2.9, 1.9, "20-50", "seeded simulation runs per scenario, with packet loss and injected failures")
    stat(s, 9.85, 1.6, 2.9, 1.9, "9", "website pages walked through in a real browser, with no console errors")
    card(s, 0.55, 3.75, 5.95, 2.45)
    text(s, 0.85, 3.9, 5.4, 0.35, "FUNCTIONAL: DOES IT DO WHAT THE SRS SAYS", 12, CORAL, bold=True)
    lines(s, 0.85, 4.35, 5.4, 1.8, [
        "Unit tests for each module.",
        "Integration tests across modules and over the API.",
        "A scripted browser run through every page and all six demo beats.",
    ], 12.5, WHITE, space_after=9, line_spacing=1.15)
    card(s, 6.8, 3.75, 5.95, 2.45)
    text(s, 7.1, 3.9, 5.4, 0.35, "NON-FUNCTIONAL: HOW WELL", 12, CYAN, bold=True)
    lines(s, 7.1, 4.35, 5.4, 1.8, [
        "Performance, delivery and recovery against 10 targets (KPIs).",
        "Scalability to 65 simulated nodes.",
        "Security attacks, fuzzing and real-socket tests.",
    ], 12.5, WHITE, space_after=9, line_spacing=1.15)

    text(s, 0.55, 6.4, 12.2, 0.4, "Re-run everything with one command:  python -m pytest -q", 13, CYAN, bold=True, font="Consolas")

    # ======================================================= 14 functional
    s = t.blank_slide(prs)
    header(s, 14, "PHASE IV · P2 FUNCTIONAL TESTING", "Every requirement traced to evidence",
           subtitle="68 functional requirements: 52 by automated tests alone, 10 by tests plus a manual look at the screen.")
    rows = [
        ("Discovery and neighbours", "15", "HELLO, neighbour table, death after 10 s"),
        ("Routing", "61", "gossip, Dijkstra, weighted path beats shorter path"),
        ("Reliability", "38", "priority, dedup, ACK, retry, bounded store-and-forward"),
        ("Security", "19", "relay cannot decrypt; forged and tampered rejected"),
        ("Storage", "23", "message, event and peer log queries"),
        ("API and website", "12 + browser", "REST, WebSocket, 9 pages, six demo beats"),
    ]
    table(s, 0.55, 2.2, 12.2, [2.6, 1.3, 5.6], ["AREA", "TESTS", "WHAT IS PROVEN"], rows, row_h=0.5, size=12)
    text(s, 0.55, 5.9, 12.2, 0.9, "Not fully met: 2 requirements are partial (immediate flush when a new neighbour appears; a history filter on the screens), "
         "2 are verified by code inspection and 2 by a manual check only.", 12.5, AMBER, line_spacing=1.2)

    # ======================================================= 15 non-functional table
    s = t.blank_slide(prs)
    header(s, 15, "PHASE IV · P2 NON-FUNCTIONAL TESTING", "Ten targets, measured, and honest about the misses")
    rows = [
        ("Delivery ratio", ">= 90%", "92.6% over 50 runs (40 nodes, 20% loss, failures)", "MET"),
        ("Convergence", "<= 15 s", "9.6 s mean; 47 of 50 runs within target", "MET"),
        ("Recovery after relay death", "<= 10 s", "8.1 s mean, but 27 of 50 runs took 10.2 s", "PARTLY"),
        ("SOS latency advantage", ">= 3x", "4.4x faster than routine traffic", "MET"),
        ("Store-and-forward flush", "100%", "201 of 201 flushed", "MET"),
        ("Weighted vs hop-count", "weighted wins", "99.2% against 57.4%", "MET"),
        ("Scale", "50 nodes", "100% at 5% loss; 88.2% at 20% loss", "PARTLY"),
        ("Screen freshness", "<= 2 s", "API median 16 ms; screens poll every 0.7 s", "MET"),
        ("Correctness", "all pass", "311 of 312 in all 3 runs; 1 timing-sensitive test failed once", "PARTLY"),
        ("Security", "all hold", "no decrypt at relays; forged and tampered rejected", "MET"),
    ]
    colors = {(i, 3): (GREEN if r[3] == "MET" else AMBER) for i, r in enumerate(rows)}
    table(s, 0.55, 1.5, 12.2, [2.6, 1.4, 6.4, 1.0], ["KPI", "TARGET", "MEASURED", "VERDICT"], rows, row_h=0.46, size=11, colors=colors)

    # ======================================================= 16 charts
    s = t.blank_slide(prs)
    header(s, 16, "PHASE IV · P2 NON-FUNCTIONAL TESTING", "The two results that carry the design")
    card(s, 0.55, 1.5, 5.95, 5.2)
    text(s, 0.85, 1.65, 5.4, 0.35, "WEIGHTED ROUTING VS HOP COUNT", 12, CORAL, bold=True)
    text(s, 0.85, 2.0, 5.4, 0.35, "delivery % on identical seeds, 20 runs", 11, GREY)
    cd = CategoryChartData()
    cd.categories = ["Hop count", "Weighted"]
    cd.add_series("delivery %", (57.4, 99.2))
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, I(0.8), I(2.4), I(5.4), I(4.1), cd)
    ch = gf.chart
    style_chart(ch, legend=False)
    ch.value_axis.maximum_scale, ch.value_axis.minimum_scale = 115, 0
    hide_value_axis(ch)
    pl = ch.plots[0]
    pl.gap_width = 70
    pl.vary_by_categories = False
    pl.has_data_labels = True
    pl.data_labels.font.size, pl.data_labels.font.bold = Pt(16), True
    pl.data_labels.font.color.rgb = WHITE
    pl.data_labels.number_format, pl.data_labels.number_format_is_linked = '0.0"%"', False
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for idx, color in enumerate((GREY, CYAN)):
        pt = pl.series[0].points[idx]
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = color
    card(s, 6.8, 1.5, 5.95, 5.2)
    text(s, 7.1, 1.65, 5.4, 0.35, "DELIVERY AS THE MESH GROWS", 12, CORAL, bold=True)
    text(s, 7.1, 2.0, 5.4, 0.35, "delivery % against number of nodes", 11, GREY)
    cd = CategoryChartData()
    cd.categories = ["10", "21", "31", "43", "50", "65"]
    cd.add_series("5% loss", (100.0, 100.0, 100.0, 100.0, 100.0, 98.9))
    cd.add_series("20% loss", (100.0, 97.9, 95.7, 95.8, 88.2, 86.0))
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, I(7.05), I(2.4), I(5.5), I(4.1), cd)
    ch = gf.chart
    style_chart(ch, legend=True)
    ch.value_axis.minimum_scale, ch.value_axis.maximum_scale = 80, 100
    ch.value_axis.tick_labels.number_format, ch.value_axis.tick_labels.number_format_is_linked = '0"%"', False
    for series, color in zip(ch.plots[0].series, (CYAN, CORAL)):
        series.format.line.color.rgb = color
        series.format.line.width = Pt(2.5)
        series.marker.format.fill.solid()
        series.marker.format.fill.fore_color.rgb = color
        series.marker.format.line.color.rgb = color
        series.smooth = False

    # ======================================================= 17 report
    s = t.blank_slide(prs)
    header(s, 17, "PHASE IV · P3 REPORT", "A 55-page report whose numbers come from the code")
    card(s, 0.55, 1.6, 5.95, 5.1)
    text(s, 0.85, 1.8, 5.4, 0.35, "ELEVEN CHAPTERS, AS THE GUIDELINES REQUIRE", 12, CORAL, bold=True)
    chapters = ["1 Introduction", "2 Literature survey", "3 Requirements (SRS)", "4 Design", "5 Algorithms", "6 Subjects applied",
                "7 Implementation", "8 Performance", "9 Testing", "10 Results", "11 Conclusion"]
    lines(s, 0.85, 2.35, 2.7, 4.2, chapters[:6], 14, WHITE, space_after=16)
    lines(s, 3.5, 2.35, 2.9, 4.2, chapters[6:], 14, WHITE, space_after=16)
    card(s, 6.8, 1.6, 5.95, 2.6)
    text(s, 7.1, 1.8, 5.4, 0.35, "EVIDENCE PIPELINE", 12, CYAN, bold=True)
    text(s, 7.1, 2.25, 5.4, 1.9, "Measurements are saved as JSON, scripts turn them into LaTeX tables and number macros, and the report includes them. "
         "Every number in Chapters 8 to 10 comes from those measurements, so a code change can be re-measured and the tables rebuilt.", 12.5, WHITE, line_spacing=1.2)
    card(s, 6.8, 4.45, 5.95, 2.25)
    text(s, 7.1, 4.6, 5.4, 0.35, "BUILT FROM", 12, CORAL, bold=True)
    lines(s, 7.1, 5.0, 5.4, 1.7, [
        "The department Overleaf template and the Mini Project Report Preparation Guidelines.",
        "12 pages of front matter, 11 chapters and references.",
        "Source in docs/report/latex; PDF in docs/report.",
    ], 12, WHITE, space_after=6, line_spacing=1.1)

    # ======================================================= 18 status
    s = t.blank_slide(prs)
    header(s, 18, "STATUS", "What is done, what is left, what we are honest about")
    titled_card(s, 0.55, 1.6, 3.95, 4.1, "DONE", "Engine, API, website, simulator with seven scenarios, real-socket demo, 312 tests, the report and this deck.", head_color=GREEN, size=14)
    card(s, 4.7, 1.6, 3.95, 4.1)
    text(s, 4.98, 1.8, 3.4, 0.4, "STILL TO DO", 12.5, CORAL, bold=True)
    lines(s, 4.98, 2.3, 3.4, 4.3, [
        "Poster or paper for the end-semester evaluation.",
        "Plagiarism report.",
        "Photo of the two-laptop run for Chapter 10.",
        "Printed, bound copy and the guide's review.",
        "Optional usability test with 5 people.",
    ], 13.5, WHITE, space_after=14, line_spacing=1.12)
    card(s, 8.85, 1.6, 3.9, 4.1)
    text(s, 9.13, 1.8, 3.4, 0.4, "KNOWN LIMITS", 12.5, AMBER, bold=True)
    lines(s, 9.13, 2.3, 3.4, 4.3, [
        "No radio hardware: the radio is a neighbour-restricted LAN.",
        "One shared key for the whole mesh.",
        "Recovery is bounded by the 10 s heartbeat.",
        "Delivery drops below 90% past about 43 nodes at 20% loss.",
        "No automated browser tests.",
    ], 13.5, WHITE, space_after=14, line_spacing=1.12)

    text(s, 0.55, 6.0, 12.2, 0.6, "What remains is documentation and evaluation material, not engine code.", 15, CYAN, bold=True)

    # ======================================================= 19 close
    s = t.blank_slide(prs)
    text(s, 0.7, 2.2, 11, 1.2, "Thank you", 54, CORAL, bold=True)
    text(s, 0.7, 3.5, 11, 0.6, "Questions?", 24, WHITE)
    ln = s.shapes.add_connector(1, I(0.7), I(4.5), I(12.6), I(4.5))
    ln.line.color.rgb, ln.line.width = BORDER, Pt(1)
    text(s, 0.7, 4.75, 12, 0.4, "github.com/tanvisheth1234-wq/miniproject   ·   branch develop_5", 15, CYAN, font="Consolas")
    text(s, 0.7, 5.35, 12, 0.4, "Miti Shah  ·  Twissha Shah  ·  Tanvi Sheth        Guide: Prof. Anuj Tawari", 14, GREY)

    assert len(prs.slides) == TOTAL, f"expected {TOTAL} slides, built {len(prs.slides)}"
    prs.save(str(OUT))
    print("done:", OUT)


if __name__ == "__main__":
    build()
