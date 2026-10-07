"""S3 raw → проверенная версия processed; XCom содержит только ссылки."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from airflow.decorators import dag, task
from airflow.hooks.base import BaseHook
from airflow.models.param import Param


@dag(
    dag_id="preprocessing_data",
    start_date=datetime(2025, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(seconds=30)},
    params={"raw_manifest": Param("", type="string", minLength=1)},
    tags=["ecom", "s3"],
)
def preprocessing_data() -> None:
    @task
    def prepare_from_s3(**context: object) -> str:
        from airflow.operators.python import get_current_context

        from src.data import prepare
        from src.storage import PREFIX, download_manifest, upload_directory

        connection = BaseHook.get_connection("ecom_s3")
        extra = connection.extra_dejson
        os.environ.update(
            {
                "AWS_ACCESS_KEY_ID": connection.login or "",
                "AWS_SECRET_ACCESS_KEY": connection.password or "",
                "S3_ENDPOINT_URL": extra["endpoint_url"],
                "S3_BUCKET": extra["bucket"],
                "AWS_DEFAULT_REGION": "ru-central1",
            }
        )
        key = get_current_context()["params"]["raw_manifest"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            download_manifest(key, root / "raw")
            manifest = prepare(root / "raw", root / "processed")
            result = upload_directory(
                root / "processed", f"{PREFIX}/processed_data/{manifest['version']}"
            )
            print("Обработка завершена:", manifest["splits"])
            return result

    prepare_from_s3()


preprocessing_data()
