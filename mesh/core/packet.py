"""Wire protocol packet: 52-byte header + path + payload + optional signature.

Spec: docs/project-plan.md section 7 (Wire protocol specification).
Network byte order (big-endian) throughout.
"""

from __future__ import annotations

import struct
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional


class PacketError(ValueError):
    """Raised when a packet cannot be built or parsed per the section 7 spec."""


# --- Section 7.3 constants -------------------------------------------------

MAGIC = 0x4D45          # b"ME"
VERSION = 1
DEFAULT_TTL = 10

# --- Section 7.1 field types -------------------------------------------------

class PacketType:
    HELLO = 0
    LINK_STATE = 1
    DATA = 2
    ACK = 3


class Priority:
    SOS = 0
    NORMAL = 1
    STATUS = 2


# --- Section 7.1 flags bitfield ---------------------------------------------

FLAG_ENCRYPTED = 1 << 0
FLAG_NEEDS_ACK = 1 << 1
FLAG_STORE_FORWARD_OK = 1 << 2
FLAG_SIGNED = 1 << 3

# --- Sizes -------------------------------------------------------------------

HEADER_SIZE = 52
NODE_ID_SIZE = 8
MSG_ID_SIZE = 16
SIGNATURE_SIZE = 64

# offset: 0     2     3    4    5    6      7          8         24    32    40         48           50        51
# field:  magic version type priority ttl flags hop_count msg_id(16) src(8) dst(8) timestamp(8) payload_len(2) path_len reserved
HEADER_FORMAT = ">H B B B B B B 16s 8s 8s Q H B B"
assert struct.calcsize(HEADER_FORMAT) == HEADER_SIZE

RESCUE_DST = "RESCUE__"
BROADCAST_DST = "BCAST___"


def _encode_node_id(node_id: str) -> bytes:
    raw = node_id.encode("ascii")
    if len(raw) > NODE_ID_SIZE:
        raise PacketError(
            f"node id {node_id!r} exceeds {NODE_ID_SIZE} bytes when ASCII-encoded"
        )
    return raw.ljust(NODE_ID_SIZE, b"\x00")


def _decode_node_id(raw: bytes) -> str:
    return raw.rstrip(b"\x00").decode("ascii")


@dataclass
class Packet:
    type: int
    priority: int
    src: str
    dst: str
    msg_id: uuid.UUID = field(default_factory=uuid.uuid4)
    version: int = VERSION
    ttl: int = DEFAULT_TTL
    hop_count: int = 0
    flags: int = 0
    timestamp: int = field(default_factory=lambda: int(time.time() * 1000))
    path: list = field(default_factory=list)
    payload: bytes = b""
    signature: Optional[bytes] = None

    # -- flag convenience accessors ------------------------------------

    @property
    def encrypted(self) -> bool:
        return bool(self.flags & FLAG_ENCRYPTED)

    @property
    def needs_ack(self) -> bool:
        return bool(self.flags & FLAG_NEEDS_ACK)

    @property
    def store_forward_ok(self) -> bool:
        return bool(self.flags & FLAG_STORE_FORWARD_OK)

    @property
    def signed(self) -> bool:
        return bool(self.flags & FLAG_SIGNED) or self.signature is not None

    # -- (de)serialisation -----------------------------------------------

    def pack(self) -> bytes:
        """Serialise this packet to bytes per section 7."""
        if not (0 <= self.type <= 0xFF):
            raise PacketError(f"type out of range: {self.type}")
        if not (0 <= self.priority <= 0xFF):
            raise PacketError(f"priority out of range: {self.priority}")
        if not (0 <= self.ttl <= 0xFF):
            raise PacketError(f"ttl out of range: {self.ttl}")
        if not (0 <= self.hop_count <= 0xFF):
            raise PacketError(f"hop_count out of range: {self.hop_count}")
        if len(self.path) > 0xFF:
            raise PacketError("path exceeds 255 entries (path_len is 1 byte)")
        if len(self.payload) > 0xFFFF:
            raise PacketError("payload exceeds 65535 bytes (payload_len is 2 bytes)")
        if self.timestamp < 0 or self.timestamp > 0xFFFFFFFFFFFFFFFF:
            raise PacketError(f"timestamp out of range: {self.timestamp}")

        flags = self.flags
        if self.signature is not None:
            if len(self.signature) != SIGNATURE_SIZE:
                raise PacketError(
                    f"signature must be {SIGNATURE_SIZE} bytes, got {len(self.signature)}"
                )
            flags |= FLAG_SIGNED
        elif flags & FLAG_SIGNED:
            raise PacketError("flags bit3 (signed) set but no signature provided")

        header = struct.pack(
            HEADER_FORMAT,
            MAGIC,
            self.version,
            self.type,
            self.priority,
            self.ttl,
            flags,
            self.hop_count,
            self.msg_id.bytes,
            _encode_node_id(self.src),
            _encode_node_id(self.dst),
            self.timestamp,
            len(self.payload),
            len(self.path),
            0,  # reserved
        )

        body = header + b"".join(_encode_node_id(p) for p in self.path) + self.payload
        if self.signature is not None:
            body += self.signature
        return body

    @classmethod
    def unpack(cls, data: bytes) -> "Packet":
        """Parse and validate bytes produced by pack(). Raises PacketError on any
        malformed input (bad magic, truncated header/path/payload/signature)."""
        if len(data) < HEADER_SIZE:
            raise PacketError(
                f"truncated header: need {HEADER_SIZE} bytes, got {len(data)}"
            )

        (
            magic,
            version,
            type_,
            priority,
            ttl,
            flags,
            hop_count,
            msg_id_raw,
            src_raw,
            dst_raw,
            timestamp,
            payload_len,
            path_len,
            _reserved,
        ) = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])

        if magic != MAGIC:
            raise PacketError(f"bad magic: expected {MAGIC:#06x}, got {magic:#06x}")

        offset = HEADER_SIZE
        path_bytes_len = path_len * NODE_ID_SIZE
        if len(data) < offset + path_bytes_len:
            raise PacketError("truncated path")
        path = [
            _decode_node_id(data[offset + i * NODE_ID_SIZE: offset + (i + 1) * NODE_ID_SIZE])
            for i in range(path_len)
        ]
        offset += path_bytes_len

        if len(data) < offset + payload_len:
            raise PacketError("truncated payload")
        payload = data[offset: offset + payload_len]
        offset += payload_len

        signature = None
        if flags & FLAG_SIGNED:
            if len(data) < offset + SIGNATURE_SIZE:
                raise PacketError("truncated signature")
            signature = data[offset: offset + SIGNATURE_SIZE]
            offset += SIGNATURE_SIZE

        return cls(
            type=type_,
            priority=priority,
            src=_decode_node_id(src_raw),
            dst=_decode_node_id(dst_raw),
            msg_id=uuid.UUID(bytes=msg_id_raw),
            version=version,
            ttl=ttl,
            hop_count=hop_count,
            flags=flags,
            timestamp=timestamp,
            path=path,
            payload=payload,
            signature=signature,
        )

    @staticmethod
    def remaining_length(header: bytes) -> int:
        """Given exactly HEADER_SIZE bytes, return how many more bytes
        (path + payload + optional signature) complete the packet.

        Lets a stream transport (TCP) read a full packet without a separate
        length prefix: read HEADER_SIZE bytes, call this, then read that many
        more.
        """
        if len(header) != HEADER_SIZE:
            raise PacketError(f"expected exactly {HEADER_SIZE} header bytes")
        fields = struct.unpack(HEADER_FORMAT, header)
        magic, flags, payload_len, path_len = fields[0], fields[5], fields[11], fields[12]
        if magic != MAGIC:
            raise PacketError(f"bad magic: expected {MAGIC:#06x}, got {magic:#06x}")
        length = path_len * NODE_ID_SIZE + payload_len
        if flags & FLAG_SIGNED:
            length += SIGNATURE_SIZE
        return length


def hexdump(data: bytes, labels: Optional[dict] = None, width: int = 16) -> str:
    """Return a labelled hex dump of ``data``.

    ``labels`` maps a byte offset to a human-readable field name; a marker is
    printed above the row containing that offset. Intended for the header
    portion of a packet (see section 24.7: "a hex dump of a real 52-byte
    header with each field labelled").
    """
    labels = labels or {}
    lines = []
    if labels:
        lines.append("Offset  Field")
        for offset in sorted(labels):
            lines.append(f"  {offset:>3}   {labels[offset]}")
        lines.append("")
    for row_start in range(0, len(data), width):
        row = data[row_start: row_start + width]
        hex_part = " ".join(f"{b:02x}" for b in row)
        ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in row)
        lines.append(f"{row_start:04x}  {hex_part:<{width * 3}} {ascii_part}")
    return "\n".join(lines)


HEADER_FIELD_OFFSETS = {
    0: "magic (2 bytes)",
    2: "version (1 byte)",
    3: "type (1 byte)",
    4: "priority (1 byte)",
    5: "ttl (1 byte)",
    6: "flags (1 byte)",
    7: "hop_count (1 byte)",
    8: "msg_id (16 bytes)",
    24: "src (8 bytes)",
    32: "dst (8 bytes)",
    40: "timestamp (8 bytes)",
    48: "payload_len (2 bytes)",
    50: "path_len (1 byte)",
    51: "reserved (1 byte)",
}
