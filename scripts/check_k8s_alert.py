"""Остановка Deployment: firing → новый Pod, S3-init → resolved."""

import argparse
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.storage import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus", default="http://127.0.0.1:29090")
    parser.add_argument(
        "--output", type=Path, default=Path("docs/evidence/k8s-recovery.json")
    )
    args = parser.parse_args()
    command = ["kubectl", "--namespace", os.environ["KUBE_NAMESPACE"]]

    def kube(*argv: str) -> str:
        return subprocess.check_output([*command, *argv], text=True, timeout=330)

    def alerts(expected: bool) -> list[Any]:
        deadline = time.monotonic() + 150
        while time.monotonic() < deadline:
            response = httpx.get(args.prometheus + "/api/v1/alerts", timeout=10)
            response.raise_for_status()
            values: list[Any] = response.json()["data"]["alerts"]
            fired = any(
                a["labels"]["alertname"] == "EcomUnavailable" and a["state"] == "firing"
                for a in values
            )
            if fired == expected:
                return values
            time.sleep(5)
        raise AssertionError("Не достигнуто ожидаемое состояние алерта")

    deployment = json.loads(kube("get", "deployment/ecom", "-o", "json"))
    replicas = deployment["spec"]["replicas"]
    if replicas != 1 or deployment["status"].get("availableReplicas") != 1:
        raise ValueError("Проверка требует одну готовую реплику ecom")
    old = json.loads(kube("get", "pods", "-l", "app=ecom", "-o", "json"))["items"][0]
    alerts(False)
    report: dict[str, Any] = {
        "started_at": datetime.now(UTC).isoformat(),
        "old_pod_uid": old["metadata"]["uid"],
    }
    try:
        kube("scale", "deployment/ecom", "--replicas=0")
        report["firing"] = alerts(True)
        report["fired_at"] = datetime.now(UTC).isoformat()
    finally:
        kube("scale", "deployment/ecom", f"--replicas={replicas}")
        kube("rollout", "status", "deployment/ecom", "--timeout=300s")
    report["resolved"] = alerts(False)
    report["resolved_at"] = datetime.now(UTC).isoformat()
    pod = json.loads(kube("get", "pods", "-l", "app=ecom", "-o", "json"))["items"][0]
    report["new_pod_uid"] = pod["metadata"]["uid"]
    assert report["new_pod_uid"] != report["old_pod_uid"]
    init = pod["status"]["initContainerStatuses"][0]
    assert init["state"]["terminated"]["exitCode"] == 0
    report["init_exit_code"] = 0
    report["init_log"] = kube(
        "logs", pod["metadata"]["name"], "-c", "model-init"
    ).strip()
    report["image"] = pod["spec"]["containers"][0]["image"]
    write_json(args.output, report)
    print("Kubernetes: firing → новый Pod и загрузка S3 → resolved")


if __name__ == "__main__":
    main()
