"""Локальное воспроизводимое сравнение трёх конфигураций CatBoost."""

import argparse
from pathlib import Path

from src.storage import PREFIX, upload_directory
from src.training import CONFIGS, fit_candidate, select_best


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--processed", type=Path, default=Path(".artifacts/processed"))
    parser.add_argument(
        "--experiments", type=Path, default=Path(".artifacts/experiments")
    )
    parser.add_argument("--output", type=Path, default=Path(".artifacts/model"))
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    for index in range(len(CONFIGS)):
        print(
            fit_candidate(args.processed, args.experiments / str(index), index),
            flush=True,
        )
    result = select_best(args.processed, args.experiments, args.output)
    if args.upload:
        print(upload_directory(args.output, f"{PREFIX}/models/{result['version']}"))
    print(result["test"])


if __name__ == "__main__":
    main()
