from app.security import TokenCipher, generate_oauth_state, hash_oauth_state


def test_state_hash_is_stable_and_secret_is_not_stored():
    raw, digest = generate_oauth_state()
    assert raw != digest
    assert hash_oauth_state(raw) == digest
    assert len(digest) == 64


def test_token_cipher_round_trip():
    cipher = TokenCipher("a sufficiently long development encryption secret")
    encrypted = cipher.encrypt("instagram-token")
    assert encrypted != "instagram-token"
    assert cipher.decrypt(encrypted) == "instagram-token"
