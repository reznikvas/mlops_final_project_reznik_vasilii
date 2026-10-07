"""Подготовка полного RetailRocket с историческими признаками."""

import hashlib
import importlib.metadata
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.features import FEATURES, SCHEMA_VERSION
from src.storage import sha256, write_json

RAW_FILES = [
    "events.csv",
    "category_tree.csv",
    "item_properties_part1.csv",
    "item_properties_part2.csv",
]
DAY = 24 * 60 * 60 * 1000


def require(condition: bool | np.bool_, message: str) -> None:
    if not condition:
        raise ValueError(message)


def make_target(views: pd.DataFrame, purchases: pd.DataFrame) -> pd.DataFrame:
    """Один просмотр — одна строка; ближайшая строго последующая покупка."""
    joined = pd.merge_asof(
        views.sort_values(["timestamp", "visitorid", "itemid"], kind="stable"),
        purchases.rename(columns={"timestamp": "purchase_time"}).sort_values(
            "purchase_time"
        ),
        left_on="timestamp",
        right_on="purchase_time",
        by=["visitorid", "itemid"],
        direction="forward",
        allow_exact_matches=False,
        tolerance=DAY,
    )
    joined["target"] = joined["purchase_time"].notna().astype("int8")
    return joined.drop(columns="purchase_time")


def prepare(raw: Path, output: Path) -> dict[str, Any]:
    sources = {name: {"sha256": sha256(raw / name)} for name in RAW_FILES}
    recipe = {
        "schema": SCHEMA_VERSION,
        "history": 0.2,
        "train_end": 0.6,
        "validation_end": 0.8,
        "window_hours": 24,
        "code_sha256": sha256(Path(__file__)),
        "features_code_sha256": sha256(Path(__file__).with_name("features.py")),
        "versions": {
            name: importlib.metadata.version(name)
            for name in ["pandas", "numpy", "pyarrow"]
        },
    }
    version = hashlib.sha256(
        json.dumps([sources, recipe], sort_keys=True).encode()
    ).hexdigest()[:16]
    output.mkdir(parents=True, exist_ok=True)
    events = pd.read_csv(raw / "events.csv")
    require(
        set(events.columns)
        == {"timestamp", "visitorid", "event", "itemid", "transactionid"},
        "Неверная схема events",
    )
    require(
        not events[["timestamp", "visitorid", "itemid", "event"]].isna().any().any(),
        "Пустые обязательные поля events",
    )
    require(
        events.event.isin(["view", "addtocart", "transaction"]).all(),
        "Неизвестный тип события",
    )
    for col in ["timestamp", "visitorid", "itemid"]:
        require((events[col] >= 0).all(), f"Отрицательные значения {col}")
    require(
        events.loc[events.event == "transaction", "transactionid"].notna().all(),
        "Покупка без transactionid",
    )
    duplicates = int(events.duplicated().sum())
    events = events.drop_duplicates()
    start, end = int(events.timestamp.min()), int(events.timestamp.max())
    snapshot = int(start + 0.2 * (end - start))
    train_end = int(start + 0.6 * (end - start))
    val_end = int(start + 0.8 * (end - start))
    history = events[events.timestamp < snapshot]
    counts = history.groupby(["itemid", "event"]).size().unstack(fill_value=0)
    lookup = counts.reindex(columns=["view", "transaction"], fill_value=0)
    lookup = lookup.rename(columns={"view": "views", "transaction": "purchases"})
    lookup["ctr"] = lookup.purchases / lookup.views.clip(lower=1)
    category = pd.read_csv(raw / "category_tree.csv")
    require(set(category.columns) == {"categoryid", "parentid"}, "Схема категорий")
    require(category.categoryid.is_unique, "Повторные categoryid")
    require(category.categoryid.notna().all(), "Пустой categoryid")
    parts = []
    property_rows = {}
    for name in RAW_FILES[2:]:
        rows = 0
        for chunk in pd.read_csv(
            raw / name, dtype={"property": str, "value": str}, chunksize=250_000
        ):
            require(
                set(chunk.columns) == {"timestamp", "itemid", "property", "value"},
                "Неверная схема свойств",
            )
            require(not chunk.isna().any().any(), "Пустое свойство")
            rows += len(chunk)
            part = chunk[
                (chunk.timestamp < snapshot)
                & chunk.property.isin(["categoryid", "available"])
            ]
            parts.append(part)
        property_rows[name] = rows
    properties = pd.concat(parts, ignore_index=True)
    properties = properties.sort_values(["timestamp", "value"], kind="stable")
    properties = properties.drop_duplicates(["itemid", "property"], keep="last")
    pivot = properties.pivot(index="itemid", columns="property", values="value")
    lookup = lookup.join(pivot, how="outer")
    lookup[["views", "purchases", "ctr"]] = lookup[
        ["views", "purchases", "ctr"]
    ].fillna(0)
    for name in ["categoryid", "available"]:
        lookup[name] = pd.to_numeric(lookup[name], errors="raise").fillna(-1)
    require(lookup.available.isin([-1, 0, 1]).all(), "Некорректная доступность")
    lookup = lookup.reset_index()
    lookup.to_parquet(output / "item_features.parquet", index=False)
    views = events.loc[
        (events.event == "view")
        & (events.timestamp >= snapshot)
        & (events.timestamp <= end - DAY),
        ["timestamp", "visitorid", "itemid"],
    ].copy()
    purchases = events.loc[
        events.event == "transaction", ["timestamp", "visitorid", "itemid"]
    ]
    frame = make_target(views, purchases)
    unknown = int((~frame.itemid.isin(lookup.itemid)).sum())
    frame = frame.merge(lookup, on="itemid", how="inner", validate="many_to_one")
    dt = pd.to_datetime(frame.timestamp, unit="ms", utc=True)
    frame["hour"], frame["weekday"] = dt.dt.hour, dt.dt.dayofweek
    frame["split"] = np.select(
        [
            frame.timestamp < train_end - DAY,
            (frame.timestamp >= train_end) & (frame.timestamp < val_end - DAY),
            frame.timestamp >= val_end,
        ],
        ["train", "validation", "test"],
        default="purge",
    )
    frame = (
        frame[frame.split != "purge"]
        .sort_values(["timestamp", "visitorid", "itemid"], kind="stable")
        .reset_index(drop=True)
    )
    stats = {}
    for split in ["train", "validation", "test"]:
        part = frame[frame.split == split]
        require(part.target.nunique() == 2, f"Нет двух классов: {split}")
        stats[split] = {
            "rows": len(part),
            "positives": int(part.target.sum()),
            "prevalence": float(part.target.mean()),
            "min_timestamp": int(part.timestamp.min()),
            "max_timestamp": int(part.timestamp.max()),
        }
    require(
        np.isfinite(frame[FEATURES].to_numpy(dtype=float)).all(), "Не конечные признаки"
    )
    frame.to_parquet(output / "data_for_training.parquet", index=False)
    manifest = {
        "version": version,
        "schema_version": SCHEMA_VERSION,
        "sources": sources,
        "recipe": recipe,
        "features": FEATURES,
        "snapshot_timestamp": snapshot,
        "splits": stats,
        "duplicate_events_removed": duplicates,
        "unknown_views_dropped": unknown,
        "property_rows": property_rows,
        "events_rows": len(events),
        "category_rows": len(category),
        "items": len(lookup),
        "files": {
            name: {"sha256": sha256(output / name)}
            for name in ["item_features.parquet", "data_for_training.parquet"]
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest
