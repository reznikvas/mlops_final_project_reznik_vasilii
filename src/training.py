"""Сравнение CatBoost по validation AP и оценка победителя на test."""

import importlib.metadata
import json
import pickle
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss

from src.features import FEATURES, feature_matrix
from src.storage import PREFIX, sha256, write_json

CONFIGS = [
    {"depth": 4, "iterations": 200, "learning_rate": 0.08},
    {"depth": 5, "iterations": 300, "learning_rate": 0.06},
    {"depth": 6, "iterations": 250, "learning_rate": 0.08},
]
SEED = 42


def evaluate(y: Any, probability: Any) -> dict[str, float]:
    return {
        "average_precision": float(average_precision_score(y, probability)),
        "log_loss": float(log_loss(y, probability)),
        "brier": float(brier_score_loss(y, probability)),
        "prevalence": float(np.mean(y)),
    }


def fit_candidate(processed: Path, output: Path, index: int) -> dict[str, Any]:
    manifest = json.loads((processed / "manifest.json").read_text())
    for name, metadata in manifest["files"].items():
        if sha256(processed / name) != metadata["sha256"]:
            raise ValueError("Нарушена целостность processed")
    frame = pd.read_parquet(processed / "data_for_training.parquet")
    train, validation = (
        frame[frame.split == split] for split in ["train", "validation"]
    )
    params = {
        **CONFIGS[index],
        "random_seed": SEED,
        "loss_function": "Logloss",
        "thread_count": 4,
        "verbose": False,
        "allow_writing_files": False,
    }
    model = CatBoostClassifier(**params)
    model.fit(feature_matrix(train), train.target)
    metrics = evaluate(
        validation.target, model.predict_proba(feature_matrix(validation))[:, 1]
    )
    output.mkdir(parents=True, exist_ok=True)
    with (output / "ranker.pkl").open("wb") as stream:
        pickle.dump(model, stream)
    result = {
        "index": index,
        "params": params,
        "validation": metrics,
        "processed_version": manifest["version"],
        "model_sha256": sha256(output / "ranker.pkl"),
    }
    write_json(output / "result.json", result)
    return result


def select_best(processed: Path, experiments: Path, output: Path) -> dict[str, Any]:
    results = [
        json.loads((experiments / str(i) / "result.json").read_text())
        for i in range(len(CONFIGS))
    ]
    winner = max(results, key=lambda r: r["validation"]["average_precision"])
    source = experiments / str(winner["index"]) / "ranker.pkl"
    if sha256(source) != winner["model_sha256"]:
        raise ValueError("Нарушена целостность модели")
    with source.open("rb") as stream:
        # Только проверенный артефакт из доверенного проектного S3.
        model = pickle.load(stream)
    frame = pd.read_parquet(processed / "data_for_training.parquet")
    test = frame[frame.split == "test"]
    test_metrics = evaluate(
        test.target, model.predict_proba(feature_matrix(test))[:, 1]
    )
    train_rate = float(frame.loc[frame.split == "train", "target"].mean())
    baseline = evaluate(test.target, np.full(len(test), train_rate))
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, output / "ranker.pkl")
    shutil.copyfile(
        processed / "item_features.parquet", output / "item_features.parquet"
    )
    data_manifest = json.loads((processed / "manifest.json").read_text())
    version = data_manifest["version"] + "-" + sha256(source)[:12]
    manifest = {
        "version": version,
        "schema_version": "1",
        "features": FEATURES,
        "processed_version": data_manifest["version"],
        "processed_manifest_key": (
            f"{PREFIX}/processed_data/{data_manifest['version']}/manifest.json"
        ),
        "processed_manifest_sha256": sha256(processed / "manifest.json"),
        "snapshot_timestamp": data_manifest["snapshot_timestamp"],
        "splits": data_manifest["splits"],
        "selection_metric": "average_precision",
        "winner": winner,
        "experiments": results,
        "test": test_metrics,
        "test_constant_baseline": baseline,
        "seed": SEED,
        "training_code_sha256": sha256(Path(__file__)),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ["catboost", "numpy", "pandas", "scikit-learn", "pyarrow"]
        },
        "files": {
            name: {"sha256": sha256(output / name)}
            for name in ["ranker.pkl", "item_features.parquet"]
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest
