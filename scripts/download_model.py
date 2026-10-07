"""Загрузить артефакты выбранного релиза из S3."""

import os
from pathlib import Path

from src.loaded_models import ModelBundle
from src.storage import download_manifest


def main() -> None:
    directory = Path(os.environ.get("MODEL_DIR", "/models"))
    download_manifest(os.environ["MODEL_MANIFEST_KEY"], directory)
    bundle = ModelBundle(directory)
    print("Модель проверена:", bundle.version)


if __name__ == "__main__":
    main()
