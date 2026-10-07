"""PR-кривая и калибровка финального победителя на отложенном test."""

import argparse
import json
import pickle
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import precision_recall_curve  # noqa: E402

from src.features import feature_matrix  # noqa: E402
from src.storage import sha256  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--processed", type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads((args.bundle / "manifest.json").read_text())
    assert (
        sha256(args.bundle / "ranker.pkl") == manifest["files"]["ranker.pkl"]["sha256"]
    )
    with (args.bundle / "ranker.pkl").open("rb") as stream:
        model = pickle.load(stream)
    frame = pd.read_parquet(args.processed / "data_for_training.parquet")
    test = frame[frame.split == "test"]
    probability = model.predict_proba(feature_matrix(test))[:, 1]
    precision, recall, _ = precision_recall_curve(test.target, probability)
    observed, predicted = calibration_curve(
        test.target, probability, n_bins=10, strategy="quantile"
    )
    figure, axes = plt.subplots(1, 2, figsize=(11, 4))
    axes[0].plot(
        recall, precision, label=f"AP = {manifest['test']['average_precision']:.4f}"
    )
    axes[0].axhline(
        test.target.mean(), color="gray", linestyle="--", label="Доля покупок"
    )
    axes[0].set(xlabel="Полнота", ylabel="Точность", title="PR-кривая: отложенный test")
    axes[0].legend()
    upper = max(max(observed), max(predicted)) * 1.1
    axes[1].plot(
        [0, upper], [0, upper], "--", color="gray", label="Идеальная калибровка"
    )
    axes[1].plot(predicted, observed, "o-", label="10 квантильных интервалов")
    axes[1].set(
        xlabel="Средняя прогнозируемая вероятность",
        ylabel="Доля реальных покупок",
        title="Калибровка; без подстройки по test",
    )
    axes[1].legend()
    figure.tight_layout()
    figure.savefig("docs/evidence/offline-quality.png", dpi=150)
    plt.close(figure)


if __name__ == "__main__":
    main()
