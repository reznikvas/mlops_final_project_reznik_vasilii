"""Контролируемая остановка API: firing → запуск → resolved с восстановлением."""

import argparse
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.storage import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-config", type=Path, default=Path(".secrets/ssh_config"))
    parser.add_argument("--host", default="course-vm")
    parser.add_argument("--prometheus", default="http://127.0.0.1:19090")
    parser.add_argument("--api", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    ssh = ["ssh", "-F", str(args.ssh_config), args.host]
    report: dict[str, Any] = {"started_at": datetime.now(UTC).isoformat()}

    def wait_alert(expected: bool) -> list[Any]:
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            response = httpx.get(args.prometheus + "/api/v1/alerts", timeout=10)
            response.raise_for_status()
            alerts = response.json()["data"]["alerts"]
            firing = any(
                a["labels"]["alertname"] == "EcomUnavailable" and a["state"] == "firing"
                for a in alerts
            )
            if firing == expected:
                return list(alerts)
            time.sleep(5)
        raise AssertionError("Истекло время ожидания состояния алерта")

    httpx.get(args.api + "/health", timeout=10).raise_for_status()
    wait_alert(False)
    try:
        subprocess.run([*ssh, "sudo docker stop ecom-api"], check=True, timeout=40)
        report["firing"] = wait_alert(True)
        report["fired_at"] = datetime.now(UTC).isoformat()
    finally:
        subprocess.run([*ssh, "sudo docker start ecom-api"], check=True, timeout=40)
    for _ in range(30):
        try:
            response = httpx.get(args.api + "/health", timeout=5)
            if response.status_code == 200:
                report["health_after"] = response.json()
                break
        except httpx.HTTPError:
            pass
        time.sleep(2)
    else:
        raise AssertionError("API не восстановился")
    report["resolved"] = wait_alert(False)
    report["resolved_at"] = datetime.now(UTC).isoformat()
    write_json(Path("docs/evidence/alert-recovery.json"), report)
    print("Проверено: остановка API → firing → восстановление health=200 → resolved")


if __name__ == "__main__":
    main()
