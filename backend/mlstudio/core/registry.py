"""Registo de modelos (model registry) com versões, estados e artefactos."""
from __future__ import annotations

import json
import platform
import re
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

import joblib
import pandas as pd

from .agent import jsonable, now_iso

STAGES = ("candidato", "produção", "arquivado")


def _lib_versions() -> dict[str, str]:
    import numpy
    import sklearn

    out = {"python": platform.python_version(), "scikit-learn": sklearn.__version__, "pandas": pd.__version__,
           "numpy": numpy.__version__}
    for lib in ("lightgbm", "xgboost", "statsmodels"):
        try:
            out[lib] = __import__(lib).__version__
        except ImportError:
            pass
    return out


class ModelRegistry:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Any] = {}
        self._lock = threading.Lock()

    def _dir(self, version_id: str) -> Path:
        if not re.fullmatch(r"[\w\-.]+", version_id):
            raise KeyError(version_id)
        return self.root / version_id

    def next_version(self, project_id: str) -> int:
        versions = [m.get("version", 0) for m in self.list(project_id)]
        return max(versions, default=0) + 1

    def register(self, meta: dict[str, Any], obj: Any = None, holdout: Optional[pd.DataFrame] = None,
                 artifacts: Optional[dict[str, pd.DataFrame]] = None) -> dict[str, Any]:
        with self._lock:
            version = meta.get("version") or self.next_version(meta["project_id"])
            vid = f"{meta['project_id']}-v{version}-{meta.get('model_id', 'modelo')}"
            folder = self._dir(vid)
            folder.mkdir(parents=True, exist_ok=True)
            meta = {"stage": "candidato", "is_champion": False, **meta, "id": vid, "version": version,
                    "created_at": now_iso(), "libraries": _lib_versions(), "artifacts": []}
            if obj is not None:
                joblib.dump(obj, folder / "model.joblib", compress=3)
            if holdout is not None:
                holdout.to_parquet(folder / "holdout.parquet", index=False)
            for name, df in (artifacts or {}).items():
                df.to_parquet(folder / f"{name}.parquet", index=False)
                meta["artifacts"].append(name)
            self._write_meta(vid, meta)
            return meta

    def _write_meta(self, vid: str, meta: dict[str, Any]) -> None:
        (self._dir(vid) / "meta.json").write_text(json.dumps(jsonable(meta), ensure_ascii=False, indent=2),
                                                  encoding="utf-8")

    def get(self, version_id: str) -> dict[str, Any]:
        path = self._dir(version_id) / "meta.json"
        if not path.exists():
            raise KeyError(version_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list(self, project_id: Optional[str] = None) -> list[dict[str, Any]]:
        out = []
        for p in self.root.glob("*/meta.json"):
            try:
                m = json.loads(p.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            if project_id is None or m.get("project_id") == project_id:
                out.append(m)
        return sorted(out, key=lambda m: (m.get("project_id", ""), -int(m.get("version", 0))))

    def load(self, version_id: str) -> Any:
        if version_id not in self._cache:
            path = self._dir(version_id) / "model.joblib"
            if not path.exists():
                raise KeyError(f"Modelo sem objeto treinado: {version_id}")
            self._cache[version_id] = joblib.load(path)
        return self._cache[version_id]

    def holdout(self, version_id: str) -> pd.DataFrame:
        path = self._dir(version_id) / "holdout.parquet"
        if not path.exists():
            raise KeyError(f"Modelo sem conjunto de teste guardado: {version_id}")
        return pd.read_parquet(path)

    def artifact(self, version_id: str, name: str) -> pd.DataFrame:
        path = self._dir(version_id) / f"{name}.parquet"
        if not path.exists():
            raise KeyError(f"Artefacto inexistente: {name}")
        return pd.read_parquet(path)

    def update(self, version_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            meta = self.get(version_id)
            meta.update(changes)
            self._write_meta(version_id, meta)
            return meta

    def set_champion(self, project_id: str, version_id: str) -> None:
        for m in self.list(project_id):
            if m.get("is_champion") != (m["id"] == version_id):
                self.update(m["id"], is_champion=m["id"] == version_id)

    def promote(self, version_id: str) -> dict[str, Any]:
        meta = self.get(version_id)
        for m in self.list(meta["project_id"]):
            if m["id"] != version_id and m.get("stage") == "produção":
                self.update(m["id"], stage="arquivado", archived_at=now_iso())
        return self.update(version_id, stage="produção", promoted_at=now_iso())

    def delete(self, version_id: str) -> None:
        self._cache.pop(version_id, None)
        shutil.rmtree(self._dir(version_id), ignore_errors=True)

    def delete_project(self, project_id: str) -> None:
        for m in self.list(project_id):
            self.delete(m["id"])
