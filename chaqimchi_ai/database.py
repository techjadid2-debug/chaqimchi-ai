"""Yuz vektor ma'lumotlar bazasi (Production Edition)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from chaqimchi_ai.embedding_crypto import (
    decrypt_array,
    encrypt_array,
    resolve_embedding_key,
)
from chaqimchi_ai.vector_index import VectorIndex


class FaceDatabase:
    def __init__(
        self,
        db_path: Path,
        *,
        encrypt_embeddings: bool = False,
        embedding_key: Optional[bytes] = None,
        vector_backend: str = "numpy",
    ):
        self.db_path = db_path
        self.meta_path = db_path / "metadata.json"
        self.embs_path = db_path / "embeddings.npy"
        self.embs_enc_path = db_path / "embeddings.enc"

        self._encrypt = encrypt_embeddings
        self._key = embedding_key if embedding_key is not None else resolve_embedding_key()
        if self._encrypt and not self._key:
            raise ValueError(
                "encrypt_embeddings=true uchun CHAQIMCHI_EMBEDDING_KEY (Fernet) kerak"
            )

        self.db_path.mkdir(parents=True, exist_ok=True)
        self.metadata: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None
        self._index = VectorIndex(backend=vector_backend)

        self._load()

    def _load(self) -> None:
        if self.meta_path.exists():
            with open(self.meta_path, encoding="utf-8") as f:
                self.metadata = json.load(f)

        if self._encrypt and self.embs_enc_path.is_file():
            data = self.embs_enc_path.read_bytes()
            self.embeddings = decrypt_array(data, self._key)  # type: ignore[arg-type]
        elif self.embs_path.exists():
            self.embeddings = np.load(self.embs_path)
        else:
            self.embeddings = np.empty((0, 512), dtype=np.float32)

        if self.embeddings is not None and len(self.metadata) != self.embeddings.shape[0]:
            raise ValueError(
                f"Metadata ({len(self.metadata)}) va embeddings "
                f"({self.embeddings.shape[0]}) soni mos kelmaydi!"
            )
        self._rebuild_index()

    def _rebuild_index(self) -> None:
        if self.embeddings is not None:
            self._index.rebuild(self.embeddings)
        else:
            self._index.rebuild(np.empty((0, 512), dtype=np.float32))

    def save(self) -> None:
        with open(self.meta_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

        if self.embeddings is not None:
            if self._encrypt and self._key:
                blob = encrypt_array(self.embeddings, self._key)
                self.embs_enc_path.write_bytes(blob)
                if self.embs_path.exists():
                    self.embs_path.unlink()
            else:
                np.save(self.embs_path, self.embeddings)
                if self.embs_enc_path.exists():
                    self.embs_enc_path.unlink()

        self._rebuild_index()

    def add_face(
        self,
        name: str,
        embedding: np.ndarray,
        extra_info: Optional[Dict] = None,
        *,
        face_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        vec = embedding.flatten().astype(np.float32)
        if vec.size != 512:
            raise ValueError("Embedding 512 o'lchamli bo'lishi kerak")
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        face_id = str(face_id or str(uuid.uuid4())[:8]).strip()
        if not face_id:
            raise ValueError("Shaxs ID bo'sh bo'lishi mumkin emas")
        if any(str(item.get("id")) == face_id for item in self.metadata):
            raise ValueError(f"Shaxs ID allaqachon mavjud: {face_id}")
        entry = {
            "id": face_id,
            "name": name,
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extra": extra_info or {},
        }
        self.metadata.append(entry)

        if self.embeddings is None or self.embeddings.size == 0:
            self.embeddings = vec.reshape(1, 512)
        else:
            self.embeddings = np.vstack([self.embeddings, vec.reshape(1, 512)])

        self.save()
        return entry

    def replace_face(
        self,
        face_id: str,
        name: str,
        embedding: np.ndarray,
        extra_info: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """Stable cloud ID'li yuzni bitta save bilan qo'shadi yoki yangilaydi."""
        clean_id = str(face_id).strip()
        if not clean_id:
            raise ValueError("Shaxs ID bo'sh bo'lishi mumkin emas")
        vec = embedding.flatten().astype(np.float32)
        if vec.size != 512:
            raise ValueError("Embedding 512 o'lchamli bo'lishi kerak")
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        entry = {
            "id": clean_id,
            "name": name,
            "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "extra": extra_info or {},
        }
        index = next(
            (i for i, item in enumerate(self.metadata) if str(item.get("id")) == clean_id),
            None,
        )
        if index is None:
            self.metadata.append(entry)
            if self.embeddings is None or self.embeddings.size == 0:
                self.embeddings = vec.reshape(1, 512)
            else:
                self.embeddings = np.vstack([self.embeddings, vec.reshape(1, 512)])
        else:
            self.metadata[index] = entry
            if self.embeddings is None:  # pragma: no cover - load invariant
                raise RuntimeError("Embedding bazasi yuklanmagan")
            self.embeddings[index] = vec
        self.save()
        return entry

    def search(self, query_embedding: np.ndarray, threshold: float = 0.4) -> List[Dict[str, Any]]:
        if self.embeddings is None or self.embeddings.size == 0:
            return []

        vec = query_embedding.flatten().astype(np.float32)
        hits = self._index.search(vec, threshold, top_k=len(self.metadata))

        results: List[Dict[str, Any]] = []
        for idx, score in hits:
            res = self.metadata[idx].copy()
            res["score"] = score
            results.append(res)
        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def get_person(self, face_id: str) -> Optional[Dict[str, Any]]:
        for meta in self.metadata:
            if meta["id"] == face_id:
                return meta.copy()
        return None

    def delete_face(self, face_id: str) -> bool:
        for i, meta in enumerate(self.metadata):
            if meta["id"] == face_id:
                self.metadata.pop(i)
                if self.embeddings is not None:
                    self.embeddings = np.delete(self.embeddings, i, axis=0)
                self.save()
                return True
        return False

    @property
    def count(self) -> int:
        return len(self.metadata)

    @property
    def vector_backend(self) -> str:
        return self._index.backend
