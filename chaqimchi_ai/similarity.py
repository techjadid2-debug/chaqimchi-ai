"""Cosine o‘xshashlik (modeldan mustaqil — unit test uchun)."""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np


def cosine_compare_arrays(
    source_embedding: np.ndarray,
    target_embeddings_list: Sequence[np.ndarray],
    threshold: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns:
        indices (N,), scores (N,), matched_mask (N,) bool
    """
    src = np.asarray(source_embedding, dtype=np.float32).reshape(-1)
    if src.size == 0:
        raise ValueError("source_embedding bo‘sh.")

    if not target_embeddings_list:
        empty = np.array([], dtype=np.int64)
        empty_f = np.array([], dtype=np.float32)
        empty_b = np.array([], dtype=bool)
        return empty, empty_f, empty_b

    tgt = np.stack(
        [np.asarray(x, dtype=np.float32).reshape(-1) for x in target_embeddings_list], axis=0
    )
    if tgt.shape[1] != src.shape[0]:
        raise ValueError(f"O‘lcham mos emas: src={src.shape[0]}, tgt={tgt.shape[1]}")

    src = src / (float(np.linalg.norm(src)) + 1e-8)
    tgt = tgt / (np.linalg.norm(tgt, axis=1, keepdims=True) + 1e-8)
    scores = (tgt @ src).astype(np.float32, copy=False)
    matched = scores >= threshold
    indices = np.arange(scores.shape[0], dtype=np.int64)
    return indices, scores, matched
