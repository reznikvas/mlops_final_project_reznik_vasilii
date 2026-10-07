"""Контракт V2, границы тензора и совместимость GET без внешних сервисов."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.main import create_app


class Predictor:
    version = "test-v2"

    def predict(self, itemid: int, hour: int, weekday: int) -> float:
        if itemid != 356475:
            raise KeyError(itemid)
        return 0.125


def payload() -> dict[str, Any]:
    return {
        "id": "request-42",
        "inputs": [
            {
                "name": "features",
                "datatype": "INT64",
                "shape": [2, 3],
                "data": [356475, 14, 3, 356475, 0, 6],
            }
        ],
    }


def test_v2_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MODEL_NAME", "ecom")
    with TestClient(create_app(Predictor(), load_model=False)) as client:
        for path in [
            "/v2",
            "/v2/health/live",
            "/v2/health/ready",
            "/v2/models/ecom/ready",
        ]:
            assert client.get(path).status_code == 200
        metadata = client.get("/v2/models/ecom").json()
        assert metadata["versions"] == ["test-v2"]
        assert metadata["inputs"][0]["shape"] == [-1, 3]
        response = client.post("/v2/models/ecom/infer", json=payload())
        assert response.status_code == 200
        assert response.json() == {
            "model_name": "ecom",
            "model_version": "test-v2",
            "id": "request-42",
            "outputs": [
                {
                    "name": "purchase_probability",
                    "shape": [2, 1],
                    "datatype": "FP64",
                    "data": [0.125, 0.125],
                }
            ],
        }
        result = client.get("/v2/models/ecom/infer")
        assert result.status_code == 200 and "id" not in result.json()
        assert result.json()["outputs"][0]["data"] == [0.125]
        assert "purchase_probability_count 3.0" in client.get("/metrics").text
        assert client.get("/v2/models/absent/infer").status_code == 404
        unknown = client.get("/v2/models/ecom/infer?itemid=1")
        assert unknown.status_code == 404 and "error" in unknown.json()
        invalid = client.get("/v2/models/ecom/infer?hour=24")
        assert invalid.status_code == 400 and "error" in invalid.json()


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("shape", [1, 3]),
        ("shape", [2, 2]),
        ("shape", [0, 3]),
        ("shape", [True, 3]),
        ("shape", [257, 3]),
        ("data", [356475, 24, 0, 356475, 0, 0]),
        ("data", [356475, 0, 7, 356475, 0, 0]),
        ("data", [-1, 0, 0, 356475, 0, 0]),
        ("data", [True, 0, 0, 356475, 0, 0]),
        ("data", [356475.0, 0, 0, 356475, 0, 0]),
        ("data", [2**63, 0, 0, 356475, 0, 0]),
        ("datatype", "FP32"),
        ("name", "other"),
    ],
)
def test_invalid_tensor(key: str, value: Any) -> None:
    request = payload()
    request["inputs"][0][key] = value
    with TestClient(create_app(Predictor(), load_model=False)) as client:
        result = client.post("/v2/models/ecom/infer", json=request)
        assert result.status_code == 400
        assert "error" in result.json()


def test_outputs_and_input_count() -> None:
    with TestClient(create_app(Predictor(), load_model=False)) as client:
        request = payload()
        request["outputs"] = [{"name": "unknown"}]
        assert client.post("/v2/models/ecom/infer", json=request).status_code == 400
        request["outputs"] = [{"name": "purchase_probability"}]
        assert client.post("/v2/models/ecom/infer", json=request).status_code == 200
        request["inputs"] *= 2
        assert client.post("/v2/models/ecom/infer", json=request).status_code == 400


def test_v2_not_ready() -> None:
    with TestClient(create_app(load_model=False)) as client:
        assert client.get("/v2/health/live").status_code == 200
        for path in [
            "/v2/health/ready",
            "/v2/models/ecom/ready",
            "/v2/models/ecom/infer",
        ]:
            response = client.get(path)
            assert response.status_code == 503 and "error" in response.json()
        assert client.post("/v2/models/ecom/infer", json=payload()).status_code == 503
