"""FastAPI: готовность, вероятность, метрики и структурированные логи."""

import json
import logging
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

from src.loaded_models import ModelBundle, Predictor
from src.schema import PurchaseRequest, PurchaseResponse
from src.v2 import install_v2

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("ecom")


def create_app(predictor: Predictor | None = None, load_model: bool = True) -> FastAPI:
    registry = CollectorRegistry()
    requests = Counter(
        "http_requests_total", "Запросы", ["path", "status"], registry=registry
    )
    latency = Histogram(
        "http_request_duration_seconds", "Задержка", ["path"], registry=registry
    )
    scores = Histogram(
        "purchase_probability",
        "Распределение вероятности",
        buckets=(0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.25, 0.5, 0.75, 1),
        registry=registry,
    )
    ready = Gauge("model_ready", "Готовность модели", registry=registry)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.predictor = predictor
        if load_model and predictor is None:
            try:
                app.state.predictor = ModelBundle(
                    Path(os.getenv("MODEL_DIR", ".artifacts/model"))
                )
            except Exception as exc:
                logger.error(
                    json.dumps(
                        {"event": "model_load_failed", "type": type(exc).__name__}
                    )
                )
        ready.set(app.state.predictor is not None)
        yield
        app.state.predictor = None
        ready.set(0)

    app = FastAPI(title="Вероятность покупки", version="1.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def observe(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            path = route.path if route else "unmatched"
            if path != "/metrics":
                requests.labels(path, str(status)).inc()
                latency.labels(path).observe(time.perf_counter() - started)
                if status >= 400:
                    logger.warning(
                        json.dumps(
                            {"event": "http_error", "path": path, "status": status}
                        )
                    )

    @app.get("/health")
    def health() -> dict[str, str]:
        if app.state.predictor is None:
            raise HTTPException(503, "Модель не готова")
        return {"status": "ok", "model_version": app.state.predictor.version}

    def predict(query: PurchaseRequest) -> PurchaseResponse:
        model = app.state.predictor
        if model is None:
            raise HTTPException(503, "Модель не готова")
        try:
            probability = model.predict(query.itemid, query.hour, query.weekday)
        except KeyError:
            raise HTTPException(404, "Товар отсутствует в версии каталога") from None
        except Exception as exc:
            logger.error(
                json.dumps({"event": "prediction_failed", "type": type(exc).__name__})
            )
            raise HTTPException(503, "Ошибка модели") from None
        scores.observe(probability)
        logger.info(
            json.dumps(
                {
                    "event": "prediction",
                    "itemid": query.itemid,
                    "probability": probability,
                    "model_version": model.version,
                }
            )
        )
        return PurchaseResponse(
            itemid=query.itemid,
            purchase_probability=probability,
            model_version=model.version,
        )

    @app.get("/predict_purchase", response_model=PurchaseResponse)
    def predict_purchase(
        query: Annotated[PurchaseRequest, Query()],
    ) -> PurchaseResponse:
        return predict(query)

    install_v2(app, predict)

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
