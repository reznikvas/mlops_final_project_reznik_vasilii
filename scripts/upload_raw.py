"""Загрузить четыре исходных CSV и manifest, не меняя источники."""

import argparse
import hashlib
import json
from pathlib import Path

from src.data import RAW_FILES
from src.storage import PREFIX, client, sha256


def main() -> None:
    import os

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    files = {
        name: {
            "sha256": sha256(args.directory / name),
            "bytes": (args.directory / name).stat().st_size,
        }
        for name in RAW_FILES
    }
    version = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[
        :16
    ]
    key = f"{PREFIX}/raw_data/{version}"
    s3 = client()
    bucket = os.environ["S3_BUCKET"]
    for name in RAW_FILES:
        s3.upload_file(str(args.directory / name), bucket, f"{key}/{name}")
        print("Загружен", name, flush=True)
    manifest = {"version": version, "schema_version": "1", "files": files}
    s3.put_object(
        Bucket=bucket,
        Key=f"{key}/manifest.json",
        Body=json.dumps(manifest).encode(),
        ContentType="application/json",
    )
    print(f"{key}/manifest.json")


if __name__ == "__main__":
    main()
