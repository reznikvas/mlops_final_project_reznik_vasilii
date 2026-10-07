"""HTTP API V2 и GET-совместимость с контрольным примером задания."""

import os
from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.schema import PurchaseRequest, PurchaseResponse

MAX_BATCH = 256


class Tensor(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["features"]
    shape: list[StrictInt] = Field(min_length=2, max_length=2)
    datatype: Literal["INT64"]
    data: list[Annotated[StrictInt, Field(ge=-(2**63), le=2**63 - 1)]] = Field(
        min_length=3, max_length=MAX_BATCH * 3
    )

    @model_validator(mode="after")
    def validate_shape(self) -> "Tensor":
        if (
            len(self.shape) != 2
            or not 1 <= self.shape[0] <= MAX_BATCH
            or self.shape[1] != 3
            or len(self.data) != self.shape[0] * 3
        ):
            raise ValueError("Ожидается тензор features формы [N, 3], 1 <= N <= 256")
        for offset in range(0, len(self.data), 3):
            PurchaseRequest(
                itemid=self.data[offset],
                hour=self.data[offset + 1],
                weekday=self.data[offset + 2],
            )
        return self


class RequestedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["purchase_probability"]


class InferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str | None = Field(default=None, max_length=128)
    inputs: list[Tensor] = Field(min_length=1, max_length=1)
    outputs: list[RequestedOutput] | None = Field(
        default=None, min_length=1, max_length=1
    )


class OutputTensor(BaseModel):
    name: str = "purchase_probability"
    shape: list[int]
    datatype: str = "FP64"
    data: list[float]


class InferenceResponse(BaseModel):
    model_name: str
    model_version: str
    id: str | None = None
    outputs: list[OutputTensor]


def install_v2(
    app: FastAPI, predict: Callable[[PurchaseRequest], PurchaseResponse]
) -> None:
    name = os.getenv("MODEL_NAME", "ecom")

    def check_model(model_name: str) -> Any:
        if model_name != name:
            raise HTTPException(404, "Модель отсутствует")
        model = app.state.predictor
        if model is None:
            raise HTTPException(503, "Модель не готова")
        return model

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        key = "error" if request.url.path.startswith("/v2/") else "detail"
        return JSONResponse({key: exc.detail}, status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        if request.url.path.startswith("/v2/"):
            return JSONResponse({"error": "Некорректный запрос V2"}, status_code=400)
        from fastapi.exception_handlers import request_validation_exception_handler

        return await request_validation_exception_handler(request, exc)

    @app.get("/v2/health/live")
    def live() -> dict[str, bool]:
        return {"live": True}

    @app.get("/v2/health/ready")
    def ready() -> dict[str, bool]:
        check_model(name)
        return {"ready": True}

    @app.get("/v2")
    def server_metadata() -> dict[str, Any]:
        return {"name": "ecom-purchase", "version": "1.1.0", "extensions": []}

    @app.get("/v2/models/{model_name}/ready")
    def model_ready(model_name: str) -> dict[str, Any]:
        check_model(model_name)
        return {"name": model_name, "ready": True}

    @app.get("/v2/models/{model_name}")
    def metadata(model_name: str) -> dict[str, Any]:
        model = check_model(model_name)
        return {
            "name": model_name,
            "versions": [model.version],
            "platform": "catboost",
            "inputs": [{"name": "features", "datatype": "INT64", "shape": [-1, 3]}],
            "outputs": [
                {
                    "name": "purchase_probability",
                    "datatype": "FP64",
                    "shape": [-1, 1],
                }
            ],
        }

    @app.post(
        "/v2/models/{model_name}/infer",
        response_model=InferenceResponse,
        response_model_exclude_none=True,
    )
    def infer(model_name: str, payload: InferenceRequest) -> InferenceResponse:
        model = check_model(model_name)
        tensor = payload.inputs[0]
        results = []
        for offset in range(0, len(tensor.data), 3):
            query = PurchaseRequest(
                itemid=tensor.data[offset],
                hour=tensor.data[offset + 1],
                weekday=tensor.data[offset + 2],
            )
            results.append(predict(query).purchase_probability)
        return InferenceResponse(
            model_name=model_name,
            model_version=model.version,
            id=payload.id,
            outputs=[OutputTensor(shape=[len(results), 1], data=results)],
        )

    @app.get(
        "/v2/models/{model_name}/infer",
        response_model=InferenceResponse,
        response_model_exclude_none=True,
        summary="GET-совместимость: контрольный пример 356475, 14, 3",
    )
    def infer_get(
        model_name: str,
        itemid: Annotated[int, Query(ge=0)] = 356475,
        hour: Annotated[int, Query(ge=0, le=23)] = 14,
        weekday: Annotated[int, Query(ge=0, le=6)] = 3,
    ) -> InferenceResponse:
        return infer(
            model_name,
            InferenceRequest(
                inputs=[
                    Tensor(
                        name="features",
                        shape=[1, 3],
                        datatype="INT64",
                        data=[itemid, hour, weekday],
                    )
                ]
            ),
        )
