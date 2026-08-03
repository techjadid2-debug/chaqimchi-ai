import numpy as np
from cryptography.fernet import Fernet

from chaqimchi_ai.embedding_crypto import decrypt_array, encrypt_array


def test_encrypt_roundtrip() -> None:
    key = Fernet.generate_key()
    src = np.random.randn(4, 512).astype(np.float32)
    blob = encrypt_array(src, key)
    out = decrypt_array(blob, key)
    assert out.shape == src.shape
    assert np.allclose(out, src, atol=1e-5)
