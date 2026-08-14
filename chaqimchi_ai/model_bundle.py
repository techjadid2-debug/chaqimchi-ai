"""Commercial Face ID model bundle'ini fail-closed tekshirish."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model_manifest(path: Path) -> List[str]:
    errors: List[str] = []
    if not path.is_file():
        return [f"commercial model manifesti topilmadi: {path}"]
    try:
        data: Dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"commercial model manifesti o'qilmadi: {exc}"]
    if data.get("licensed_for_commercial_use") is not True:
        errors.append("commercial model litsenziyasi manifestda tasdiqlanmagan")
    reference = str(data.get("license_reference") or "")
    if not reference or "REQUIRED" in reference:
        errors.append("commercial model license reference berilmagan")
    files = data.get("files") or {}
    if not isinstance(files, dict) or not files:
        errors.append("commercial model fayllari manifestda yo'q")
        return errors
    for name, expected in files.items():
        model = path.parent / str(name)
        if not model.is_file():
            errors.append(f"commercial model fayli topilmadi: {name}")
            continue
        if sha256(model) != str(expected).lower():
            errors.append(f"commercial model SHA-256 mos emas: {name}")
    return errors
