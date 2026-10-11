"""Generates the corrected SRS PDF for EcoMesh. Run once, standalone."""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    ListFlowable, ListItem, PageBreak, NextPageTemplate, FrameBreak,
    KeepTogether, HRFlowable
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.platypus.flowables import Flowable
from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.pdfgen import canvas as canvas_mod

OUT = "SRS_EcoMesh_Group20.pdf"

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", fontSize=16, leading=20, spaceBefore=18, spaceAfter=10,
                           textColor=colors.HexColor("#1a4a7a"), fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="H2", fontSize=13, leading=17, spaceBefore=14, spaceAfter=8,
                           textColor=colors.HexColor("#1a5a8a"), fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="H3", fontSize=11, leading=14, spaceBefore=10, spaceAfter=6,
                           fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="Body", fontSize=10, leading=14, spaceAfter=8, alignment=TA_JUSTIFY,
                           fontName="Helvetica"))
styles.add(ParagraphStyle(name="BulletBody", fontSize=10, leading=14, alignment=TA_JUSTIFY,
                           fontName="Helvetica"))
styles.add(ParagraphStyle(name="ReqID", fontSize=10, leading=14, spaceAfter=4,
                           fontName="Helvetica"))
styles.add(ParagraphStyle(name="TitlePage", fontSize=24, leading=30, alignment=TA_CENTER,
                           fontName="Helvetica-Bold", textColor=colors.HexColor("#1a4a7a")))
styles.add(ParagraphStyle(name="SubtitlePage", fontSize=13, leading=18, alignment=TA_CENTER,
                           fontName="Helvetica"))
styles.add(ParagraphStyle(name="NoteBody", fontSize=9.5, leading=13, spaceAfter=8, alignment=TA_JUSTIFY,
                           fontName="Helvetica-Oblique", textColor=colors.HexColor("#555555")))
styles.add(ParagraphStyle(name="FooterHead", fontSize=8, fontName="Helvetica-Oblique",
                           textColor=colors.HexColor("#555555")))
styles.add(ParagraphStyle(name="TOCHead", fontSize=18, leading=22, spaceAfter=14,
                           fontName="Helvetica-Bold", textColor=colors.HexColor("#1a4a7a")))

TOC_LEVEL_STYLES = [
    ParagraphStyle(name="TOC1", fontSize=11, leading=16, fontName="Helvetica-Bold",
                    leftIndent=0, firstLineIndent=0),
    ParagraphStyle(name="TOC2", fontSize=10, leading=14, fontName="Helvetica",
                    leftIndent=16, firstLineIndent=0),
]


def bullets(items, style="BulletBody"):
    return ListFlowable(
        [ListItem(Paragraph(t, styles[style]), leftIndent=14) for t in items],
        bulletType="bullet", start="•", leftIndent=16, spaceBefore=2, spaceAfter=8,
    )


def req(id_, text):
    return Paragraph(f"<b>{id_}:</b> {text}", styles["ReqID"])


def draw_footer(canvas, doc):
    page_num = canvas.getPageNumber()
    if page_num <= 1:  # skip the title page
        return
    canvas.saveState()
    canvas.setFont("Helvetica-Oblique", 8)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(0.9 * inch, 0.55 * inch, "Software Requirements Specification for EcoMesh")
    canvas.drawRightString(letter[0] - 0.9 * inch, 0.55 * inch, f"Page {page_num - 1}")
    canvas.setStrokeColor(colors.HexColor("#cccccc"))
    canvas.line(0.9 * inch, 0.72 * inch, letter[0] - 0.9 * inch, 0.72 * inch)
    canvas.restoreState()


class SRSDoc(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph):
            style_name = flowable.style.name
            text = flowable.getPlainText()
            if style_name == "H1" and not text.startswith("Revision") and not text.startswith("Table of"):
                self.notify('TOCEntry', (0, text, self.page))
                self.canv.bookmarkPage(text)
                self.canv.addOutlineEntry(text, text, level=0)
            elif style_name == "H2":
                self.notify('TOCEntry', (1, text, self.page))
                self.canv.bookmarkPage(text)
                self.canv.addOutlineEntry(text, text, level=1)


def fit_drawing(d, max_width):
    """Scale a Drawing down (never up) so it fits within max_width -- otherwise
    a Drawing wider than the page's content area is silently clipped, not
    shrunk, by platypus."""
    if d.width > max_width:
        scale = max_width / d.width
        d.width *= scale
        d.height *= scale
        d.scale(scale, scale)
    return d


def make_context_diagram():
    d = Drawing(460, 300)

    def box(x, y, w, h, title, lines, fill="#eaf2fb"):
        d.add(Rect(x, y, w, h, fillColor=colors.HexColor(fill), strokeColor=colors.HexColor("#2a5a8a")))
        d.add(String(x + w / 2, y + h - 14, title, textAnchor="middle", fontSize=8.5, fontName="Helvetica-Bold"))
        for i, ln in enumerate(lines):
            d.add(String(x + w / 2, y + h - 26 - i * 10, ln, textAnchor="middle", fontSize=7))

    def arrow(x1, y1, x2, y2, label="", dx=0, dy=0):
        d.add(Line(x1, y1, x2, y2, strokeColor=colors.HexColor("#444444")))
        if label:
            d.add(String((x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy, label, fontSize=6.5,
                          textAnchor="middle", fillColor=colors.HexColor("#333333")))

    box(150, 250, 160, 50, "End User", ["Send / SOS / view peers", "view delivery / relay"])
    box(150, 110, 160, 60, "EcoMesh Node", ["Discovery, routing,", "reliability, security,", "storage, interface"], "#dbeafd")
    box(10, 110, 120, 50, "Neighbouring Nodes", ["Beacons, link-state,", "relay, ACKs"])
    box(330, 110, 120, 50, "Gateway Node", ["Advertise role,", "forward outbound"])
    box(10, 10, 150, 50, "Rescue Coordinator", ["Topology, SOS queue,", "hop paths, log"])
    box(300, 10, 150, 50, "Institution Admin", ["Node IDs, roles,", "gateway designation"])

    arrow(230, 250, 230, 170, "message / SOS", 40, 0)
    arrow(130, 135, 150, 135, "packets in/out", 0, 8)
    arrow(310, 135, 330, 135, "outbound / advertise", -10, 8)
    arrow(150, 100, 85, 60, "SOS queue, topology", -45, 10)
    arrow(310, 100, 375, 60, "node config", 35, 10)
    return d


def make_activity_diagram():
    W, H = 620, 460
    d = Drawing(W, H)

    RED = colors.HexColor("#a83232")
    GREEN = colors.HexColor("#2a8a3a")
    BLUE = colors.HexColor("#2a5a8a")
    DARK = colors.HexColor("#333333")

    box_x, box_w, box_h = 140, 280, 34
    center_x = box_x + box_w / 2

    def main_box(y, text, fill="#eaf2fb", stroke=BLUE, x=box_x, w=box_w):
        d.add(Rect(x, y, w, box_h, fillColor=colors.HexColor(fill), strokeColor=stroke))
        d.add(String(x + w / 2, y + box_h / 2 - 3, text, textAnchor="middle", fontSize=8.5))

    def side_box(x, y, w, h, lines, fill, stroke):
        d.add(Rect(x, y, w, h, fillColor=colors.HexColor(fill), strokeColor=stroke))
        n = len(lines)
        top = y + h / 2 + (n - 1) * 5.5
        for i, ln in enumerate(lines):
            d.add(String(x + w / 2, top - i * 11, ln, textAnchor="middle", fontSize=7.5))

    def vline(x, y1, y2, color=DARK):
        d.add(Line(x, y1, x, y2, strokeColor=color))

    def hline(x1, x2, y, color=DARK):
        d.add(Line(x1, y, x2, y, strokeColor=color))

    def label(x, y, text, color=DARK, size=7.5):
        d.add(String(x, y, text, fontSize=size, fillColor=color, fontName="Helvetica-Bold"))

    # --- start terminal ---
    d.add(Rect(center_x - 5, H - 20, 10, 10, fillColor=colors.black, strokeColor=colors.black))
    vline(center_x, H - 20, H - 30)

    rows = [
        (H - 60, "Receive packet from transport layer"),
        (H - 110, "Parse and validate 52-byte header"),
        (H - 160, "Header valid?"),
        (H - 210, "Message ID already seen?"),
        (H - 260, "Hop allowance remaining?"),
        (H - 310, "Addressed to this node?"),
    ]
    for y, text in rows:
        main_box(y, text)

    # spine connecting consecutive rows (top of lower box to bottom of upper box)
    for (y1, _), (y2, _) in zip(rows, rows[1:]):
        vline(center_x, y1, y2 + box_h)

    y_start, y_header, y_msgid, y_hop, y_addr = (rows[0][0], rows[2][0], rows[3][0], rows[4][0], rows[5][0])

    # --- discard branch (left side) ---
    discard_x, discard_w, discard_h = 10, 110, 44
    discard_y = y_msgid - 5  # vertically centred on the middle branch row
    discard_cy = discard_y + discard_h / 2
    side_box(discard_x, discard_y, discard_w, discard_h, ["Discard packet", "and log reason"],
              "#fdeaea", RED)
    d.add(String(discard_x + discard_w / 2, discard_y - 12, "Packet discarded", textAnchor="middle",
                  fontSize=7, fontName="Helvetica-Oblique"))

    bus_x = discard_x + discard_w + 20  # shared vertical bus between the three branch stubs
    branch_rows = [(y_header, "No"), (y_msgid, "Yes"), (y_hop, "No")]
    stub_ys = [y + box_h / 2 for y, _ in branch_rows]
    vline(bus_x, min(stub_ys), max(stub_ys), RED)
    hline(bus_x, discard_x + discard_w, discard_cy, RED)
    for (y, txt), sy in zip(branch_rows, stub_ys):
        hline(bus_x, box_x, sy, RED)
        label(bus_x - 18, sy + 3, txt, RED)

    # --- deliver branch (right side, off "Addressed to this node?") ---
    deliver_x, deliver_w, deliver_h = box_x + box_w + 40, 130, 44
    deliver_y = y_addr - 5
    deliver_cy = deliver_y + deliver_h / 2
    side_box(deliver_x, deliver_y, deliver_w, deliver_h, ["Verify signature, decrypt,", "deliver to user"],
              "#eafbea", GREEN)
    d.add(String(deliver_x + deliver_w / 2, deliver_y - 12, "Message delivered", textAnchor="middle",
                  fontSize=7, fontName="Helvetica-Oblique"))
    addr_cy = y_addr + box_h / 2
    hline(box_x + box_w, deliver_x, addr_cy, GREEN)
    label(box_x + box_w + 14, addr_cy + 5, "Yes", GREEN)
    label(center_x + 8, y_addr - 14, "No", RED)

    # --- forward path continues below "Addressed to this node?" ---
    y_decrement = y_addr - 60
    y_enqueue = y_decrement - 50
    main_box(y_decrement, "Decrement hop allowance, append path")
    main_box(y_enqueue, "Enqueue by priority and forward")
    vline(center_x, y_addr, y_decrement + box_h)
    vline(center_x, y_decrement, y_enqueue + box_h)

    # --- end terminal ---
    d.add(Rect(center_x - 5, y_enqueue - 22, 10, 10, fillColor=colors.black, strokeColor=colors.black))
    vline(center_x, y_enqueue, y_enqueue - 12)

    return d


def build():
    doc = SRSDoc(OUT, pagesize=letter,
                 leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                 topMargin=0.9 * inch, bottomMargin=0.9 * inch)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="normal")
    doc.addPageTemplates([PageTemplate(id="main", frames=frame, onPage=draw_footer)])

    story = []

    # --- Title page ---------------------------------------------------------
    story.append(Spacer(1, 1.5 * inch))
    story.append(Paragraph("Software Requirements Specification", styles["TitlePage"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("for", styles["SubtitlePage"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("EcoMesh", ParagraphStyle(
        name="ProjectName", fontSize=30, leading=36, alignment=TA_CENTER,
        fontName="Helvetica-Bold", textColor=colors.HexColor("#1a4a7a"))))
    story.append(Spacer(1, 6))
    story.append(Paragraph("Distributed Peer-to-Peer Disaster Relief Communication Mesh",
                            styles["SubtitlePage"]))
    story.append(Spacer(1, 40))
    story.append(Paragraph("Prepared by", ParagraphStyle(name="p1", fontSize=11, alignment=TA_CENTER,
                                                           fontName="Helvetica-Bold")))
    story.append(Spacer(1, 10))
    author_table = Table([
        ["Miti Shah", "2024300230", "miti.shah24@spit.ac.in"],
        ["Twissha Shah", "2024300231", "twissha.shah24@spit.ac.in"],
        ["Tanvi Sheth", "2024300239", "tanvi.sheth24@spit.ac.in"],
    ], colWidths=[1.6 * inch, 1.4 * inch, 2.6 * inch])
    author_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(author_table)
    story.append(Spacer(1, 40))
    meta_table = Table([
        ["Instructor:", "Prof. Anuj Tawari"],
        ["Course:", "Mini Project I"],
        ["Date:", "23-09-26"],
    ], colWidths=[1.3 * inch, 2.3 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(meta_table)
    story.append(PageBreak())

    # --- Table of Contents ---------------------------------------------------
    story.append(Paragraph("Table of Contents", styles["TOCHead"]))
    toc = TableOfContents()
    toc.levelStyles = TOC_LEVEL_STYLES
    story.append(toc)
    story.append(PageBreak())

    story.append(Paragraph("Revision History", styles["H1"]))
    rev_table = Table([
        ["Name", "Date", "Reason For Changes", "Version"],
        ["Group 20", "23-09-26", "Initial release of the SRS document", "1.0"],
        ["Group 20", "25-09-26",
         "Clarified X25519 as a planned (not current) interface; aligned priority-level\n"
         "naming with the wire protocol; added an implementation-status note for\n"
         "signing/public-key distribution", "1.1"],
        ["Group 20", "11-10-26",
         "Updated the SEC-1..SEC-6 implementation-status note: Ed25519 signing and\n"
         "public-key distribution via discovery beacons are now implemented and wired\n"
         "end to end, not just AES-256-GCM encryption", "1.2"],
    ], colWidths=[1.1 * inch, 0.9 * inch, 3.3 * inch, 0.7 * inch])
    rev_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4a7a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(rev_table)
    story.append(PageBreak())

    # --- 1. Introduction ------------------------------------------------------
    story.append(Paragraph("1 Introduction", styles["H1"]))
    story.append(Paragraph(
        "The <b>Distributed Peer-to-Peer Disaster Relief Communication Mesh (EcoMesh)</b> is a decentralised "
        "communication platform designed to keep people connected when cellular towers, internet links and "
        "centralised messaging services have failed. Every participating device runs an identical program "
        "that acts at the same time as a communication endpoint and as a forwarding router, so that a message "
        "travels hop by hop across neighbouring devices until it reaches its destination, a gateway node "
        "holding residual external connectivity, or a rescue node. The system additionally provides emergency "
        "message prioritisation, adaptive routing, reliable delivery, payload encryption and a monitoring "
        "dashboard for rescue coordinators.", styles["Body"]))

    story.append(Paragraph("1.1 Purpose", styles["H2"]))
    story.append(Paragraph(
        "The Distributed Peer-to-Peer Disaster Relief Communication Mesh (EcoMesh) Version 1.0 is designed to "
        "assist individuals affected by a disaster in sending distress and status messages without internet "
        "access or any central server, relaying other users' messages transparently through their own devices, "
        "having emergency messages delivered ahead of routine traffic, and having undelivered messages retained "
        "and forwarded opportunistically when a route later becomes available.", styles["Body"]))
    story.append(Paragraph(
        "The system also provides rescue coordinators with the ability to view the live mesh topology, receive "
        "a prioritised queue of outstanding distress messages, inspect delivery paths, and monitor node "
        "availability across the affected area. Institution administrators are provided with the ability to "
        "pre-deploy the software, assign node identifiers and designate gateway nodes.", styles["Body"]))
    story.append(Paragraph(
        "This document serves as a reference for stakeholders, developers, testers, project guides and "
        "evaluators involved in the development and assessment of the Disaster Relief Communication Mesh. It "
        "establishes a common understanding of the system requirements and serves as the foundation for system "
        "design, implementation, testing, evaluation and future extension.", styles["Body"]))

    story.append(Paragraph("1.2 Document Conventions", styles["H2"]))
    story.append(Paragraph(
        "This Software Requirements Specification follows the <b>IEEE 830</b> standard for documenting "
        "software requirements. The document uses clear, consistent and unambiguous language to describe the "
        "functional and non-functional requirements of the system. Section headings are numbered "
        "hierarchically, and all requirements are written in a structured format with unique identifiers to "
        "ensure readability, traceability and ease of implementation. The term <i>node</i> refers to any "
        "device running the EcoMesh program.", styles["Body"]))

    story.append(Paragraph("1.3 Intended Audience and Reading Suggestions", styles["H2"]))
    story.append(Paragraph("This document is intended for the following stakeholders:", styles["Body"]))
    story.append(bullets([
        "<b>Developers</b>, who will implement the protocol, routing, reliability and interface modules "
        "according to the specified requirements.",
        "<b>Testers</b>, who will verify and validate that the system satisfies all functional and "
        "non-functional requirements under both normal and degraded network conditions.",
        "<b>Project Guides and Evaluators</b>, who will use the document to assess the scope, design rigour "
        "and completeness of the system.",
        "<b>System Administrators</b>, who will pre-deploy, configure and maintain the software on "
        "organisational devices.",
        "<b>Stakeholders and Clients</b>, including disaster response agencies, who will review the "
        "requirements to ensure the system meets operational objectives.",
    ]))
    story.append(Paragraph(
        "Readers are encouraged to begin with the Introduction and Overall Description sections to understand "
        "the system, followed by the Functional and Non-Functional Requirements for detailed specifications.",
        styles["Body"]))

    story.append(Paragraph("1.4 Product Scope", styles["H2"]))
    story.append(Paragraph(
        "The Distributed Peer-to-Peer Disaster Relief Communication Mesh (EcoMesh) is designed to provide a "
        "decentralised platform for automatic discovery of nearby devices, multi-hop message forwarding using "
        "a custom binary protocol, adaptive route selection based on measured link quality rather than hop "
        "count alone, priority handling for emergency traffic, reliable delivery through acknowledgements and "
        "retransmission, delay-tolerant retention of undeliverable messages, encryption of message payloads so "
        "that relaying devices cannot read them, persistent logging of all message activity, and a monitoring "
        "dashboard for rescue coordinators.", styles["Body"]))
    story.append(Paragraph(
        "The primary objective of the system is to preserve communication capability during infrastructure "
        "failure, to allow the residual connectivity of a single device to be shared across an entire group of "
        "users, and to reduce the time required for rescue teams to locate and reach affected individuals.",
        styles["Body"]))
    story.append(Paragraph(
        "In the current version the mesh operates over local area network sockets, which stand in for "
        "Bluetooth Low Energy or Wi-Fi Direct radio links. Each node's visible neighbour set is restricted in "
        "configuration to emulate limited radio range. Discovery, routing, reliability and encryption are "
        "transport-agnostic, so replacing the socket transport with a radio transport does not alter any layer "
        "above it.", styles["Body"]))

    story.append(Paragraph("1.5 References", styles["H2"]))
    story.append(bullets([
        "IEEE Recommended Practice for Software Requirements Specifications (IEEE Std 830).",
        "C. Perkins, E. Belding-Royer and S. Das, “Ad hoc On-Demand Distance Vector (AODV) Routing,” "
        "RFC 3561, IETF, 2003.",
        "T. Clausen and P. Jacquet, “Optimized Link State Routing Protocol (OLSR),” RFC 3626, IETF, 2003.",
        "S. Burleigh, K. Fall and E. Birrane, “Bundle Protocol Version 7,” RFC 9171, IETF, 2022.",
        "D. S. J. De Couto, D. Aguayo, J. Bicket and R. Morris, “A High-Throughput Path Metric for Multi-Hop "
        "Wireless Routing,” ACM MobiCom, 2003.",
        "M. R. Albrecht, J. Blasco, R. B. Jensen and L. Mareková, “Mesh Messaging in Large-Scale Protests: "
        "Breaking Bridgefy,” CT-RSA 2021.",
        "Z. Liu, O. Chabra, J. Lynch, A. Martin, C. Li and H. Balakrishnan, “Scalable Routing in a City-Scale "
        "Wi-Fi Network for Disaster Recovery,” NINeS 2026.",
        "Project Master Reference Document, <i>Distributed Peer-to-Peer Disaster Relief Communication Mesh</i>, "
        "Group 20, Department of Computer Engineering, SPIT.",
    ]))

    # --- 2. Overall Description -------------------------------------------------
    story.append(Paragraph("2 Overall Description", styles["H1"]))
    story.append(Paragraph("2.1 Product Perspective", styles["H2"]))
    story.append(Paragraph(
        "The <b>Distributed Peer-to-Peer Disaster Relief Communication Mesh (EcoMesh)</b> is a self-contained, "
        "decentralised communication system developed to replace the conventional client-server messaging "
        "model in environments where communication infrastructure has failed. It replaces the conventional "
        "approach of routing every message through a remote server by allowing devices to exchange messages "
        "directly and to forward messages on behalf of one another.", styles["Body"]))
    story.append(Paragraph(
        "Existing messaging applications require every message to reach a remote server or cellular tower. A "
        "functioning local network with a severed external uplink is therefore sufficient to render all of "
        "them unusable, even between devices that remain fully reachable to each other. EcoMesh removes this "
        "dependency entirely: there is no server and no privileged node, and each node maintains its own "
        "neighbour table, routing graph, message queue and local database.", styles["Body"]))
    story.append(Paragraph(
        "The system connects end users, relaying users, gateway nodes holding residual external connectivity, "
        "rescue coordinators and institution administrators within a single self-organising network, enabling "
        "efficient communication during infrastructure failure.", styles["Body"]))

    story.append(Paragraph("2.2 Product Functions", styles["H2"]))
    story.append(Paragraph("The Disaster Relief Communication Mesh provides the following major functions:",
                            styles["Body"]))
    story.append(Paragraph("<b>End User Functions</b>", styles["H3"]))
    story.append(bullets([
        "Automatic discovery of nearby nodes without manual configuration.",
        "Composition and transmission of text messages to a named node.",
        "Raising a high-priority SOS message through a dedicated control.",
        "Viewing the list of currently reachable nodes and their hop distance.",
        "Viewing live delivery status and the hop path taken by each message.",
        "Transparent relaying of other users' messages through the device.",
        "Viewing the local history of sent, received and forwarded messages.",
    ]))
    story.append(Paragraph("<b>Node (System) Functions</b>", styles["H3"]))
    story.append(bullets([
        "Maintenance of a live neighbour table with node failure detection.",
        "Construction of a network graph through link-state exchange.",
        "Computation of least-cost routes using a link-quality-weighted metric.",
        "Priority-based scheduling of outgoing messages at every hop.",
        "Loop prevention, duplicate suppression, acknowledgement and retransmission.",
        "Retention and later forwarding of messages with no available route.",
        "Encryption, signing and verification of message traffic.",
        "Persistent logging of every message and network event.",
    ]))
    story.append(Paragraph("<b>Rescue Coordinator Functions</b>", styles["H3"]))
    story.append(bullets([
        "Viewing the live mesh topology and node availability.",
        "Receiving the prioritised queue of outstanding SOS messages.",
        "Inspecting delivery paths, hop counts and delivery outcomes.",
        "Viewing aggregate delivery statistics for the operating area.",
    ]))
    story.append(Paragraph("<b>Administrator Functions</b>", styles["H3"]))
    story.append(bullets([
        "Pre-deployment and configuration of the software on organisational devices.",
        "Assignment of unique node identifiers and node roles.",
        "Designation of gateway nodes where an external link is expected to survive.",
        "Verification of node configuration before deployment.",
    ]))
    story.append(Spacer(1, 8))
    story.append(fit_drawing(make_context_diagram(), doc.width))
    story.append(Paragraph("Figure 1: Context Diagram", ParagraphStyle(
        name="caption", fontSize=9, alignment=TA_CENTER, fontName="Helvetica-Oblique", spaceBefore=4)))

    story.append(Paragraph("2.3 Users and Characteristics", styles["H2"]))
    story.append(Paragraph("<b>End User</b>", styles["H3"]))
    story.append(bullets([
        "An individual carrying a device on which the EcoMesh software has been pre-installed.",
        "Should possess basic knowledge of using a messaging application; the emergency action is a single "
        "long-press control.",
        "Can send and receive messages, raise an SOS, view reachable peers, and view the delivery status and "
        "hop path of each message.",
    ]))
    story.append(Paragraph("<b>Relay User</b>", styles["H3"]))
    story.append(bullets([
        "Any end user whose device forwards traffic on behalf of other users.",
        "Participates passively and requires no action, configuration or awareness; relaying is fully "
        "automatic.",
        "Cannot read the contents of messages that transit the device.",
    ]))
    story.append(Paragraph("<b>Rescue Coordinator</b>", styles["H3"]))
    story.append(bullets([
        "Authorised rescue personnel operating a node configured with the RESCUE role.",
        "Can view the mesh topology, the SOS queue ordered by urgency and age, delivery paths, and aggregate "
        "delivery statistics.",
        "Requires no configuration to join an existing mesh; the node is discovered automatically on arrival "
        "in the affected area.",
    ]))
    story.append(Paragraph("<b>Administrator</b>", styles["H3"]))
    story.append(bullets([
        "Personnel at a hospital, campus, hostel or similar institution responsible for pre-installing the "
        "software on organisational devices.",
        "Assigns unique node identifiers and roles, and designates gateway nodes.",
        "Requires appropriate access to organisational devices and deployment privileges.",
    ]))

    story.append(Paragraph("2.4 Operating Environment", styles["H2"]))
    story.append(Paragraph(
        "The Disaster Relief Communication Mesh (EcoMesh) is a cross-platform application compatible with "
        "deployment on Linux (Ubuntu 22.04 LTS or higher), Windows 10 or higher, and macOS 12 or higher. Each "
        "node requires Python 3.11 or higher, a minimum of 2 GB RAM, 500 MB of storage for the runtime and "
        "message database, and a network interface capable of UDP multicast and TCP communication on a local "
        "network segment.", styles["Body"]))
    story.append(Paragraph(
        "The system does not require internet connectivity, a cellular connection, a domain name service, or "
        "any server infrastructure. The user interface is served by each node itself and is accessed through "
        "modern web browsers such as Google Chrome, Mozilla Firefox, Microsoft Edge and Safari, either on the "
        "node device or on another device connected to the same local network.", styles["Body"]))

    story.append(Paragraph("2.5 Design and Implementation Constraints", styles["H2"]))
    story.append(Paragraph("<b>Technology Constraints</b>", styles["H3"]))
    story.append(bullets([
        "The system shall be implemented using asynchronous single-threaded concurrency; shared mutable state "
        "shall not be accessed from multiple threads.",
        "All inter-node communication shall use a custom binary packet format with a fixed 52-byte header "
        "transmitted in network byte order.",
        "The mesh engine shall not depend on any specific transport; all transport access shall occur through "
        "a defined transport interface.",
        "Persistent storage shall use an embedded, file-based database requiring no separate server process.",
    ]))
    story.append(Paragraph("<b>Security Constraints</b>", styles["H3"]))
    story.append(bullets([
        "Message payloads shall be encrypted such that intermediate forwarding nodes cannot read them.",
        "Packet headers shall be cryptographically signed to prevent forgery of emergency messages.",
        "Only established cryptographic libraries shall be used; cryptographic primitives shall not be "
        "implemented from first principles.",
        "Packet structure shall be validated before any forwarding decision is taken.",
    ]))
    story.append(Paragraph("<b>Performance Constraints</b>", styles["H3"]))
    story.append(bullets([
        "The system is specified for deployments of up to approximately fifty concurrent nodes.",
        "Topology convergence following a network change shall complete within a bounded interval.",
        "The system shall continue to operate under packet loss without unbounded retransmission.",
    ]))

    story.append(Paragraph("2.6 User Documentation", styles["H2"]))
    story.append(Paragraph("The system will provide:", styles["Body"]))
    story.append(bullets([
        "User Manual containing step-by-step instructions for sending messages and raising an SOS.",
        "Deployment Guide for institutions, covering node configuration, identifier assignment and gateway "
        "designation.",
        "Rescue Coordinator Guide for interpreting the topology view and the SOS queue.",
        "Developer Reference documenting the wire protocol, module structure and transport interface.",
        "Online Help and FAQs for common issues and troubleshooting.",
    ]))

    story.append(Paragraph("2.7 Assumptions and Dependencies", styles["H2"]))
    story.append(bullets([
        "The software is pre-installed on participating devices before a disaster occurs; installation during "
        "an incident is assumed to be impossible.",
        "Participating devices are within communication range of at least one other participating device, "
        "either directly or through intermediate devices.",
        "Devices have sufficient battery capacity to operate for the duration of the incident.",
        "At least one node with residual external connectivity, or a rescue node entering the area, is "
        "required for messages to leave the mesh.",
        "The local network segment permits UDP multicast; where it does not, a configured seed list of peer "
        "addresses is used instead.",
        "Node identifiers are unique within a deployment and are assigned in advance.",
        "The system depends on the Python runtime and an established cryptography library being present on "
        "each device.",
    ]))

    # --- 3. External Interface Requirements --------------------------------------
    story.append(Paragraph("3 External Interface Requirements", styles["H1"]))
    story.append(Paragraph("3.1 User Interfaces", styles["H2"]))

    story.append(Paragraph("<b>i) Node View</b>", styles["H3"]))
    story.append(Paragraph("<b>User:</b> End Users and Relay Users", styles["Body"]))
    story.append(Paragraph("<b>Properties:</b>", styles["Body"]))
    story.append(bullets([
        "Displays a prominent SOS control requiring a sustained long press, preventing accidental activation.",
        "Displays the list of currently reachable nodes together with hop distance.",
        "Provides a message composition field and a destination selector.",
        "Displays each message with a live delivery state of sending, relayed via n nodes, delivered, queued "
        "or failed.",
        "Displays a count of nearby nodes so the user can confirm participation in the mesh.",
    ]))

    story.append(Paragraph("<b>ii) Message History View</b>", styles["H3"]))
    story.append(Paragraph("<b>User:</b> End Users", styles["Body"]))
    story.append(Paragraph("<b>Properties:</b>", styles["Body"]))
    story.append(bullets([
        "Displays previously sent, received and forwarded messages with timestamps.",
        "Displays the final delivery outcome and hop count of each message.",
        "Allows the user to filter records by status and by time.",
    ]))

    story.append(Paragraph("<b>iii) Rescue Dashboard</b>", styles["H3"]))
    story.append(Paragraph("<b>User:</b> Rescue Coordinators", styles["Body"]))
    story.append(Paragraph("<b>Properties:</b>", styles["Body"]))
    story.append(bullets([
        "Renders the live mesh graph, with nodes appearing on join and dimming on failure.",
        "Displays the outstanding SOS queue sorted by priority and then by age.",
        "Displays the delivery log with source, destination, hop path and outcome.",
        "Displays aggregate statistics including delivery ratio, mean hop count and number of nodes online.",
    ]))

    story.append(Paragraph("<b>iv) Node Configuration Interface</b>", styles["H3"]))
    story.append(Paragraph("<b>User:</b> Administrators", styles["Body"]))
    story.append(Paragraph("<b>Properties:</b>", styles["Body"]))
    story.append(bullets([
        "Accepts a configuration file specifying node identifier, role, listening ports and multicast group.",
        "Accepts an optional visible-neighbour list used to constrain connectivity during testing and "
        "demonstration.",
        "Validates the configuration at start-up and reports errors before the node joins the mesh.",
    ]))

    story.append(Paragraph("3.2 Hardware Interfaces", styles["H2"]))
    story.append(Paragraph("The Disaster Relief Communication Mesh interacts with the following hardware "
                            "components:", styles["Body"]))
    story.append(bullets([
        "End-user devices such as laptops, desktops and tablets on which the node program executes.",
        "Network interface hardware supporting UDP multicast and TCP on a local segment.",
        "Devices belonging to rescue personnel, operating as rescue nodes.",
        "Devices holding residual external connectivity, operating as gateway nodes.",
        "Bluetooth Low Energy and Wi-Fi Direct radio interfaces in future versions of the system.",
    ]))

    story.append(Paragraph("3.3 Software Interfaces", styles["H2"]))
    story.append(Paragraph("The system interfaces with:", styles["Body"]))
    story.append(bullets([
        "Embedded Database Management System (SQLite in write-ahead logging mode) for storing message, event "
        "and peer records, with one database file per node.",
        "Operating system socket interface for UDP multicast and TCP stream communication.",
        "Cryptographic library providing AES-256-GCM authenticated encryption and Ed25519 digital "
        "signatures, both implemented and wired into the live send/receive path. X25519 key agreement is a "
        "<b>planned</b> interface for a future key-establishment upgrade and is not yet in use — see TBD-2; "
        "the current release uses a pre-shared symmetric session key for encryption and HELLO-distributed "
        "public keys for signing.",
        "Embedded web server exposing a REST and WebSocket interface on the loopback or local network address "
        "for the user interface.",
        "Browser-based front end communicating with the node over WebSocket for live updates.",
    ]))

    story.append(Paragraph("3.4 Communications Interfaces", styles["H2"]))
    story.append(bullets([
        "Discovery beacons shall be transmitted over UDP multicast to a configured group address and port at "
        "a fixed interval.",
        "Link-state reports shall be transmitted over UDP to directly reachable neighbours.",
        "Data messages and acknowledgements shall be transmitted over TCP on a per-hop basis, providing "
        "ordered and reliable delivery across each individual link.",
        "All packets shall conform to the defined binary format, beginning with a magic value and protocol "
        "version; non-conforming packets shall be rejected without forwarding.",
        "Message payloads shall be encrypted end to end; only the header fields required for routing remain "
        "readable by intermediate nodes.",
        "Communication between the browser interface and the node shall use HTTP and WebSocket over the local "
        "network only.",
    ]))

    # --- 4. System Features -------------------------------------------------------
    story.append(Paragraph("4 System Features", styles["H1"]))

    def feature_block(num, title, desc, priority, stim_resp, req_list):
        story.append(Paragraph(f"4.{num} {title}", styles["H2"]))
        story.append(Paragraph(f"4.{num}.1 Description and Priority", styles["H3"]))
        story.append(Paragraph(desc, styles["Body"]))
        story.append(Paragraph(f"Priority: {priority}", styles["Body"]))
        story.append(Paragraph(f"4.{num}.2 Stimulus / Response Sequences", styles["H3"]))
        for stim, resp in stim_resp:
            story.append(Paragraph(f"<b>Stimulus:</b> {stim}", styles["Body"]))
            story.append(Paragraph(f"<b>Response:</b> {resp}", styles["Body"]))
        story.append(Paragraph(f"4.{num}.3 Functional Requirements", styles["H3"]))
        for rid, rtext in req_list:
            story.append(req(rid, rtext))

    feature_block(1, "Peer Discovery",
        "The system shall allow nodes to detect other nodes on the same network automatically, without "
        "manual entry of addresses, and shall detect when a previously known node becomes unreachable.",
        "High",
        [
            ("A node starts up.", "The node begins transmitting discovery beacons at a fixed interval and "
             "begins listening for beacons from other nodes."),
            ("A beacon is received from a previously unknown node.", "The system adds the node to the "
             "neighbour table with its address, role, public key and time of observation."),
            ("No beacon is received from a known node for the timeout interval.", "The system marks the node "
             "as unreachable, removes it from the neighbour table and triggers a routing update."),
        ],
        [
            ("DIS-1", "The system shall transmit a discovery beacon at a fixed configurable interval."),
            ("DIS-2", "The system shall maintain a neighbour table containing node identifier, address, role, "
             "public key, last-seen time and measured link quality."),
            ("DIS-3", "The system shall add a previously unknown node to the neighbour table on receipt of a "
             "valid beacon."),
            ("DIS-4", "The system shall declare a neighbour unreachable after a configurable period of "
             "silence."),
            ("DIS-5", "The system shall compute link quality as the proportion of expected beacons actually "
             "received over a sliding window."),
            ("DIS-6", "The system shall operate without any manual configuration of peer addresses."),
            ("DIS-7", "The system shall support an optional configured seed list of peers for networks where "
             "multicast is unavailable."),
        ])

    feature_block(2, "Message Composition and Transmission",
        "The system shall allow a user to compose a text message, select a destination and transmit it into "
        "the mesh, and shall report the progress of that message back to the user.",
        "High",
        [
            ("User composes a message and selects a destination.", "The system encapsulates the message in a "
             "packet, assigns a unique identifier and places it on the outgoing queue."),
            ("User activates the SOS control.", "The system generates a pre-composed distress message at the "
             "highest priority level and transmits it towards the rescue destination."),
            ("No route to the destination currently exists.", "The system retains the message for later "
             "delivery and reports the queued state to the user."),
        ],
        [
            ("MSG-1", "The system shall allow a user to compose and send a text message to a named node."),
            ("MSG-2", "The system shall allow a user to send a message addressed to the rescue service rather "
             "than to a specific node."),
            ("MSG-3", "The system shall provide a distinct control for raising an SOS, requiring a sustained "
             "press to activate."),
            ("MSG-4", "The system shall assign a globally unique identifier to every message it originates."),
            ("MSG-5", "The system shall record the creation time of every message it originates."),
            ("MSG-6", "The system shall display the current delivery state of each originated message."),
            ("MSG-7", "The system shall display the number of intermediate nodes traversed by a delivered "
             "message."),
        ])

    feature_block(3, "Multi-Hop Message Forwarding",
        "The system shall forward messages that are not addressed to it towards their destination, so that "
        "nodes outside direct communication range can be reached.",
        "High",
        [
            ("A packet addressed to another node is received.", "The system validates the packet, decrements "
             "its remaining hop allowance, records its own identifier in the traversal path and forwards it "
             "towards the next hop."),
            ("A packet addressed to this node is received.", "The system decrypts the payload, verifies its "
             "signature and delivers it to the user interface."),
            ("A packet with an exhausted hop allowance is received.", "The system discards the packet and "
             "records the reason in the event log."),
        ],
        [
            ("FWD-1", "The system shall forward packets not addressed to it towards the destination."),
            ("FWD-2", "The system shall decrement the remaining hop allowance of every packet it forwards."),
            ("FWD-3", "The system shall discard any packet whose hop allowance has reached zero."),
            ("FWD-4", "The system shall append its own identifier to the traversal path of every forwarded "
             "packet."),
            ("FWD-5", "The system shall discard any packet whose traversal path already contains its own "
             "identifier."),
            ("FWD-6", "The system shall validate the structure of a packet before taking any forwarding "
             "decision."),
            ("FWD-7", "The system shall not be able to read the payload of a packet it merely forwards."),
        ])

    story.append(Spacer(1, 8))
    story.append(fit_drawing(make_activity_diagram(), doc.width))
    story.append(Paragraph("Figure 2: Packet Forwarding Activity Diagram", ParagraphStyle(
        name="caption2", fontSize=9, alignment=TA_CENTER, fontName="Helvetica-Oblique", spaceBefore=4)))

    feature_block(4, "Adaptive Routing",
        "The system shall maintain a model of the network and select routes according to measured link "
        "reliability rather than hop count alone, updating routes as the network changes.",
        "High",
        [
            ("A link-state report is received from a neighbour.", "The system merges the reported adjacency "
             "into its network graph and recomputes routes if the topology has changed."),
            ("A destination is selected for an outgoing message.", "The system computes the least-cost path "
             "to that destination over the weighted graph and resolves the next hop."),
            ("A node on the current path fails.", "The system removes the corresponding edges, recomputes "
             "routes and forwards subsequent messages along an alternative path."),
        ],
        [
            ("RTE-1", "The system shall periodically transmit its own neighbour list to adjacent nodes."),
            ("RTE-2", "The system shall construct a graph of the network from received link-state reports."),
            ("RTE-3", "The system shall compute least-cost paths using Dijkstra's algorithm over the weighted "
             "graph."),
            ("RTE-4", "The system shall assign each link a cost derived from a base hop penalty, the measured "
             "link quality and the number of recent delivery failures on that link."),
            ("RTE-5", "The system shall recompute routes whenever the topology changes."),
            ("RTE-6", "The system shall treat any node advertising the gateway or rescue role as a valid "
             "terminal for messages addressed to the rescue service."),
            ("RTE-7", "The system shall select the least-cost terminal where more than one gateway or rescue "
             "node is reachable."),
            ("RTE-8", "The system shall converge on a consistent view of the topology within a bounded "
             "interval following a change."),
        ])

    feature_block(5, "Priority-Based Message Handling",
        "The system shall ensure that emergency messages are transmitted ahead of routine traffic, and shall "
        "apply this precedence at every node along the delivery path.",
        "High",
        [
            ("An emergency message and a routine message are queued simultaneously.", "The system transmits "
             "the emergency message first."),
            ("An emergency message arrives at a node with routine traffic already queued.", "The system "
             "places the emergency message ahead of the queued routine traffic."),
            ("Two messages of equal priority are queued.", "The system transmits the older message first."),
        ],
        [
            ("PRI-1", "The system shall support three priority levels, corresponding directly to the priority "
             "field values defined in the wire protocol: <b>SOS</b> (emergency), <b>NORMAL</b> (routine) and "
             "<b>STATUS</b>."),
            ("PRI-2", "The system shall maintain outgoing messages in a priority queue rather than a "
             "first-in-first-out queue."),
            ("PRI-3", "The system shall apply priority ordering at every hop, not only at the originating "
             "node."),
            ("PRI-4", "The system shall order messages of equal priority by creation time, oldest first."),
            ("PRI-5", "The system shall assign SOS (emergency) priority to all messages generated by the SOS "
             "control."),
            ("PRI-6", "The system shall display the priority level of each message in the interface."),
        ])

    feature_block(6, "Reliability Mechanisms",
        "The system shall confirm delivery, prevent indefinite circulation of messages, suppress duplicates "
        "and detect unreachable nodes, so that the network remains stable under packet loss and topology "
        "change.",
        "High",
        [
            ("A message reaches its destination.", "The destination transmits an acknowledgement towards the "
             "originator along the reverse path."),
            ("No acknowledgement is received within the timeout interval.", "The system recomputes the route "
             "and retransmits the message, up to a bounded number of attempts."),
            ("A previously seen message is received again.", "The system discards the duplicate and records "
             "the event."),
        ],
        [
            ("REL-1", "The system shall carry a hop allowance in every packet and shall decrement it at each "
             "hop."),
            ("REL-2", "The system shall maintain a record of recently observed message identifiers for a "
             "configurable retention period."),
            ("REL-3", "The system shall discard any packet whose identifier is already present in that "
             "record."),
            ("REL-4", "The system shall transmit an acknowledgement on successful delivery to the "
             "destination."),
            ("REL-5", "The system shall retransmit an unacknowledged message after a configurable timeout."),
            ("REL-6", "The system shall recompute the route before each retransmission attempt."),
            ("REL-7", "The system shall abandon delivery after a configurable number of failed attempts and "
             "shall mark the message accordingly."),
            ("REL-8", "The system shall detect node failure through absence of discovery beacons and shall "
             "update the routing graph accordingly."),
        ])

    feature_block(7, "Store-and-Forward Delivery",
        "The system shall retain messages for which no route currently exists and shall deliver them when "
        "connectivity subsequently becomes available, rather than discarding them.",
        "High",
        [
            ("A message is submitted and no route to the destination exists.", "The system places the message "
             "in the retention queue and reports the queued state to the user."),
            ("A new node or route becomes available.", "The system re-evaluates the retention queue and "
             "transmits any message that has become deliverable."),
            ("A retained message exceeds its retention period.", "The system discards the message and records "
             "the expiry in the event log."),
        ],
        [
            ("SNF-1", "The system shall retain a message when route computation yields no path."),
            ("SNF-2", "The system shall periodically re-attempt delivery of retained messages."),
            ("SNF-3", "The system shall attempt delivery of retained messages immediately upon detecting a new "
             "neighbour."),
            ("SNF-4", "The system shall bound the retention queue by both message count and retention "
             "period."),
            ("SNF-5", "The system shall discard the lowest-priority retained messages first when the queue "
             "bound is reached."),
            ("SNF-6", "The system shall report the number of retained messages in the interface."),
        ])

    feature_block(8, "Message Security",
        "The system shall protect message contents from intermediate nodes, detect tampering, and prevent "
        "forgery of emergency messages.",
        "High",
        [
            ("A message is transmitted.", "The system encrypts the payload and signs the header before "
             "transmission."),
            ("A message is received at its destination.", "The system verifies the signature, decrypts the "
             "payload and rejects the message if either operation fails."),
            ("A relayed packet has been modified in transit.", "The destination detects the modification and "
             "discards the packet."),
        ],
        [
            ("SEC-1", "The system shall encrypt message payloads using authenticated symmetric encryption."),
            ("SEC-2", "The system shall ensure that intermediate nodes cannot recover the plaintext of "
             "messages they forward."),
            ("SEC-3", "The system shall sign the packet header and traversal path using a digital signature "
             "scheme."),
            ("SEC-4", "The system shall verify the signature of every received packet before delivery."),
            ("SEC-5", "The system shall discard any packet failing signature verification or authentication."),
            ("SEC-6", "The system shall distribute node public keys through discovery beacons."),
            ("SEC-7", "The system shall use established cryptographic libraries and shall not implement "
             "cryptographic primitives directly."),
        ])
    story.append(Paragraph(
        "<b>Implementation status note:</b> as of the current build, all of SEC-1 through SEC-6 are "
        "implemented and wired end to end through the send and receive path. AES-256-GCM payload "
        "encryption (SEC-1, SEC-2) uses a pre-shared session key. Ed25519 header signing and verification "
        "(SEC-3–SEC-5) are opt-in per node and sign the fields that stay constant across every hop rather "
        "than the full mutable header, so a signature survives multi-hop relaying (see the Design of "
        "Algorithms document, Algorithm 9, for why). Node public keys are distributed through discovery "
        "beacons to direct neighbours (DIS-2, SEC-6) and propagate further through link-state gossip, so a "
        "destination several hops from the originator can still verify its signature.", styles["NoteBody"]))

    feature_block(9, "Message Logging and History",
        "The system shall persistently record all message activity and network events on each node, so that "
        "delivery behaviour can be reviewed and analysed after an incident.",
        "High",
        [
            ("A message is sent, received, forwarded, acknowledged or discarded.", "The system writes a "
             "corresponding record to the local database."),
            ("The user opens the message history.", "The system displays previously sent and received "
             "messages with their status and timestamps."),
            ("A node or link changes state.", "The system records the event together with its time of "
             "occurrence."),
        ],
        [
            ("LOG-1", "The system shall maintain a persistent local record of all messages sent, received and "
             "forwarded."),
            ("LOG-2", "The system shall record the status, creation time, resolution time, hop count and "
             "traversal path of each message."),
            ("LOG-3", "The system shall record network events including node arrival, node failure, route "
             "change, duplicate suppression, hop-allowance expiry, retransmission and retention."),
            ("LOG-4", "The system shall store plaintext message content only where the node is the originator "
             "or the destination."),
            ("LOG-5", "The system shall allow the user to view and filter the local message history."),
            ("LOG-6", "The system shall support extraction of delivery statistics from the stored records."),
        ])

    feature_block(10, "Rescue Monitoring Dashboard",
        "The system shall provide rescue coordinators with a live view of the mesh, the outstanding distress "
        "messages and the delivery record for the operating area.",
        "Medium",
        [
            ("A rescue node joins the mesh.", "The system discovers the surrounding nodes and populates the "
             "topology view."),
            ("An emergency message reaches the rescue node.", "The system places it in the distress queue "
             "ordered by priority and age, and alerts the coordinator."),
            ("A node in the mesh fails.", "The system updates the topology view to indicate that the node is "
             "no longer reachable."),
        ],
        [
            ("DSH-1", "The system shall render the current mesh topology as a graph of nodes and active "
             "links."),
            ("DSH-2", "The system shall update the topology view as nodes join and fail."),
            ("DSH-3", "The system shall display outstanding emergency messages ordered by priority and then "
             "by age."),
            ("DSH-4", "The system shall display the originating node identifier and traversal path of each "
             "received message."),
            ("DSH-5", "The system shall display aggregate statistics including delivery ratio, mean hop count "
             "and number of nodes online."),
            ("DSH-6", "The system shall receive updates without requiring the coordinator to refresh the "
             "view."),
        ])

    # --- 5. Other Non-functional Requirements -------------------------------------
    story.append(Paragraph("5 Other Non-functional Requirements", styles["H1"]))
    story.append(Paragraph("5.1 Performance Requirements", styles["H2"]))
    story.append(bullets([
        "The system shall deliver at least 90% of messages in a forty-node network subject to 20% packet "
        "loss.",
        "The system shall converge on a consistent view of the network topology within 15 seconds of a "
        "change.",
        "The system shall resume delivery along an alternative path within 10 seconds of a node failure.",
        "The system shall deliver emergency messages measurably faster than routine messages under equivalent "
        "network load.",
        "The system shall support at least fifty concurrent nodes without degradation beyond the stated "
        "targets.",
        "The user interface shall reflect a change in message or node state within 2 seconds of the "
        "underlying event.",
    ]))

    story.append(Paragraph("5.2 Safety Requirements", styles["H2"]))
    story.append(bullets([
        "The system shall not discard an undeliverable message while retention capacity remains available.",
        "The system shall prevent indefinite circulation of any message through a bounded hop allowance and "
        "traversal-path inspection.",
        "The system shall prevent uncontrolled replication of messages through duplicate suppression.",
        "The system shall require a sustained press to activate the emergency control, preventing accidental "
        "distress signals.",
        "The system shall record every delivery outcome so that failures can be identified after an incident.",
        "The system shall continue to operate on the remaining nodes when any subset of nodes fails.",
    ]))

    story.append(Paragraph("5.3 Security Requirements", styles["H2"]))
    story.append(bullets([
        "The system shall encrypt all message payloads during transmission.",
        "The system shall ensure that a relaying node cannot recover the content of messages it forwards.",
        "The system shall detect and reject packets whose contents have been modified in transit.",
        "The system shall reject emergency messages that fail signature verification.",
        "The system shall validate all packet fields before acting upon them.",
        "The system shall store cryptographic key material only in local node storage and shall not transmit "
        "private keys.",
        "The system shall maintain an auditable local log of message and network events.",
    ]))

    story.append(Paragraph("5.4 Software Quality Attributes", styles["H2"]))
    story.append(Paragraph("<b>Usability</b>", styles["H3"]))
    story.append(bullets(["The system shall present the emergency action as a single prominent control and "
                           "shall require no configuration by the end user."]))
    story.append(Paragraph("<b>Reliability</b>", styles["H3"]))
    story.append(bullets(["The system shall continue to operate correctly in the presence of packet loss, "
                           "node failure and network partition."]))
    story.append(Paragraph("<b>Availability</b>", styles["H3"]))
    story.append(bullets(["The system shall have no single point of failure; the loss of any individual node "
                           "shall not disable the network."]))
    story.append(Paragraph("<b>Maintainability</b>", styles["H3"]))
    story.append(bullets(["The software shall be modular, organised into independent modules for discovery, "
                           "transport, routing, reliability, security, storage and interface."]))
    story.append(Paragraph("<b>Portability</b>", styles["H3"]))
    story.append(bullets(["The mesh engine shall be independent of the underlying transport, so that an "
                           "alternative link technology can be substituted without modifying any other "
                           "module."]))
    story.append(Paragraph("<b>Testability</b>", styles["H3"]))
    story.append(bullets(["The system shall provide a simulated transport allowing deterministic execution of "
                           "multiple nodes within a single process under configurable loss and latency."]))
    story.append(Paragraph("<b>Scalability</b>", styles["H3"]))
    story.append(bullets(["The system shall support the addition of new nodes up to the specified limit "
                           "without configuration changes to existing nodes."]))

    story.append(Paragraph("5.5 Business Rules", styles["H2"]))
    story.append(bullets([
        "Every node must possess a unique identifier within a deployment.",
        "Emergency messages must take precedence over all other traffic at every node.",
        "A node must forward traffic on behalf of other users regardless of user action, and without access "
        "to message contents.",
        "Only nodes configured with the gateway or rescue role may act as exit points for messages addressed "
        "to the rescue service.",
        "A message may be discarded only when its hop allowance is exhausted, it is a duplicate, it fails "
        "validation, or its retention period has expired.",
        "The system must not require or accept a central server in any operating mode.",
    ]))

    # --- 6. Other Requirements -----------------------------------------------------
    story.append(Paragraph("6 Other Requirements", styles["H1"]))
    story.append(Paragraph("6.1 Database Requirements", styles["H2"]))
    story.append(bullets([
        "The system shall maintain a local embedded database on each node for storing message, network event "
        "and peer records; no shared or central database shall be required.",
        "The database shall ensure data consistency, integrity and efficient retrieval of records.",
        "The database shall permit concurrent reading by the user interface while the mesh engine is writing.",
        "The database shall be indexed to permit efficient retrieval of events by time and of messages by "
        "status.",
        "The database shall persist across restarts of the node program.",
        "The database shall support queries producing delivery ratio, hop distribution, latency by priority "
        "and recovery time.",
    ]))
    story.append(Paragraph("6.2 Legal and Regulatory Requirements", styles["H2"]))
    story.append(bullets([
        "The system shall comply with applicable data privacy and cybersecurity regulations concerning the "
        "storage of personal communications.",
        "Message content shall be retained only on the originating and destination nodes.",
        "Deployment within an institution shall be subject to the informed consent of participants.",
        "The system shall comply with applicable regulations governing the use of unlicensed radio spectrum "
        "where a radio transport is subsequently adopted.",
        "The system shall use only software components whose licences permit academic and humanitarian use.",
    ]))

    # --- Appendix A: Glossary -------------------------------------------------------
    story.append(Paragraph("Appendix A – Glossary", styles["H1"]))
    glossary_data = [
        ["Term", "Description"],
        ["ACK", "Acknowledgement — a packet confirming successful message delivery"],
        ["AES-256-GCM", "Authenticated symmetric encryption algorithm used for payloads"],
        ["BLE", "Bluetooth Low Energy"],
        ["DTN", "Delay-Tolerant Networking"],
        ["EcoMesh", "Distributed Peer-to-Peer Disaster Relief Communication Mesh"],
        ["Ed25519", "Digital signature scheme used to sign packet headers"],
        ["Gateway Node", "A node with residual external connectivity, acting as an exit point"],
        ["Hop", "A single transmission between two directly communicating nodes"],
        ["Link Quality", "Proportion of expected beacons received over a sliding window"],
        ["Mesh", "A network in which every device both originates and forwards traffic"],
        ["Node", "Any device running the EcoMesh program"],
        ["Rescue Node", "A node operated by rescue personnel, acting as an SOS destination"],
        ["SOS", "Highest-priority distress message"],
        ["SRS", "Software Requirements Specification"],
        ["Store-and-Forward", "Retention of an undeliverable message for later delivery"],
        ["TCP", "Transmission Control Protocol"],
        ["TTL", "Time To Live — the remaining hop allowance carried in a packet"],
        ["UDP", "User Datagram Protocol"],
    ]
    glossary_rows = [[Paragraph(f"<b>{r[0]}</b>", styles["Body"]) if i == 0 else Paragraph(r[0], styles["Body"]),
                       Paragraph(r[1], styles["Body"])] for i, r in enumerate(glossary_data)]
    glossary_table = Table(glossary_rows, colWidths=[1.4 * inch, 4.9 * inch], repeatRows=1)
    glossary_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4a7a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(glossary_table)

    # --- Appendix B: Analysis Models -------------------------------------------------
    story.append(Paragraph("Appendix B – Analysis Models", styles["H1"]))
    story.append(Paragraph(
        "The analysis models used in the development of the Distributed Peer-to-Peer Disaster Relief "
        "Communication Mesh (EcoMesh) provide a graphical representation of the system boundary and of its "
        "principal control flow. The following models have been included in the relevant sections of this "
        "document:", styles["Body"]))
    story.append(bullets([
        "<b>Context Diagram</b> - Refer to Figure 1 in Section 2.2 Product Functions",
        "<b>Packet Forwarding Activity Diagram</b> - Refer to Figure 2 in Section 4.3 Multi-Hop Message "
        "Forwarding",
    ]))
    story.append(Paragraph(
        "Further models, comprising the use case diagram, class diagram, sequence diagram, state machine "
        "diagram and deployment diagram, are maintained in the accompanying design documentation.",
        styles["Body"]))

    # --- Appendix C: TBD List --------------------------------------------------------
    story.append(Paragraph("Appendix C – To Be Determined List", styles["H1"]))
    tbd_data = [
        ["TBD ID", "Description", "Status"],
        ["TBD-1", "Final radio transport to be adopted (BLE or Wi-Fi Direct)", "Pending"],
        ["TBD-2", "Key establishment scheme for the production release (X25519 per-pair agreement, "
                  "replacing the current pre-shared key)", "Pending"],
        ["TBD-3", "Maximum supported node count beyond the specified fifty", "Pending"],
        ["TBD-4", "Native mobile client platform and implementation language", "Pending"],
        ["TBD-5", "Retention period and queue bound for store-and-forward", "Pending"],
        ["TBD-6", "Institutional node identifier assignment procedure", "Pending"],
    ]
    tbd_rows = [[Paragraph(f"<b>{r[0]}</b>", styles["Body"]) if i == 0 else Paragraph(r[0], styles["Body"]),
                 Paragraph(r[1], styles["Body"]), Paragraph(r[2], styles["Body"])] for i, r in enumerate(tbd_data)]
    tbd_table = Table(tbd_rows, colWidths=[0.8 * inch, 4.6 * inch, 0.9 * inch])
    tbd_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a4a7a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(tbd_table)

    doc.multiBuild(story)


if __name__ == "__main__":
    build()
    print("done")
