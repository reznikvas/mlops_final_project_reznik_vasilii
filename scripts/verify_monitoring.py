"""Реальный трафик и проверка Prometheus, Loki и Grafana через туннели."""

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.storage import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:18000")
    parser.add_argument("--prometheus", default="http://127.0.0.1:19090")
    parser.add_argument("--loki", default="http://127.0.0.1:13100")
    parser.add_argument("--grafana", default="http://127.0.0.1:13000")
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/evidence/monitoring.json")
    )
    args = parser.parse_args()
    report: dict[str, Any] = {"checked_at": datetime.now(UTC).isoformat()}
    with httpx.Client(timeout=30) as client:
        for index in range(120):
            response = client.get(
                args.api + "/predict_purchase",
                params={"itemid": 356475, "hour": index % 24, "weekday": index % 7},
            )
            response.raise_for_status()
            time.sleep(0.1)
        client.get(args.api + "/predict_purchase?itemid=-1&hour=14&weekday=3")
        time.sleep(15)
        report["prometheus"] = {}
        for query in [
            'up{job="ecom"}',
            "model_ready",
            "purchase_probability_count",
            "sum(rate(http_requests_total[2m]))",
            "sum(rate(http_request_duration_seconds_count[2m]))",
        ]:
            response = client.get(
                args.prometheus + "/api/v1/query", params={"query": query}
            )
            response.raise_for_status()
            results = response.json()["data"]["result"]
            assert results and float(results[0]["value"][1]) > 0, query
            report["prometheus"][query] = results
        response = client.get(
            args.loki + "/loki/api/v1/query_range",
            params={
                "query": '{job="ecom"} |= "prediction"',
                "limit": 10,
                "since": "15m",
            },
        )
        response.raise_for_status()
        logs = response.json()["data"]["result"]
        assert logs, "В Loki нет реальных логов прогнозов"
        report["loki"] = logs
        response = client.get(
            args.grafana + "/api/dashboards/uid/ecom",
            auth=("admin", args.password_file.read_text().strip()),
        )
        response.raise_for_status()
        report["grafana"] = {
            "uid": response.json()["dashboard"]["uid"],
            "panels": len(response.json()["dashboard"]["panels"]),
        }
    write_json(args.output, report)
    print("Prometheus, Loki и Grafana проверены на реальном трафике")


if __name__ == "__main__":
    main()
