# EcoMesh: final work plan (everything left, A to Z)

Branch for all of this: `develop_5`. Goal: finish the whole project (code, demo, testing, report, deck, poster) in one go.
Read `docs/HANDOFF.md` first for the project background and `docs/contribution-log.md` for who built what.

## 0. Decisions already made

1. **One app, not two.** The device screen `story/node.html` is the single frontend and the demo. It becomes the survivor phone, the gateway view or the rescue console depending on the device role. The React website in `ui/` is NOT part of the demo any more. It stays in the repo and in the report as the *simulation lab* that produced the experiment results.
2. **Honest framing.** This is a working prototype of the routing and reliability layer. The radio is emulated (devices only talk to configured neighbours over TCP). A real product would swap the transport for Bluetooth or Wi-Fi Direct. Never claim more than that anywhere (demo, report, deck, poster).
3. **A phone is only a screen.** The engine runs on laptops (Python). A phone opens a device's web page in its browser over the same Wi-Fi or hotspot. No website deployment, no cloud.
4. **Do not change the 52-byte packet header and do not touch relay behaviour.** That would invalidate every measurement. So these are NOT being built: a battery indicator, and relay-side store-and-forward.

## 1. Who does what (summary)

| Person | Owns | Files they edit |
|---|---|---|
| **Miti** | Engine and API work: the small gaps, the new endpoints, new features, all their tests | `mesh/core/*`, `story/node.py`, `story/lan_transport.py`, `tests/*`, `sim/*` |
| **Twissha** | The one frontend and the demo: the screen, the network-activity panel, the demo script, screenshots, usability test | `story/node.html` only, `docs/DEMO_SCRIPT.md`, `docs/report/latex/figures/story_*`, usability notes |
| **Tanvi** | Testing, evidence, report, deck, poster, plagiarism, printing, final consistency | `docs/testing/*`, `docs/report/*`, the deck, the poster, `requirements.txt` |

**Why files are split this way:** two people editing the same file causes merge conflicts. Miti owns `story/node.py` (the server side) and Twissha owns `story/node.html` (the screen). They agree on the API in section 2 and work in parallel.

## 2. API contract between Miti (server) and Twissha (screen)

Miti builds these in `story/node.py`. Twissha builds the screen against them (using fake data until they land). All return JSON. Existing endpoints `/api/me`, `/api/sos`, `/api/power` keep working.

| Endpoint | Request | Response |
|---|---|---|
| `POST /api/send` | `{ "dst": "<node id>", "text": "...", "priority": "NORMAL" or "SOS" or "STATUS" }` (priority defaults to NORMAL) | `{ "msg_id": "..." }`; 404 if `dst` is not a known node; 400 if text is empty |
| `POST /api/sos` | `{ "text": "...", "need": "Trapped", "where": "3rd floor" }` (`need` and `where` optional; plain `text` alone must still work) | `{ "msg_id": "..." }` |
| `POST /api/safe` | `{ "where": "..." }` optional | `{ "msg_id": "..." }`; sends a STATUS-priority "I am safe" message to the rescue team |
| `GET /api/events?since=<ms>&limit=200` | `since` optional | `{ "now_ms": ..., "events": [ { "ts_ms", "kind", "peer", "msg_id", "detail" } ] }` ascending by time; use the event kinds the store already logs, do not invent new ones |
| `GET /api/history?kind=&direction=&limit=` | all optional | the same message objects as `thread` in `/api/me`, filtered (this is requirement LOG-5; the filter already exists in `store.py`) |
| `GET /api/export.csv` | none; only for the RESCUE role | CSV of received messages: time, from, priority, need, where, hops, route |

`/api/me` thread entries must also include `need` and `where` (parsed fields, empty if the message is plain text).

**Structured SOS format:** the payload is the JSON string `{"v":1,"need":"...","where":"...","text":"..."}`. The receiver parses it. If parsing fails (an old plain-text message), show the raw text. Nothing else about the protocol changes.

## 3. MITI: engine, API and tests

For every task: one commit for the feature and one commit for its tests (at least), conventional message (`feat(node): ...`, `test(node): ...`), run `python -m pytest -q` before each push, push small and often. Ask your Claude to follow `tests/test_api.py` and `tests/test_node.py` for how to write the tests.

| ID | Task | Details and acceptance |
|---|---|---|
| M0 | Phone access | Check that the web server in `story/node.py` binds to `0.0.0.0` (not only `127.0.0.1`) and print a line at startup such as `Open on your phone: http://<LAN-IP>:8101`. Acceptance: a phone on the same Wi-Fi opens the page. |
| M1 | `POST /api/send` | As in section 2. Reuse `Node.send`. Test: a message sent to a named node across the mesh is delivered; an unknown `dst` returns 404. |
| M2 | `GET /api/events` | Backed by `store.events_since`. Test: after a peer comes up, the events include `peer_up` with that peer; `since` returns only newer events. This unblocks Twissha's network-activity panel, so do it FIRST after M0. |
| M3 | `GET /api/history` (LOG-5) | Expose the existing filter in `store.py`. Test: filtering by direction and kind returns only matching messages. |
| M4 | SNF-3: send held messages the moment a neighbour appears | `_on_peer_up()` in `mesh/core/node.py` (around line 226) never calls the flush. Make it trigger an immediate flush of retained messages, reusing the function the flush loop uses. Test: hold a message for node C with no route; when C appears it is delivered in under 1 second, not after the flush interval. |
| M5 | Rescue reply | No new engine feature: the console replies by calling `/api/send` with `dst` = the sender. Test: the RESCUE device sends "Help is on the way" to a survivor across the mesh and it arrives. |
| M6 | `POST /api/safe` | STATUS priority to `RESCUE__`. Test: it is delivered, and it is ordered below an SOS in the queue. |
| M7 | Structured SOS | As in section 2. Tests: structured round trip; a legacy plain-text message is still shown. |
| M8 | `GET /api/export.csv` | As in section 2. Test: header row plus one row per received message; a non-rescue device gets 403. |
| M9 | Fix the two flaky tests | `test_api.py::test_node_view_reports_peers_with_hop_distance` and `test_ack_multihop.py::test_ack_returns_over_the_path_the_data_took`. Replace the fixed sleeps with a `wait_until(condition, timeout)` helper (put it in `tests/conftest.py`). Acceptance: each passes 20 times in a row when run in a loop. |
| M10 | Tell Tanvi what changed | Short note in the PR or chat: which requirements are now fully met (SNF-3, LOG-5, MSG-1 on devices) so the traceability map can be updated. |
| M11 (optional, only if everything else is done) | Faster recovery | Lower the neighbour timeout from 10 s to about 7 s. RISK: with a 3 s HELLO this can mark healthy links dead under loss. Only do it if the 20% loss sweep still shows no regression after re-running `collect.py`. If in doubt, skip it and leave K3 as "partly met", which the report already states honestly. |

## 4. TWISSHA: the one frontend and the demo (`story/node.html` only)

Design rules: calm, plain, text first. No emojis, no game styling, no animation except where it carries information. Works at 390 px wide (phone) and at 1280 px (console). Large tap targets. Plain-language wording.

| ID | Task | Details and acceptance |
|---|---|---|
| T1 | Network-activity panel | A collapsible panel on every device screen titled "What this device is doing", fed by `/api/events`. Plain sentences, for example "Heard Phone 2 (link good)", "Phone 3 went silent", "New route to the rescue team: L1, L2, L4, L5", "Message held: no route", "Held message sent", "Passed on an SOS from L1". Last 30 lines with times. This is what makes discovery and routing visible to an examiner. |
| T2 | Survivor screen | Keep the SOS hold button. Add a secondary "I'm safe" button, a "Send a message" form (choose a known node, type text), and send the need and where as structured fields. Show a reply from the rescue team ("Help is on the way") prominently above the tracker. |
| T3 | Rescue console | A "Reply" action on each request (quick reply "Help is on the way" plus free text), a separate "Marked safe" list, filter and sort requests by need, the history filter (LOG-5), an "Export CSV" button, and the activity panel. |
| T4 | Gateway view | Show messages passed on and the activity panel. |
| T5 | Network map | Show link quality (line weight and a small label), highlight the live route of a new message. |
| T6 | Polish | One type scale, consistent spacing, check at 360, 390 and 1280 px wide. Nothing toy-like. |
| T7 | Phone | Optional: a web manifest so "Add to home screen" works. Test the survivor page on a real phone through the laptop's IP. |
| T8 | `docs/DEMO_SCRIPT.md` | A 5 minute scripted demo (see section 6). Rehearse it twice. Record a backup screen recording in case the network misbehaves on the day. |
| T9 | Screenshots | Retake the Chapter 10 screenshots from the final screen (1280x760 console, 390x844 phone). Take the two-laptop photo. |
| T10 | Usability test | 5 people, task "send an SOS". Record time and mistakes in `docs/usability.md`. Give the numbers to Tanvi for Chapter 9. |

## 5. TANVI: testing, evidence, report, deck, poster, release

| ID | Task | Details and acceptance |
|---|---|---|
| V1 | `httpx` | Add `httpx` to `requirements.txt` (your backup branch `backup-develop_4-before-reset` has the fix; re-add it as a fresh commit). Acceptance: a fresh virtual environment installs and the API tests run. |
| V2 | Browser checks for the device screen | `ui_walkthrough.cjs` tests the website. Add `docs/testing/device_walkthrough.cjs` that drives the device screen (send SOS, I'm safe, reply, filter, CSV, activity panel) and writes a results JSON next to the existing one. |
| V3 | Re-run all evidence | In order: pytest (3 runs), `python docs/report/evidence/collect.py all`, `live_test.py`, `traceability.py` (update the requirement map: SNF-3, LOG-5, MSG-1), `fr_table.py`, `make_tables.py`, `git_stats.py`. Regenerate the testing PDF with `docs/testing/generate_testing_document.py`. |
| V4 | Report | Miti reformatted it to the template. Check page count (target 25 to 40), headings against the guidelines, and update: test counts, the limitations (SNF-3 and LOG-5 become met), the screenshots, the single-app framing in Chapter 10, and the usability result. Rebuild the PDF (and the Word version if you keep it). |
| V5 | Deck | Update `docs/Phase_III_IV_EcoMesh_Group20.pptx` to the single-app story and the new numbers. |
| V6 | Poster | One page: title, the problem (infrastructure fails, phones still have battery), the architecture figure (`fig_architecture`), the key results chart (`fig_results`), two screenshots of the one app, limitations and future work, a QR code to the repo. |
| V7 | Paper (only if the guide asks) | 4 to 6 pages condensed from the report. |
| V8 | Plagiarism report | Run the final report through the college's checker and attach the result. |
| V9 | Print | Spiral-bound copy, signed certificates, date and place on the declaration. |
| V10 | Final consistency | The same names, commit counts, test counts and numbers in the README, the contribution log, the report, the deck, the poster and the testing document. |

## 6. The demo (5 minutes, one app)

1. Show the five devices on the map. Open the activity panel on one device: it shows real HELLO exchange and the route being learned.
2. On a phone, open the survivor screen and send an SOS with the long press. On the rescue console it arrives with its route. The survivor screen shows "rescue team has your request".
3. Rescue replies "Help is on the way"; the survivor sees it.
4. Switch off the relay on the path. The activity panel shows it lost and a new route; send another SOS and it still arrives.
5. Switch off the gateway. Send an SOS: it is held ("Saved, waiting for a path"). Switch the gateway back on: the held message is delivered.
6. Show the numbers (slide): 92.6 % delivery at 40 nodes with failures, SOS 4.4 times faster, weighted vs hop-count routing, what is not done (radio is emulated).

## 7. Order of work

1. **Miti:** M0, then M2 (events), M1 (send), M3 (history), M7 (structured SOS), M6, M8, then M4, M5, M9. Push each when its tests pass.
2. **Twissha:** build T1 to T6 against the contract in section 2 (fake data until Miti's endpoints land), then switch to the real endpoints.
3. **Tanvi:** V1 now, V2 once the screen is stable, V4 to V6 in parallel, V3 once the code is frozen.
4. **Code freeze:** when M1 to M9 and T1 to T6 are in. After that, only fixes.
5. **Final integration run** on two or three laptops and one phone (section 8).
6. **Then** V3 re-run, regenerate and rebuild everything, V10, V8, V9.

## 8. Final checks before submission

- [ ] `python -m pytest -q` passes, three times in a row
- [ ] A fresh clone plus `pip install -r requirements.txt` works
- [ ] The demo in section 6 runs on 2 or 3 laptops and 1 phone, twice in a row
- [ ] The report builds with 0 undefined references; page count within the template's range
- [ ] Every number in the report matches `docs/report/evidence/results/*.json`
- [ ] README, contribution log, report, deck, poster and testing document agree on names and counts
- [ ] Plagiarism report attached; printed copy ready; declaration dated

## 9. Rules for everyone

- Work on `develop_5`. Never merge between phase branches.
- Commit small and often, under your own identity (`git config user.name`, `git config user.email`). Conventional messages: `feat(scope): ...`, `fix(scope): ...`, `test(scope): ...`, `docs: ...`. No co-author lines.
- Always `git pull` before `git push`. If a push is rejected, pull, then push again. Never force-push, rebase or rewrite history.
- Edit only the files you own (section 1). If you need a change in someone else's file, ask them.
- Do not commit the template zips, the guidelines docx or `ui/package-lock.json` changes.
- Never claim in any document something that was not built and tested.
