"""Контракт API без S3, ClearML и настоящей модели."""

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


class FakePredictor:
    version = "unit-test"

    def predict(self, itemid: int, hour: int, weekday: int) -> float:
        if itemid != 356475:
            raise KeyError(itemid)
        return 0.125


def test_health_and_prediction() -> None:
    with TestClient(create_app(FakePredictor())) as client:
        assert client.get("/health").json()["status"] == "ok"
        result = client.get("/predict_purchase?itemid=356475&hour=14&weekday=3")
        assert result.status_code == 200
        assert result.json() == {
            "itemid": 356475,
            "purchase_probability": 0.125,
            "model_version": "unit-test",
        }
        assert client.get("/docs").status_code == 200
        metrics = client.get("/metrics").text
        assert "purchase_probability_count 1.0" in metrics
        assert (
            'http_requests_total{path="/predict_purchase",status="200"} 1.0' in metrics
        )


@pytest.mark.parametrize(
    "query",
    [
        "itemid=-1&hour=2&weekday=1",
        "itemid=x&hour=2&weekday=1",
        "itemid=1&hour=24&weekday=1",
        "itemid=1&hour=1&weekday=7",
        "itemid=1&weekday=1",
    ],
)
def test_invalid_request(query: str) -> None:
    with TestClient(create_app(FakePredictor())) as client:
        assert client.get("/predict_purchase?" + query).status_code == 422


def test_unknown_item() -> None:
    with TestClient(create_app(FakePredictor())) as client:
        assert (
            client.get("/predict_purchase?itemid=0&hour=1&weekday=1").status_code == 404
        )


def test_missing_model(tmp_path: object, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_DIR", str(tmp_path))
    with TestClient(create_app()) as client:
        assert client.get("/health").status_code == 503
        assert (
            client.get("/predict_purchase?itemid=356475&hour=1&weekday=1").status_code
            == 503
        )
        assert "model_ready 0.0" in client.get("/metrics").text
