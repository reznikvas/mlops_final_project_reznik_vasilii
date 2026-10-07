"""Версионированные артефакты S3 с проверкой SHA256."""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import boto3

PREFIX = "Reznik_Vasilii_project"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=os.getenv("S3_ENDPOINT_URL", "https://storage.yandexcloud.net"),
        region_name=os.getenv("AWS_DEFAULT_REGION", "ru-central1"),
    )


def upload_directory(directory: Path, key: str) -> str:
    """Manifest загружается последним — признак завершённой публикации."""
    s3 = client()
    bucket = os.environ["S3_BUCKET"]
    files = sorted(p for p in directory.iterdir() if p.is_file())
    for path in sorted(files, key=lambda p: p.name == "manifest.json"):
        s3.upload_file(str(path), bucket, f"{key}/{path.name}")
    return f"{key}/manifest.json"


def download_manifest(key: str, directory: Path) -> dict[str, Any]:
    s3 = client()
    bucket = os.environ["S3_BUCKET"]
    manifest = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    directory.mkdir(parents=True, exist_ok=True)
    for name, metadata in manifest["files"].items():
        if Path(name).name != name:
            raise ValueError("Недопустимое имя артефакта")
        target = directory / name
        if not target.exists() or sha256(target) != metadata["sha256"]:
            temporary = target.with_suffix(target.suffix + ".tmp")
            s3.download_file(bucket, f"{key.rsplit('/', 1)[0]}/{name}", str(temporary))
            if sha256(temporary) != metadata["sha256"]:
                temporary.unlink()
                raise ValueError("Контрольная сумма артефакта не совпала")
            temporary.replace(target)
    write_json(directory / "manifest.json", manifest)
    return dict(manifest)
