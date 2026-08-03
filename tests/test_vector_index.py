import numpy as np

from chaqimchi_ai.vector_index import VectorIndex


def test_vector_index_numpy_search() -> None:
    emb = np.eye(3, 512, dtype=np.float32)
    idx = VectorIndex("numpy")
    idx.rebuild(emb)
    hits = idx.search(emb[1], threshold=0.5, top_k=3)
    assert any(i == 1 for i, _ in hits)
