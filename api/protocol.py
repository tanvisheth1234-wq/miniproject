"""Builds and parses real wire packets for the protocol inspector. Every
byte shown comes from ``mesh.core.packet.Packet.pack()`` / ``unpack()`` --
the page is a window onto the actual encoder, not a re-implementation."""

from __future__ import annotations

import uuid
from typing import Optional

from mesh.core import crypto
from mesh.core.packet import (
    BROADCAST_DST,
    DEFAULT_TTL,
    FLAG_ENCRYPTED,
    FLAG_NEEDS_ACK,
    FLAG_SIGNED,
    FLAG_STORE_FORWARD_OK,
    HEADER_SIZE,
    MAGIC,
    NODE_ID_SIZE,
    RESCUE_DST,
    SIGNATURE_SIZE,
    Packet,
    PacketError,
    PacketType,
    Priority,
)

TYPE_NAMES = {PacketType.HELLO: "HELLO", PacketType.LINK_STATE: "LINK_STATE", PacketType.DATA: "DATA", PacketType.ACK: "ACK"}
PRIORITY_NAMES = {Priority.SOS: "SOS", Priority.NORMAL: "NORMAL", Priority.STATUS: "STATUS"}

# one shared demo identity so "encrypt" and "sign" are reproducible within a session
_DEMO_KEY = crypto.generate_session_key()
_DEMO_KEYPAIR = crypto.generate_keypair()

# (name, offset, size, what it is for)
_HEADER_FIELDS = [
    ("magic", 0, 2, "Constant 0x4D45 (“ME”). Anything else is not our protocol and is dropped."),
    ("version", 2, 1, "Protocol version, so a future format can coexist."),
    ("type", 3, 1, "0 HELLO · 1 LINK_STATE · 2 DATA · 3 ACK."),
    ("priority", 4, 1, "0 SOS · 1 NORMAL · 2 STATUS. Read by every hop's queue."),
    ("ttl", 5, 1, "Hops left. Each relay decrements it; at 0 the packet is dropped."),
    ("flags", 6, 1, "bit0 encrypted · bit1 wants ACK · bit2 store-and-forward OK · bit3 signed."),
    ("hop_count", 7, 1, "How many relays have handled it so far."),
    ("msg_id", 8, 16, "128-bit random id: dedup key and the thing an ACK refers to."),
    ("src", 24, 8, "Originating node id, ASCII, zero-padded."),
    ("dst", 32, 8, "Destination node id, or RESCUE__ for “any gateway or rescue node”."),
    ("timestamp", 40, 8, "Milliseconds since the Unix epoch when the sender created it."),
    ("payload_len", 48, 2, "Length of the payload that follows the path."),
    ("path_len", 50, 1, "Number of 8-byte node ids in the relay path."),
    ("attempt", 51, 1, "Retransmission counter: 0 on the first send, +1 per retry. Lets relays tell a retry from a duplicate."),
]


def _decode_flags(flags: int) -> list[str]:
    names = []
    if flags & FLAG_ENCRYPTED:
        names.append("encrypted")
    if flags & FLAG_NEEDS_ACK:
        names.append("needs_ack")
    if flags & FLAG_STORE_FORWARD_OK:
        names.append("store_forward_ok")
    if flags & FLAG_SIGNED:
        names.append("signed")
    return names


def _field_value(name: str, raw: bytes) -> str:
    n = int.from_bytes(raw, "big")
    if name == "magic":
        return f"0x{n:04X} ({raw.decode('ascii', errors='replace')})"
    if name == "type":
        return TYPE_NAMES.get(n, f"unknown ({n})")
    if name == "priority":
        return PRIORITY_NAMES.get(n, f"unknown ({n})")
    if name == "flags":
        decoded = _decode_flags(n)
        return f"0b{n:08b}" + (f" = {' + '.join(decoded)}" if decoded else " = none")
    if name == "msg_id":
        return str(uuid.UUID(bytes=raw))
    if name in ("src", "dst"):
        return raw.rstrip(b"\x00").decode("ascii", errors="replace")
    return str(n)


def describe(data: bytes) -> dict:
    """Break a serialised packet into labelled regions."""
    pkt = Packet.unpack(data)  # raises PacketError on anything malformed
    fields = []
    for name, offset, size, meaning in _HEADER_FIELDS:
        raw = data[offset: offset + size]
        fields.append({"name": name, "offset": offset, "size": size, "hex": raw.hex(),
                       "value": _field_value(name, raw), "meaning": meaning})

    path_start = HEADER_SIZE
    path_end = path_start + len(pkt.path) * NODE_ID_SIZE
    payload_end = path_end + len(pkt.payload)
    regions = [{"name": "header", "start": 0, "end": HEADER_SIZE}]
    if pkt.path:
        regions.append({"name": "path", "start": path_start, "end": path_end})
    if pkt.payload:
        regions.append({"name": "payload", "start": path_end, "end": payload_end})
    if pkt.signature is not None:
        regions.append({"name": "signature", "start": payload_end, "end": payload_end + SIGNATURE_SIZE})

    return {
        "hex": data.hex(),
        "length": len(data),
        "fields": fields,
        "regions": regions,
        "path": pkt.path,
        "payload_hex": pkt.payload.hex(),
        "payload_text": pkt.payload.decode("utf-8", errors="replace") if not pkt.encrypted else None,
        "signature_hex": pkt.signature.hex() if pkt.signature else None,
        "summary": {
            "type": TYPE_NAMES.get(pkt.type, str(pkt.type)),
            "priority": PRIORITY_NAMES.get(pkt.priority, str(pkt.priority)),
            "src": pkt.src,
            "dst": pkt.dst,
            "ttl": pkt.ttl,
            "hop_count": pkt.hop_count,
            "flags": _decode_flags(pkt.flags),
            "msg_id": str(pkt.msg_id),
        },
    }


def build(
    *,
    type_: str = "DATA",
    priority: int = Priority.SOS,
    src: str = "L1",
    dst: str = RESCUE_DST,
    ttl: int = DEFAULT_TTL,
    hop_count: int = 0,
    path: Optional[list[str]] = None,
    text: str = "",
    needs_ack: bool = True,
    store_forward_ok: bool = True,
    encrypt: bool = False,
    sign: bool = False,
) -> dict:
    """Pack a packet from form fields. ``encrypt`` / ``sign`` use the demo
    key and identity, exactly as ``Node.send`` would with its own."""
    type_codes = {v: k for k, v in TYPE_NAMES.items()}
    if type_ not in type_codes:
        raise PacketError(f"type must be one of {', '.join(type_codes)}")
    flags = 0
    payload = text.encode("utf-8")
    if needs_ack:
        flags |= FLAG_NEEDS_ACK
    if store_forward_ok:
        flags |= FLAG_STORE_FORWARD_OK
    if encrypt:
        payload = crypto.encrypt_payload(_DEMO_KEY, payload)
        flags |= FLAG_ENCRYPTED
    pkt = Packet(
        type=type_codes[type_], priority=priority, src=src, dst=BROADCAST_DST if type_ == "HELLO" else dst,
        ttl=ttl, hop_count=hop_count, flags=flags, path=list(path or []), payload=payload,
    )
    if sign:
        from dataclasses import replace

        pkt = replace(pkt, flags=pkt.flags | FLAG_SIGNED)
        pkt = replace(pkt, signature=crypto.sign(_DEMO_KEYPAIR.private_key, pkt.identity_bytes()))
    data = pkt.pack()
    out = describe(data)
    out["encrypted_with"] = _DEMO_KEY.hex() if encrypt else None
    out["signed_by"] = _DEMO_KEYPAIR.public_bytes.hex() if sign else None
    return out


def parse(hex_string: str) -> dict:
    cleaned = "".join(hex_string.split()).removeprefix("0x")
    try:
        data = bytes.fromhex(cleaned)
    except ValueError as exc:
        raise PacketError("not valid hexadecimal") from exc
    return describe(data)


def relay_step(hex_string: str, relay_id: str) -> dict:
    """What a relay does to a packet: ttl-1, hop_count+1, itself appended to
    the path -- and, crucially, nothing to the payload."""
    from dataclasses import replace

    cleaned = "".join(hex_string.split())
    try:
        pkt = Packet.unpack(bytes.fromhex(cleaned))
    except ValueError as exc:
        raise PacketError("not a valid packet") from exc
    if pkt.ttl <= 0:
        raise PacketError("ttl is 0: this packet would be dropped (ttl_expired)")
    if relay_id in pkt.path:
        raise PacketError(f"{relay_id} is already on the path: this packet would be dropped (loop_detected)")
    after = replace(pkt, ttl=pkt.ttl - 1, hop_count=pkt.hop_count + 1, path=[*pkt.path, relay_id])
    return {"before": describe(pkt.pack()), "after": describe(after.pack())}


def constants() -> dict:
    return {"magic": f"0x{MAGIC:04X}", "header_size": HEADER_SIZE, "node_id_size": NODE_ID_SIZE,
            "signature_size": SIGNATURE_SIZE, "default_ttl": DEFAULT_TTL, "rescue_dst": RESCUE_DST}
