"""Confidentiality, integrity and sender authenticity for the wire
protocol. Spec: docs/project-plan.md section 10 (Security).

- Payload encryption: AES-256-GCM. Relays need ``dst``/``ttl`` from the
  header (plaintext, section 7.1) but the payload is opaque bytes to
  them; GCM's authentication tag also catches a relay tampering with it.
- Header/path signing: Ed25519. Proves a message genuinely came from the
  node whose ID is in ``src``, so a relay can't forge an SOS.

Never implement the primitives yourself -- both wrap ``cryptography``
(vetted, audited) rather than hand-rolled AES/EdDSA (section 10's
explicit guidance). Key establishment here is Phase 1's pre-shared
session key (section 10: "get it working"); per-pair X25519 agreement
is a later-phase upgrade, not implemented here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature, InvalidTag
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- section 7.2: payload is "AES-256-GCM ciphertext (12-byte nonce prefixed)" -

NONCE_SIZE = 12
KEY_SIZE = 32  # AES-256
SIGNATURE_SIZE = 64  # Ed25519 signatures are always 64 bytes, matches packet.py


class CryptoError(ValueError):
    """Raised for any encrypt/decrypt/sign/verify failure -- bad key size,
    forged signature, tampered ciphertext, truncated input."""


# --- payload confidentiality (AES-256-GCM) ---------------------------------------

def generate_session_key() -> bytes:
    """A fresh random 32-byte AES-256 key. Phase 1's pre-shared key: every
    node in the mesh is configured with the same key out of band (section
    10's key establishment table)."""
    return AESGCM.generate_key(bit_length=256)


def encrypt_payload(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> bytes:
    """Encrypt ``plaintext`` with AES-256-GCM, returning
    ``nonce (12 bytes) || ciphertext (includes the GCM tag)`` -- exactly
    the wire layout section 7.2 specifies for the payload field.

    ``associated_data``, if given, is authenticated but not encrypted --
    intended for header fields that must not be tampered with in transit
    even though relays need to read them (e.g. dst, ttl).
    """
    if len(key) != KEY_SIZE:
        raise CryptoError(f"key must be {KEY_SIZE} bytes, got {len(key)}")
    aesgcm = AESGCM(key)
    nonce = _random_nonce()
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data or None)
    return nonce + ciphertext


def decrypt_payload(key: bytes, data: bytes, associated_data: bytes = b"") -> bytes:
    """Inverse of ``encrypt_payload``. Raises ``CryptoError`` if the key
    is wrong, the ciphertext was tampered with, or ``data`` is too short
    to even contain a nonce -- callers must treat all three the same way
    (drop the message), so they're collapsed into one exception type."""
    if len(key) != KEY_SIZE:
        raise CryptoError(f"key must be {KEY_SIZE} bytes, got {len(key)}")
    if len(data) < NONCE_SIZE:
        raise CryptoError("ciphertext shorter than the nonce prefix")
    nonce, ciphertext = data[:NONCE_SIZE], data[NONCE_SIZE:]
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, associated_data or None)
    except InvalidTag as exc:  # wrong key, tampered ciphertext, or mismatched associated_data
        raise CryptoError("decryption failed: wrong key or tampered payload") from exc
    except ValueError as exc:
        raise CryptoError(f"decryption failed: {exc}") from exc


def _random_nonce() -> bytes:
    return os.urandom(NONCE_SIZE)


# --- header/path authenticity (Ed25519) ---------------------------------------

@dataclass
class KeyPair:
    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @property
    def public_bytes(self) -> bytes:
        """The 32-byte raw public key, as distributed in HELLO (section 10)."""
        return self.public_key.public_bytes_raw()


def generate_keypair() -> KeyPair:
    """A fresh Ed25519 identity for one node."""
    private_key = Ed25519PrivateKey.generate()
    return KeyPair(private_key=private_key, public_key=private_key.public_key())


def load_public_key(raw: bytes) -> Ed25519PublicKey:
    """Reconstruct a peer's public key from the 32 raw bytes carried in
    its HELLO payload."""
    if len(raw) != 32:
        raise CryptoError(f"Ed25519 public key must be 32 bytes, got {len(raw)}")
    return Ed25519PublicKey.from_public_bytes(raw)


def sign(private_key: Ed25519PrivateKey, message: bytes) -> bytes:
    """Sign ``message`` (header + path, per section 7.2), producing the
    64-byte signature that goes in the packet's trailing signature field."""
    return private_key.sign(message)


def verify(public_key: Ed25519PublicKey, message: bytes, signature: bytes) -> bool:
    """True if ``signature`` over ``message`` genuinely came from the
    holder of ``public_key``. Never raises -- a forged SOS should be
    dropped, not crash the receiver, so this collapses
    ``InvalidSignature`` into ``False``."""
    if len(signature) != SIGNATURE_SIZE:
        return False
    try:
        public_key.verify(signature, message)
        return True
    except InvalidSignature:
        return False
