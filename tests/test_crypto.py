import pytest

from mesh.core.crypto import (
    CryptoError,
    KEY_SIZE,
    NONCE_SIZE,
    decrypt_payload,
    encrypt_payload,
    generate_keypair,
    generate_session_key,
    load_public_key,
    sign,
    verify,
)


# --- AES-256-GCM payload encryption ---------------------------------------------

def test_generate_session_key_is_32_bytes():
    key = generate_session_key()
    assert len(key) == KEY_SIZE


def test_encrypt_decrypt_round_trip():
    key = generate_session_key()
    plaintext = b"four of us in room 302, one unconscious"
    ciphertext = encrypt_payload(key, plaintext)
    assert decrypt_payload(key, ciphertext) == plaintext


def test_ciphertext_is_nonce_prefixed_per_section_7_2():
    key = generate_session_key()
    ciphertext = encrypt_payload(key, b"hello")
    assert len(ciphertext) >= NONCE_SIZE + len(b"hello")  # nonce + ciphertext + GCM tag


def test_ciphertext_does_not_contain_plaintext():
    key = generate_session_key()
    plaintext = b"trapped in east stairwell"
    ciphertext = encrypt_payload(key, plaintext)
    assert plaintext not in ciphertext


def test_two_encryptions_of_same_plaintext_differ():
    # fresh random nonce each time -- relays must not be able to spot
    # identical repeated SOS payloads by comparing ciphertext bytes
    key = generate_session_key()
    a = encrypt_payload(key, b"help")
    b = encrypt_payload(key, b"help")
    assert a != b


def test_decrypt_with_wrong_key_fails():
    key = generate_session_key()
    wrong_key = generate_session_key()
    ciphertext = encrypt_payload(key, b"secret location")
    with pytest.raises(CryptoError):
        decrypt_payload(wrong_key, ciphertext)


def test_tampered_ciphertext_fails_gcm_tag_check():
    key = generate_session_key()
    ciphertext = bytearray(encrypt_payload(key, b"secret location"))
    ciphertext[-1] ^= 0xFF  # flip a bit in the tag/ciphertext
    with pytest.raises(CryptoError):
        decrypt_payload(key, bytes(ciphertext))


def test_decrypt_rejects_input_shorter_than_nonce():
    key = generate_session_key()
    with pytest.raises(CryptoError):
        decrypt_payload(key, b"short")


def test_encrypt_rejects_wrong_key_size():
    with pytest.raises(CryptoError):
        encrypt_payload(b"too short", b"data")


def test_associated_data_must_match_on_decrypt():
    key = generate_session_key()
    ciphertext = encrypt_payload(key, b"payload", associated_data=b"dst=GATEWAY")
    with pytest.raises(CryptoError):
        decrypt_payload(key, ciphertext, associated_data=b"dst=ATTACKER")


def test_associated_data_matching_succeeds():
    key = generate_session_key()
    ciphertext = encrypt_payload(key, b"payload", associated_data=b"dst=GATEWAY")
    assert decrypt_payload(key, ciphertext, associated_data=b"dst=GATEWAY") == b"payload"


# --- Ed25519 header/path signing --------------------------------------------------

def test_generate_keypair_public_bytes_is_32():
    kp = generate_keypair()
    assert len(kp.public_bytes) == 32


def test_sign_verify_round_trip():
    kp = generate_keypair()
    message = b"header+path bytes for an SOS from N33"
    signature = sign(kp.private_key, message)
    assert verify(kp.public_key, message, signature) is True


def test_verify_fails_for_tampered_message():
    kp = generate_keypair()
    message = b"header+path bytes"
    signature = sign(kp.private_key, message)
    assert verify(kp.public_key, b"different bytes", signature) is False


def test_verify_fails_for_wrong_public_key_forged_sos():
    """Section 10's threat model: a stranger forging an SOS from someone
    else's node ID must be caught."""
    real = generate_keypair()
    attacker = generate_keypair()
    message = b"SOS from N33"
    forged_signature = sign(attacker.private_key, message)

    assert verify(real.public_key, message, forged_signature) is False


def test_verify_never_raises_on_garbage_signature():
    kp = generate_keypair()
    assert verify(kp.public_key, b"message", b"not a real signature") is False


def test_verify_rejects_wrong_length_signature():
    kp = generate_keypair()
    assert verify(kp.public_key, b"message", b"\x00" * 10) is False


def test_load_public_key_round_trip():
    kp = generate_keypair()
    reconstructed = load_public_key(kp.public_bytes)
    message = b"header bytes"
    signature = sign(kp.private_key, message)
    assert verify(reconstructed, message, signature) is True


def test_load_public_key_rejects_wrong_size():
    with pytest.raises(CryptoError):
        load_public_key(b"too short")
