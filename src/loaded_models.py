"""Однократная загрузка согласованной пары модель/lookup."""

import json
import math
import os
import pickle
from pathlib import Path
from typing import Protocol

import pandas as pd

from src.features import FEATURES, feature_matrix
from src.storage import sha256


class Predictor(Protocol):
    version: str

    def predict(self, itemid: int, hour: int, weekday: int) -> float: ...


class ModelBundle:
    def __init__(self, directory: Path) -> None:
        manifest = json.loads((directory / "manifest.json").read_text())
        if manifest["features"] != FEATURES or manifest["schema_version"] != "1":
            raise ValueError("Несовместимая схема модели")
        expected = os.getenv("MODEL_VERSION")
        if expected and manifest["version"] != expected:
            raise ValueError("Версия модели не соответствует релизу")
        for name in ["ranker.pkl", "item_features.parquet"]:
            if sha256(directory / name) != manifest["files"][name]["sha256"]:
                raise ValueError("Нарушена целостность артефакта")
        with (directory / "ranker.pkl").open("rb") as stream:
            self.model = pickle.load(stream)
        self.items = pd.read_parquet(directory / "item_features.parquet").set_index(
            "itemid"
        )
        if not self.items.index.is_unique or self.items.empty:
            raise ValueError("Некорректная таблица товаров")
        self.version = str(manifest["version"])

    def predict(self, itemid: int, hour: int, weekday: int) -> float:
        if itemid not in self.items.index:
            raise KeyError(itemid)
        row = self.items.loc[[itemid]].copy()
        row["hour"], row["weekday"] = hour, weekday
        probability = float(self.model.predict_proba(feature_matrix(row))[0, 1])
        if not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError("Некорректная вероятность")
        return probability
