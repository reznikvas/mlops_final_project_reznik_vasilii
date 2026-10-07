"""Деплой фиксированной пары image/model и Helm-мониторинга в namespace."""

import base64
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx


def kubectl(*args: str, text: str | None = None) -> str:
    return subprocess.check_output(
        ["kubectl", "--namespace", os.environ["KUBE_NAMESPACE"], *args],
        input=text,
        text=True,
        timeout=360,
    )


def secret(name: str, values: dict[str, str]) -> None:
    payload: dict[str, Any] = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {"name": name},
        "type": "Opaque",
        "data": {k: base64.b64encode(v.encode()).decode() for k, v in values.items()},
    }
    kubectl("apply", "--server-side", "-f", "-", text=json.dumps(payload))


def main() -> None:
    image = os.environ["APP_IMAGE"]
    if not re.fullmatch(r"[a-zA-Z0-9./:_-]+@sha256:[a-f0-9]{64}", image):
        raise ValueError("Требуется образ с неизменным sha256 digest")
    replacements = {"APP_IMAGE": image}
    for key in ["MODEL_VERSION", "MODEL_MANIFEST_KEY"]:
        value = os.environ[key]
        if not re.fullmatch(r"[a-zA-Z0-9/_.-]+", value):
            raise ValueError("Недопустимый идентификатор артефакта")
        replacements[key] = value
    namespace = os.environ["KUBE_NAMESPACE"]
    if not re.fullmatch(r"[a-z0-9-]+", namespace):
        raise ValueError("Недопустимый namespace")
    secret(
        "ecom-s3",
        {
            key: os.environ[key]
            for key in [
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "S3_BUCKET",
                "S3_ENDPOINT_URL",
                "AWS_DEFAULT_REGION",
            ]
        },
    )
    secret("ecom-grafana", {"password": os.environ["GRAFANA_PASSWORD"]})
    for file in ["deployment.yml", "service.yml"]:
        manifest = (Path("mlops/deploy/k8s") / file).read_text()
        for key, value in replacements.items():
            manifest = manifest.replace("${" + key + "}", value)
        if "${" in manifest:
            raise ValueError("Остались незаполненные параметры манифеста")
        print(kubectl("apply", "-f", "-", text=manifest).strip())
    print(kubectl("rollout", "status", "deployment/ecom", "--timeout=300s").strip())
    subprocess.run(
        [
            "helm",
            "upgrade",
            "--install",
            "ecom-monitoring",
            "mlops/grafana/chart",
            "--namespace",
            namespace,
            "--wait",
            "--timeout",
            "5m",
            "--history-max",
            "3",
        ],
        check=True,
        timeout=330,
    )
    Path(".artifacts").mkdir(exist_ok=True)
    port = int(os.getenv("KUBE_SMOKE_PORT", "28000"))
    with Path(".artifacts/k8s-port-forward.log").open("w") as log:
        forward = subprocess.Popen(
            [
                "kubectl",
                "--namespace",
                namespace,
                "port-forward",
                "service/ecom",
                f"{port}:8000",
            ],
            stdout=log,
            stderr=log,
        )
        try:
            for _ in range(30):
                if forward.poll() is not None:
                    raise RuntimeError("Port-forward завершился до проверки API")
                try:
                    httpx.get(
                        f"http://127.0.0.1:{port}/health", timeout=2
                    ).raise_for_status()
                    break
                except httpx.HTTPError:
                    time.sleep(1)
            else:
                raise RuntimeError("Истекло время ожидания API")
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "scripts.smoke_v2",
                    "--url",
                    f"http://127.0.0.1:{port}",
                    "--output",
                    ".artifacts/k8s-ci-smoke.json",
                ],
                check=True,
                timeout=90,
            )
        finally:
            forward.terminate()
            forward.wait(timeout=10)
    print("Инференс и мониторинг развёрнуты; V2 проверен")


if __name__ == "__main__":
    main()
