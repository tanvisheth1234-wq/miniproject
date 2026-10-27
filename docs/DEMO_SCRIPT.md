# EcoMesh demo script (5 minutes, one app)

The demo uses one app: the device screen served by each device (`story/node.html`). It becomes the survivor phone, the gateway view or the rescue console depending on the device role.

## What is real and what is emulated (say this up front)

- **Real:** five separate programs, each running the full engine. They exchange real packets over TCP: neighbour discovery by HELLO beacons, link-state gossip, Dijkstra routing, acknowledgements and retries, held messages, AES-256-GCM encryption, Ed25519 signing, and a SQLite log per device.
- **Emulated:** the radio. A config file says which devices can hear each other, so a message can only reach the rescue team by hopping through the others. A real phone app would swap the transport layer for Bluetooth or Wi-Fi Direct.
- **The phone is only a screen.** The engine runs on the laptop. The phone opens the device's web page over the same Wi-Fi or hotspot.

## Set up (do this before the audience arrives)

All devices on one laptop, with a phone for the survivor screen:

1. Connect the laptop and the phone to the same Wi-Fi, or to the phone's hotspot (no internet needed).
2. In the project folder run:
   ```
   python -m story.local --phone
   ```
3. The terminal lists one link per device. On the phone open the link for **Trapped person** (port 8101). On the laptop open **Rescue team** (port 8105) in a browser.

Two laptops (more convincing): put each laptop's Wi-Fi IPv4 address (`ipconfig`) into `story/mesh_two_laptops.json`, then

- laptop A: `python -m story.local --config story/mesh_two_laptops.json --only L1,L2,L3 --phone`
- laptop B: `python -m story.local --config story/mesh_two_laptops.json --only L4,L5 --phone`

Open the survivor screen (L1) on the phone and the rescue console (L5) on a laptop.

Keep three browser tabs ready: survivor (8101), gateway (8104), rescue console (8105). The "Demonstration controls" section at the bottom of each screen switches that device off and on.

## The script

1. **The mesh finds itself (30 s).** On the rescue console, point at the network map and the live panel "What this device is doing". Say: "Nobody configured routes. Each device announces itself, hears its neighbours and learns the whole network from their reports." The panel shows the real events ("Can now hear Gateway"). The percentages on the map are the measured link quality.
2. **An SOS crosses the mesh (60 s).** On the phone choose **Trapped**, type "3rd floor, room 304", and hold the SOS button for one second. Show the survivor screen: created, handed to Phone 2, confirmed by the rescue team. Show the rescue console: the request arrives with its need, location and the route it took (Trapped person, Phone 2, Gateway, Rescue team). Point out that the survivor's phone never talked to the rescue team directly.
3. **The rescue team replies (30 s).** On the console press **Reply**, then **Help is on the way**. The reply crosses the mesh back and appears at the top of the survivor screen.
4. **A relay fails (45 s).** In the demonstration controls, switch off **Phone 2** (or whichever relay the route used). Send another message from the survivor. It still arrives, by the other path (Phone 3). Show the activity panel: the lost contact and the new route.
5. **The gateway fails (60 s).** Switch off the **Gateway**. Send an SOS. The survivor screen says "Saved, waiting for a path" and explains that the phone keeps the message safe. Switch the gateway back on. Within a few seconds the held message is delivered, and the screen changes to "The rescue team has your request".
6. **Check-ins and history (30 s).** Press **I am safe** on another phone screen. It appears under "Marked safe" on the console, at the lowest priority. Open Message history and filter by priority, then press **Export requests (CSV)**.
7. **The numbers (30 s).** Show the results slide: 92.6 % delivery on a 40-node mesh at 20 % loss with failures, SOS about 4.4 times faster than routine traffic under load, weighted routing delivering 99.2 % against 57.4 % for hop count on the same seeds. Finish with what is not built: no real radio, one shared key for the mesh, no phone app.

## If something goes wrong

- A device page does not open: check that the device is in the terminal list and that the phone is on the same Wi-Fi as the laptop.
- A device shows "switched off": open its demonstration controls and switch it back on.
- No route after a restart: wait about ten seconds. Devices need a few HELLO and gossip rounds.
- Keep a screen recording of a successful run as a backup.

## Likely questions

- **"Who would use this?"** Where towers fail or jam but phones still have battery, devices can reach each other directly. This is a prototype of the routing and reliability layer; the transport is built to be replaced by Bluetooth or Wi-Fi Direct.
- **"Is the Wi-Fi not infrastructure?"** In the demo it is the wire that stands in for the radio. Nothing goes through the internet, a server or a router's logic; every hop is device to device.
- **"What if power is down?"** Phones run on batteries for a day or more; the network is what fails. If every device is dead, nothing works, and the report says so.
