"""Vektor qidiruv: numpy (default) yoki FAISS (ixtiyoriy)."""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

_FAISS = None
try:
    import faiss  # type: ignore

    _FAISS = faiss
except ImportError:
    pass


class VectorIndex:
    def __init__(self, backend: str = "numpy") -> None:
        b = backend.lower().strip()
        if b == "faiss" and _FAISS is None:
            b = "numpy"
        self.backend = b
        self._faiss_index: Optional[object] = None
        self._matrix: Optional[np.ndarray] = None

    def rebuild(self, embeddings: np.ndarray) -> None:
        if embeddings is None or embeddings.size == 0:
            self._matrix = np.empty((0, 512), dtype=np.float32)
            self._faiss_index = None
            return

        mat = np.asarray(embeddings, dtype=np.float32)
        norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-8
        self._matrix = mat / norms

        if self.backend == "faiss" and _FAISS is not None:
            dim = self._matrix.shape[1]
            index = _FAISS.IndexFlatIP(dim)
            index.add(self._matrix)
            self._faiss_index = index
        else:
            self._faiss_index = None

    def search(
        self,
        query: np.ndarray,
        threshold: float,
        top_k: int = 10,
    ) -> List[Tuple[int, float]]:
        if self._matrix is None or self._matrix.size == 0:
            return []

        vec = query.flatten().astype(np.float32)
        vec = vec / (float(np.linalg.norm(vec)) + 1e-8)

        if self.backend == "faiss" and self._faiss_index is not None:
            scores, indices = self._faiss_index.search(vec.reshape(1, -1), min(top_k, len(self._matrix)))
            out: List[Tuple[int, float]] = []
            for idx, score in zip(indices[0].tolist(), scores[0].tolist()):
                if idx < 0:
                    continue
                if score >= threshold:
                    out.append((int(idx), float(score)))
            return out

        scores = self._matrix @ vec
        order = np.argsort(-scores)
        results: List[Tuple[int, float]] = []
        for idx in order[:top_k]:
            s = float(scores[idx])
            if s >= threshold:
                results.append((int(idx), s))
        return results
