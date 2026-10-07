"""Реальные HTTP-проверки V2 и сравнение с исходным маршрутом инференса."""

import argparse
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from src.storage import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--output", type=Path, default=Path(".artifacts/v2-smoke.json"))
    args = parser.parse_args()
    report: dict[str, Any] = {"checked_at": datetime.now(UTC).isoformat(), "checks": []}
    with httpx.Client(base_url=args.url, timeout=30) as client:
        for path in [
            "/v2",
            "/v2/health/live",
            "/v2/health/ready",
            "/v2/models/ecom",
            "/v2/models/ecom/ready",
            "/v2/models/ecom/infer",
        ]:
            result = client.get(path)
            result.raise_for_status()
            report["checks"].append({"path": path, "status": result.status_code})
        old = client.get("/predict_purchase?itemid=356475&hour=14&weekday=3")
        old.raise_for_status()
        expected = old.json()["purchase_probability"]
        payload = {
            "id": "smoke-v2",
            "inputs": [
                {
                    "name": "features",
                    "datatype": "INT64",
                    "shape": [2, 3],
                    "data": [356475, 14, 3, 356475, 14, 3],
                }
            ],
        }
        result = client.post("/v2/models/ecom/infer", json=payload)
        result.raise_for_status()
        response = result.json()
        assert response["outputs"][0]["shape"] == [2, 1]
        assert response["outputs"][0]["data"] == [expected, expected]
        assert response["id"] == "smoke-v2"
        assert response["model_version"] == old.json()["model_version"]
        report["prediction"] = response
        report["checks"].append({"path": "POST infer + parity", "status": 200})
        for path, status in [
            ("/v2/models/absent/infer", 404),
            ("/v2/models/ecom/infer?itemid=999999999", 404),
            ("/v2/models/ecom/infer?hour=24", 400),
        ]:
            result = client.get(path)
            assert result.status_code == status and "error" in result.json()
            report["checks"].append({"path": path, "status": result.status_code})
        payload["inputs"][0]["shape"] = [1, 3]  # type: ignore[index]
        result = client.post("/v2/models/ecom/infer", json=payload)
        assert result.status_code == 400 and "error" in result.json()
        report["checks"].append({"path": "POST invalid shape", "status": 400})
    write_json(args.output, report)
    print("V2 проверен:", len(report["checks"]), "сценариев")


if __name__ == "__main__":
    main()
