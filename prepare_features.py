"""Подготовка признаков: локальные CSV или manifest исходных данных S3."""

import argparse
from pathlib import Path

from src.data import prepare
from src.storage import PREFIX, download_manifest, upload_directory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, default=Path(".artifacts/raw"))
    parser.add_argument("--output", type=Path, default=Path(".artifacts/processed"))
    parser.add_argument("--raw-manifest")
    parser.add_argument("--upload", action="store_true")
    args = parser.parse_args()
    if args.raw_manifest:
        download_manifest(args.raw_manifest, args.raw)
    manifest = prepare(args.raw, args.output)
    if args.upload:
        print(
            upload_directory(
                args.output, f"{PREFIX}/processed_data/{manifest['version']}"
            )
        )
    else:
        print(manifest["version"])


if __name__ == "__main__":
    main()
