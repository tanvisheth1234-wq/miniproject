"""Section 10 made visible: the same ``mesh.core.crypto`` primitives the
nodes use, exposed one operation at a time, plus a three-node attack drill
that runs real ``Node`` objects and shows what the destination does when a
relay tampers with a message or someone forges a signature."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Optional

from mesh.core import crypto
from mesh.core.discovery import NodeRole
from mesh.core.node import Node
from mesh.core.packet import (
    FLAG_ENCRYPTED,
    FLAG_NEEDS_ACK,
    FLAG_SIGNED,
    Packet,
    PacketType,
    Priority,
)
from mesh.core.transport_sim import SimulatedNetwork, SimulatedTransport

from .lab import PersistentStore

_KEY = crypto.generate_session_key()
_IDENTITIES = {"alice": crypto.generate_keypair(), "mallory": crypto.generate_keypair()}


class SecurityError(ValueError):
    pass


def _identity(name: str) -> crypto.KeyPair:
    if name not in _IDENTITIES:
        raise SecurityError("identity must be 'alice' or 'mallory'")
    return _IDENTITIES[name]


def _hex(value: str, what: str) -> bytes:
    try:
        return bytes.fromhex("".join(value.split()))
    except ValueError as exc:
        raise SecurityError(f"{what} is not valid hexadecimal") from exc


def info() -> dict:
    return {
        "cipher": "AES-256-GCM", "key_bits": 256, "nonce_bytes": crypto.NONCE_SIZE, "tag_bytes": 16,
        "signature": "Ed25519", "signature_bytes": crypto.SIGNATURE_SIZE,
        "session_key": _KEY.hex(),
        "identities": {n: kp.public_bytes.hex() for n, kp in _IDENTITIES.items()},
    }


def seal(text: str, key_hex: Optional[str] = None) -> dict:
    key = _hex(key_hex, "key") if key_hex else _KEY
    try:
        wire = crypto.encrypt_payload(key, text.encode("utf-8"))
    except crypto.CryptoError as exc:
        raise SecurityError(str(exc)) from exc
    nonce, body = wire[: crypto.NONCE_SIZE], wire[crypto.NONCE_SIZE:]
    return {
        "key": key.hex(), "wire": wire.hex(), "nonce": nonce.hex(),
        "ciphertext": body[:-16].hex(), "tag": body[-16:].hex(),
        "plaintext_bytes": len(text.encode("utf-8")), "wire_bytes": len(wire),
    }


def open_(wire_hex: str, key_hex: Optional[str] = None, tamper: bool = False) -> dict:
    key = _hex(key_hex, "key") if key_hex else _KEY
    wire = bytearray(_hex(wire_hex, "ciphertext"))
    flipped = None
    if tamper and len(wire) > crypto.NONCE_SIZE:
        flipped = crypto.NONCE_SIZE  # flip one bit of the first ciphertext byte, as a malicious relay might
        wire[flipped] ^= 0x01
    try:
        plaintext = crypto.decrypt_payload(key, bytes(wire))
    except crypto.CryptoError as exc:
        return {"ok": False, "error": str(exc), "tampered": tamper, "wire": bytes(wire).hex(), "flipped_byte": flipped}
    return {"ok": True, "plaintext": plaintext.decode("utf-8", errors="replace"), "tampered": tamper,
            "wire": bytes(wire).hex(), "flipped_byte": flipped}


def sign(message: str, who: str = "alice") -> dict:
    kp = _identity(who)
    signature = crypto.sign(kp.private_key, message.encode("utf-8"))
    return {"who": who, "public_key": kp.public_bytes.hex(), "signature": signature.hex(), "message": message}


def verify(message: str, public_key_hex: str, signature_hex: str) -> dict:
    try:
        public_key = crypto.load_public_key(_hex(public_key_hex, "public key"))
    except crypto.CryptoError as exc:
        raise SecurityError(str(exc)) from exc
    ok = crypto.verify(public_key, message.encode("utf-8"), _hex(signature_hex, "signature"))
    return {"valid": ok}


# --- the attack drill -------------------------------------------------------------


async def attack_drill() -> dict:
    """A — M — B with encryption and signing on, and M hostile.

    1. A sends a message through M. M forwards it untouched. B reads it.
    2. A (not signing, this once) sends another and M flips a bit of its
       ciphertext. B's AES-GCM tag check fails.
    3. The same tampering against a *signed* message: the Ed25519 signature
       covers the ciphertext, so it is rejected even earlier.
    4. M builds an "SOS from A" signed with its *own* key. B knows A's real
       public key, so the signature check fails.

    Real nodes, real packets, real timers (compressed); every verdict comes
    from B's own event log."""
    net = SimulatedNetwork(seed=7)
    net.set_link("A", "M", latency_ms=(2, 4))
    net.set_link("M", "B", latency_ms=(2, 4))

    def make(node_id: str, role: str = NodeRole.NORMAL, keypair: Optional[crypto.KeyPair] = None) -> Node:
        node = Node(
            node_id, SimulatedTransport(node_id, net), role=role, hello_interval=0.05, neighbour_timeout=0.6,
            prune_interval=0.1, link_state_interval=0.08, ack_timeout=0.4, ack_poll_interval=0.05,
            session_key=_KEY, keypair=keypair,
        )
        node.store.close()
        node.store = PersistentStore(node_id, None)
        return node

    a, m, b = make("A", keypair=_IDENTITIES["alice"]), make("M", keypair=_IDENTITIES["mallory"]), make("B", NodeRole.GATEWAY)
    nodes = [a, m, b]
    delivered: list[str] = []
    b.on_deliver = lambda pkt: delivered.append(pkt.payload.decode("utf-8", errors="replace"))
    steps: list[dict] = []

    real_send = m.transport.send

    async def tampering_send(node_id: str, data: bytes) -> None:
        pkt = Packet.unpack(data)
        if pkt.type == PacketType.DATA and node_id == "B" and pkt.src == "A":
            body = bytearray(pkt.payload)
            body[-1] ^= 0x01
            data = replace(pkt, payload=bytes(body)).pack()
        await real_send(node_id, data)

    async def wait_for(condition, timeout: float = 5.0) -> bool:
        """Poll instead of sleeping a fixed time, so a slow machine only makes the drill slower, never wrong."""
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            if condition():
                return True
            await asyncio.sleep(0.02)
        return False

    async def run_step(title: str, what: str, action, expect_kind: Optional[str]) -> None:
        before_delivered, before = len(delivered), _counts(b.store)
        await action()
        if expect_kind is None:
            await wait_for(lambda: len(delivered) > before_delivered)
        else:
            await wait_for(lambda: len(delivered) > before_delivered or _counts(b.store).get(expect_kind, 0) > before.get(expect_kind, 0))
        await asyncio.sleep(0.15)  # a short settle, so an attack that did get through would show up too
        got = delivered[before_delivered:]
        delta = {k: v - before[k] for k, v in _counts(b.store).items() if v - before[k]}
        if expect_kind is None:
            defended, verdict = bool(got), "B accepted and decrypted it" if got else "B never received it"
        else:
            defended = not got and delta.get(expect_kind, 0) > 0
            verdict = f"B dropped it: {expect_kind}" if defended else "B accepted it — the attack got through"
        steps.append({"title": title, "what": what, "delivered": got, "defended": defended,
                      "verdict": verdict, "b_events": delta, "mechanism": expect_kind})

    try:
        for node in nodes:
            await node.start()
        # discovery and gossip must converge, and B must know Alice's public key (learned from M's report),
        # before the drill starts; otherwise a signed message is dropped as "unknown signer" instead
        await wait_for(lambda: "A" in b._known_keys, timeout=15.0)

        await run_step("Honest relay", "M forwards A's message untouched.",
                       lambda: a.send("B", b"Honest message: four of us in room 302", Priority.NORMAL, needs_ack=True),
                       None)

        m.transport.send = tampering_send  # type: ignore[method-assign]

        async def unsigned_then_tampered():
            a._keypair = None  # this one message goes out unsigned, so only AES-GCM stands in the way
            try:
                await a.send("B", b"East stairwell is blocked", Priority.NORMAL, needs_ack=True)
            finally:
                a._keypair = _IDENTITIES["alice"]

        await run_step("Tampered ciphertext (unsigned)", "M flips one bit of the payload. Nothing but the GCM tag can notice.",
                       unsigned_then_tampered, "drop_decrypt_failed")
        await run_step("Tampered ciphertext (signed)", "Same tampering, but A signed the message: the signature fails first.",
                       lambda: a.send("B", b"Water is in the basement", Priority.NORMAL, needs_ack=True),
                       "drop_signature_invalid")
        m.transport.send = real_send  # type: ignore[method-assign]

        async def forge():
            pkt = Packet(
                type=PacketType.DATA, priority=Priority.SOS, src="A", dst="B",
                flags=FLAG_NEEDS_ACK | FLAG_SIGNED | FLAG_ENCRYPTED,
                payload=crypto.encrypt_payload(_KEY, b"FAKE SOS from A: send everyone to the north exit"),
            )
            pkt = replace(pkt, signature=crypto.sign(_IDENTITIES["mallory"].private_key, pkt.identity_bytes()))
            await m.transport.send("B", pkt.pack())

        await run_step("Forged SOS", "M signs a fake “SOS from A” with its own private key.", forge, "drop_signature_invalid")
    finally:
        for node in nodes:
            await node.stop()
        for node in nodes:
            node.store.shutdown()  # type: ignore[attr-defined]

    return {
        "steps": steps,
        "note": "Signing is opt-in mesh-wide in this build, so a forger who simply leaves a packet unsigned is not "
                "caught by signature checks. A deployment would add a policy that rejects unsigned SOS.",
    }


def _counts(store) -> dict[str, int]:
    return {k: store.count_events(k) for k in ("drop_decrypt_failed", "drop_signature_invalid", "drop_unknown_signer")}
