"""Реальная HTTP-проверка контракта; результат без секретов."""

import argparse
from datetime import UTC, datetime
from pathlib import Path

import httpx

from src.storage import write_json


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:32000")
    parser.add_argument(
        "--output", type=Path, default=Path("docs/evidence/local-api.json")
    )
    args = parser.parse_args()
    results = []
    with httpx.Client(base_url=args.url, timeout=30) as client:
        for path, expected in [
            ("/health", 200),
            ("/docs", 200),
            ("/predict_purchase?itemid=356475&hour=14&weekday=3", 200),
            ("/predict_purchase?itemid=999999999&hour=14&weekday=3", 404),
            ("/predict_purchase?itemid=356475&hour=24&weekday=3", 422),
            ("/predict_purchase?itemid=-1&hour=14&weekday=3", 422),
            ("/metrics", 200),
        ]:
            response = client.get(path)
            assert response.status_code == expected, (path, response.status_code)
            result = {"path": path, "status": response.status_code}
            if response.headers.get("content-type", "").startswith("application/json"):
                result["body"] = response.json()
            if path.startswith("/predict_purchase") and expected == 200:
                probability = response.json()["purchase_probability"]
                assert 0 <= probability <= 1
                assert response.json()["model_version"]
            results.append(result)
    write_json(
        args.output, {"checked_at": datetime.now(UTC).isoformat(), "results": results}
    )
    print("HTTP-проверки пройдены:", len(results))


if __name__ == "__main__":
    main()
