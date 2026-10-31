"""Builds the EcoMesh poster (A2 and A3, portrait, one page each) as PDFs.

    python docs/poster/generate_poster.py

Every number comes from the repository (docs/testing/kpis.py -> docs/report/evidence/results,
the last pytest result cached by docs/generate_final_ppt.py, the report PDF page count, and git),
and the pictures are the report's own figures and the device-app screenshots. The look follows
the device app: charcoal header and footer, light body, one blue accent, red only for SOS.
The PDF is printed by headless Chrome (set CHROME if it is not in the default place).
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIG = ROOT / "docs" / "report" / "latex" / "figures"
OUT = HERE / "EcoMesh_Poster.pdf"
OUT_A3 = HERE / "EcoMesh_Poster_A3.pdf"
CHROME = os.environ.get("CHROME", "C:/Program Files/Google/Chrome/Application/chrome.exe")
REPO_URL = "https://github.com/tanvisheth1234-wq/miniproject"

spec = importlib.util.spec_from_file_location("kpis", ROOT / "docs" / "testing" / "kpis.py")
kpis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kpis)


def data_uri(path: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def build_html() -> str:
    import pymupdf
    import qrcode

    rows = {r["id"]: r for r in kpis.evaluate()}
    met, total, not_met = kpis.summary()
    scen = json.loads((ROOT / "docs" / "report" / "evidence" / "results" / "scenarios.json").read_text(encoding="utf-8"))["scenarios"]
    delivery = scen["collapse_40"]["weighted"]["delivery_ratio"]["mean"]
    adv = scen["priority_load"]["weighted"]["sos_latency_advantage"]
    hv = scen["hopcount_vs_weighted"]
    cache = ROOT / "docs" / "testing" / "results" / "deck_pytest.json"
    tests = json.loads(cache.read_text(encoding="utf-8"))["passed"] if cache.exists() else None
    if tests is None:
        raise SystemExit("run `python docs/generate_final_ppt.py` first: it records the fresh pytest result the poster quotes")
    pages = len(pymupdf.open(ROOT / "docs" / "report" / "EcoMesh_Mini_Project_Report.pdf"))

    tmp = Path(tempfile.mkdtemp(prefix="ecomesh_poster_"))
    arch = tmp / "arch.png"
    pymupdf.open(FIG / "fig_architecture.pdf")[0].get_pixmap(dpi=200).save(arch)
    from PIL import Image, ImageChops
    im = Image.open(arch).convert("RGB")
    box = ImageChops.difference(im, Image.new("RGB", im.size, "white")).getbbox()  # trim the blank margin
    if box:
        im.crop((max(box[0] - 20, 0), max(box[1] - 20, 0), box[2] + 20, box[3] + 20)).save(arch)
    qr = qrcode.QRCode(border=2, box_size=12)
    qr.add_data(REPO_URL)
    qr.make(fit=True)
    qr_png = tmp / "qr.png"
    qr.make_image(fill_color="#0E1114", back_color="#FFFFFF").save(qr_png)

    css = """
@page { size: 420mm 594mm; margin: 0; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, Arial, sans-serif; color: #14181D; background: #fff; }
.poster { width: 420mm; height: 593mm; overflow: hidden; display: flex; flex-direction: column; }
header { background: #0E1114; color: #EEF1F4; padding: 8mm 22mm 6mm; }
header .eyebrow { font-size: 15pt; letter-spacing: .12em; color: #A6AFB9; font-weight: 700; text-transform: uppercase; }
header h1 { font-size: 68pt; line-height: 1; margin: 4mm 0 3mm; font-weight: 800; letter-spacing: -.02em; }
header .tag { font-size: 28pt; color: #A6AFB9; max-width: 330mm; line-height: 1.2; }
header .team { margin-top: 5mm; font-size: 22pt; color: #EEF1F4; }
header .team span { color: #5B9CF0; font-weight: 700; }
main { flex: 1; padding: 10mm 22mm 6mm; display: grid; grid-template-columns: 1fr 1fr; gap: 8mm 14mm; align-content: start; zoom: .85; }
section h2 { font-size: 26pt; margin: 0 0 3mm; font-weight: 800; border-bottom: 2pt solid #14181D; padding-bottom: 2mm; }
section p, section li { font-size: 16pt; line-height: 1.3; margin: 0 0 2.5mm; color: #14181D; }
section ul { margin: 0; padding-left: 8mm; }
.full { grid-column: 1 / -1; }
.resrow { display: grid; grid-template-columns: 1fr 1fr; gap: 12mm; align-items: stretch; }
.chart svg { margin-top: 2mm; }
.stats { display: grid; grid-template-columns: 1fr 1fr; gap: 4mm; }
.chart { background: #F3F5F8; border: 1pt solid #D5DBE2; border-radius: 3mm; padding: 4mm 6mm; }
.chart .t { font-size: 15pt; color: #4D5864; margin-bottom: 1mm; }
.stat { background: #F3F5F8; border: 1pt solid #D5DBE2; border-radius: 3mm; padding: 4mm 5mm 3mm; }
.stat b { display: block; font-size: 34pt; color: #5B9CF0; line-height: 1.05; }
.stat span { font-size: 13pt; color: #4D5864; line-height: 1.25; display: block; margin-top: 2mm; }
.stat.sos b { color: #E0464C; }
img { display: block; max-width: 100%; }
.archrow { display: grid; grid-template-columns: 1.45fr 1fr; gap: 12mm; align-items: start; }
.arch img { width: 100%; max-height: 150mm; object-fit: contain; margin: 0 auto; }
.shots { display: grid; grid-template-columns: 1.05fr .8fr 2fr 1.35fr; gap: 6mm; align-items: start; }
.shots img { width: 100%; height: 74mm; object-fit: cover; object-position: top; }
.lf h3 { font-size: 20pt; margin: 0 0 2mm; }
.lf ul { margin: 0 0 5mm; padding-left: 6mm; }
.lf li { font-size: 13pt !important; margin-bottom: 1.5mm !important; }
.shots img { border: 1pt solid #D5DBE2; border-radius: 2mm; }
.cap { font-size: 13pt; color: #4D5864; margin-top: 2mm; }
.steps { counter-reset: s; list-style: none; padding: 0; }
.steps li { counter-increment: s; position: relative; padding-left: 13mm; }
.steps li::before { content: counter(s); position: absolute; left: 0; top: 0; width: 9mm; height: 9mm; border-radius: 50%; background: #5B9CF0; color: #0E1114; font-weight: 800; font-size: 15pt; text-align: center; line-height: 9mm; }
.formula { background: #0E1114; color: #EEF1F4; font-size: 28pt; font-weight: 700; text-align: center; padding: 6mm; border-radius: 3mm; margin: 2mm 0 3mm; letter-spacing: .02em; }
footer { background: #0E1114; color: #A6AFB9; padding: 6mm 22mm; display: flex; align-items: center; justify-content: space-between; gap: 16mm; }
footer .l { font-size: 17pt; line-height: 1.5; }
footer .l b { color: #EEF1F4; font-size: 21pt; }
footer .url { color: #5B9CF0; font-size: 19pt; }
footer img { width: 38mm; height: 38mm; background: #fff; padding: 2mm; border-radius: 2mm; }
"""
    stats = (
        f'<div class="stat"><b>{100 * delivery:.1f}%</b><span>delivered on a 40-node mesh at 20% packet loss, with relay and gateway failures</span></div>'
        f'<div class="stat sos"><b>{adv:.1f}&times;</b><span>faster median delivery for an SOS than routine traffic under load</span></div>'
        f'<div class="stat"><b>{100 * hv["weighted"]["delivery_ratio"]["mean"]:.0f}% vs {100 * hv["hopcount"]["delivery_ratio"]["mean"]:.0f}%</b><span>weighted routing against hop-count routing on identical seeds</span></div>'
        f'<div class="stat"><b>{tests}</b><span>automated tests pass; {met} of {total} target metrics fully met</span></div>'
    )
    loss = json.loads((ROOT / "docs" / "report" / "evidence" / "results" / "loss.json").read_text(encoding="utf-8"))
    bars = ""
    for i, r in enumerate(loss):
        h = 100 * r["delivery_mean"] * 1.6
        x = 20 + i * 60
        bars += (f'<rect x="{x}" y="{180 - h:.1f}" width="40" height="{h:.1f}" fill="#5B9CF0"/>'
                 f'<text x="{x + 20}" y="{172 - h:.1f}" font-size="12" text-anchor="middle" fill="#14181D">{100 * r["delivery_mean"]:.0f}%</text>'
                 f'<text x="{x + 20}" y="198" font-size="12" text-anchor="middle" fill="#4D5864">{100 * r["loss"]:.0f}%</text>')
    chart = (f'<div class="t">Delivery ratio as packet loss rises ({loss[0]["nodes"]}-node mesh, {loss[0]["runs"]} runs each)</div>'
             f'<svg viewBox="0 0 390 222" style="height:48mm;width:100%"><line x1="10" y1="180" x2="380" y2="180" stroke="#14181D"/>{bars}'
             f'<text x="195" y="219" font-size="12" text-anchor="middle" fill="#4D5864">per-link packet loss</text></svg>')
    misses = "; ".join(f"{r['name'].lower()}" for r in not_met)
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>EcoMesh poster</title><style>{css}</style></head><body><div class="poster">
<header>
 <div class="eyebrow">Mini Project I &middot; T.E. Semester V &middot; Department of Computer Engineering &middot; SPIT &middot; Group 20</div>
 <h1>EcoMesh</h1>
 <div class="tag">A peer-to-peer communication mesh for disaster relief: an SOS hops from device to device until it reaches a rescue team</div>
 <div class="team"><span>Twissha Shah</span> &nbsp;&middot;&nbsp; <span>Miti Shah</span> &nbsp;&middot;&nbsp; <span>Tanvi Sheth</span> &nbsp;&nbsp;|&nbsp;&nbsp; Guide: Prof. Anuj Tawari</div>
</header>
<main>
 <section>
  <h2>The problem</h2>
  <p>After an earthquake, fire or building collapse, cell towers fail or are jammed. Messaging apps need a server far away, so they stop even for two people in the same building.</p>
  <p>But phones still have battery, and nearby devices can still reach each other. People trapped inside cannot tell anyone where they are, and rescuers search room by room.</p>
 </section>
 <section>
  <h2>The idea</h2>
  <p>Make every device both an endpoint and a relay. An SOS travels from phone to phone until it reaches a rescue team or a gateway to the outside. No tower, no internet, no central server.</p>
  <p>Messages are encrypted (AES-256-GCM), identities are signed (Ed25519), and a message with no route is held and sent the moment a path appears.</p>
  <p>The survivor picks one of <b>nine request types</b> (Medical emergency, Injured, Trapped, Fire or smoke, Unsafe building, Need water, Need food, Need medicine, Elderly or child needs help) and can <b>speak</b> the location instead of typing it.</p>
 </section>
 <section class="full">
  <h2>Architecture and how an SOS travels</h2>
  <div class="archrow">
   <div class="arch"><img src="{data_uri(arch)}" alt="EcoMesh architecture"><div class="cap">One node = one process on one event-loop thread. Every layer reaches the network only through the transport interface, so the same engine runs on a simulated radio, on TCP between processes, or on UDP.</div></div>
   <div>
    <ol class="steps">
     <li><b>Route.</b> Dijkstra over a link-state graph that every node builds from its neighbours' reports.</li>
     <li><b>Seal.</b> The payload is encrypted and the packet's identity is signed.</li>
     <li><b>Relay.</b> Every hop sends SOS before routine traffic.</li>
     <li><b>Confirm.</b> The receiver acknowledges; a missed ACK retries on a recomputed route.</li>
     <li><b>Hold.</b> No route? The message is kept and sent when a path appears.</li>
    </ol>
    <div class="formula">cost = 1 + 5 (1 &minus; q) + 3 f</div>
    <p style="font-size:15pt;color:#4D5864">q: share of recent beacons heard; f: recent ACK timeouts. A lossy link costs more than two clean hops, so routes avoid it.</p>
   </div>
  </div>
 </section>
 <section class="full">
  <h2>Measured results</h2>
  <div class="resrow"><div class="stats">{stats}</div><div class="chart">{chart}</div></div>
 </section>
 <section class="full">
  <h2>One app for the whole demonstration, and what it does not do</h2>
  <div class="shots">
   <div><img src="{data_uri(FIG / 'story_survivor_request.png')}" alt="Request form"><div class="cap">Request form: nine request types and a Speak button for voice input</div></div>
   <div><img src="{data_uri(FIG / 'story_survivor_delivered.png')}" alt="Survivor screen"><div class="cap">Survivor phone: SOS delivered, rescue team's reply on top</div></div>
   <div><img src="{data_uri(FIG / 'story_rescue_console.png')}" alt="Rescue console"><div class="cap">Rescue console: request with its type, location and route; reply, filters, history, network map</div></div>
   <div class="lf"><h3>Limits</h3><ul>
    <li>The radio is emulated: real packets over TCP, between configured neighbours only.</li>
    <li>No phone app: a phone opens a web page served by a laptop.</li>
    <li>Voice input uses the browser's online speech service; typing always works.</li>
    <li>One shared key protects the mesh.</li>
    <li>Not fully met: {misses}.</li>
   </ul><h3>Future work</h3><ul>
    <li>Bluetooth LE or Wi-Fi Direct transport and a phone client.</li>
    <li>Per-pair key agreement (X25519).</li>
    <li>Adaptive timers; a usability study.</li>
   </ul></div>
  </div>
 </section>
</main>
<footer>
 <div class="l"><b>Code, report and testing document</b><br><span class="url">{REPO_URL}</span><br>{pages}-page report &middot; {len(rows)} target metrics validated against stored measurements &middot; every number is generated from the code</div>
 <img src="{data_uri(qr_png)}" alt="QR code to the repository">
</footer>
</div></body></html>"""
    return html


def print_pdf(html: str, out: Path, label: str) -> None:
    import pymupdf

    tmp = HERE / "_poster.html"
    tmp.write_text(html, encoding="utf-8")
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", tmp.as_uri()], check=True, capture_output=True, timeout=180)
    tmp.unlink(missing_ok=True)
    print(f"wrote {out} ({len(pymupdf.open(out))} page, {label})")


def main() -> None:
    html = build_html()
    print_pdf(html, OUT, "A2")
    # A3 has the same proportions as A2 (1 : sqrt 2), so the same layout is printed at 1/sqrt(2) scale
    a3 = html.replace("@page { size: 420mm 594mm; margin: 0; }", "@page { size: 297mm 420mm; margin: 0; }\nbody { zoom: 0.70711; }", 1)
    assert a3 != html
    print_pdf(a3, OUT_A3, "A3")


if __name__ == "__main__":
    main()
