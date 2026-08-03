from pathlib import Path

import numpy as np

from chaqimchi_ai.database import FaceDatabase


def _unit_vec(seed: int) -> np.ndarray:
    v = np.zeros(512, dtype=np.float32)
    v[seed % 512] = 1.0
    return v


def test_add_search_delete_face(tmp_path: Path) -> None:
    db = FaceDatabase(tmp_path / "db")
    e1 = db.add_face("Ali", _unit_vec(1))
    e2 = db.add_face("Vali", _unit_vec(2))

    hits = db.search(_unit_vec(1), threshold=0.9)
    assert len(hits) == 1
    assert hits[0]["name"] == "Ali"

    assert db.delete_face(e1["id"]) is True
    assert db.count == 1
    assert db.delete_face("missing") is False

    assert db.get_person(e2["id"])["name"] == "Vali"
