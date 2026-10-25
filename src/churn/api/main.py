"""FastAPI backend for churn scoring, explanations and retention playbooks."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from .schemas import (
    INPUT_FIELDS,
    BatchPredictionOut,
    BatchRequest,
    CustomerInput,
    HealthOut,
    HighRiskListOut,
    PredictionOut,
)
from .service import ChurnService, DataUnavailableError

logger = logging.getLogger(__name__)


def get_service(request: Request) -> ChurnService:
    service = getattr(request.app.state, "service", None)
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=("Model is not loaded. Train it with `uv run churn-train` and restart the API."),
        )
    return service


def create_app(
    *,
    bundle_path: str | Path | None = None,
    scored_path: str | Path | None = None,
    data_path: str | Path | None = None,
    report_dir: str | Path | None = None,
    mount_static: bool = True,
) -> FastAPI:
    """Application factory (useful for tests and multiple deployments)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.service = ChurnService.from_paths(
                bundle_path, scored_path=scored_path, data_path=data_path
            )
            logger.info("Loaded churn model '%s'", app.state.service.model_name)
        except FileNotFoundError as exc:
            logger.warning("Starting without a trained model: %s", exc)
            app.state.service = None
        except Exception:  # pragma: no cover - fail open, endpoints return 503
            logger.exception("Failed to load the model bundle")
            app.state.service = None
        try:
            yield
        finally:
            app.state.service = None

    app = FastAPI(
        title=config.API_TITLE,
        version=config.API_VERSION,
        description=(
            "Predict customer churn, understand the drivers behind each score with SHAP, "
            "and generate personalised retention recommendations from a rule-based playbook."
        ),
        lifespan=lifespan,
        contact={"name": "Churn Intelligence", "url": "https://github.com/"},
        license_info={"name": "MIT"},
    )

    origins = [origin.strip() for origin in config.CORS_ORIGINS if origin.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials="*" not in origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    reports_dir = Path(report_dir) if report_dir else config.REPORT_DIR
    figures_dir = reports_dir / "figures"

    @app.exception_handler(DataUnavailableError)
    async def _data_unavailable(_: Request, exc: DataUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def _value_error(_: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # ------------------------------- meta ------------------------------- #
    @app.get("/", tags=["meta"])
    def root() -> dict[str, Any]:
        return {
            "name": config.API_TITLE,
            "version": config.API_VERSION,
            "docs": "/docs",
            "endpoints": {
                "health": "/health",
                "model_info": "/model/info",
                "model_metrics": "/model/metrics",
                "model_features": "/model/features",
                "predict": "POST /predict",
                "predict_batch": "POST /predict/batch",
                "high_risk": "/customers/high-risk",
                "customer_detail": "/customers/{customer_id}",
                "eda": "/eda/summary",
                "model_card": "/model/card",
                "figures": "/figures",
            },
        }

    @app.get("/health", response_model=HealthOut, tags=["meta"])
    def health(request: Request) -> dict[str, Any]:
        service: ChurnService | None = getattr(request.app.state, "service", None)
        if service is None:
            return {
                "status": "degraded",
                "model_loaded": False,
                "model_name": None,
                "model_version": None,
                "threshold": None,
                "scored_customers": 0,
                "api_version": config.API_VERSION,
            }
        return service.health()

    @app.get("/model/info", tags=["model"])
    def model_info(service: ChurnService = Depends(get_service)) -> dict[str, Any]:
        return service.model_info()

    @app.get("/model/metrics", tags=["model"])
    def model_metrics(service: ChurnService = Depends(get_service)) -> dict[str, Any]:
        return service.model_metrics()

    @app.get("/model/features", tags=["model"])
    def model_features() -> dict[str, Any]:
        defaults = {field["name"]: field["default"] for field in INPUT_FIELDS}
        example = CustomerInput.model_config.get("json_schema_extra", {}).get("example", defaults)
        return {
            "fields": INPUT_FIELDS,
            "defaults": defaults,
            "example": example,
            "required_fields": [field["name"] for field in INPUT_FIELDS if field.get("required")],
            "derived_features": [
                "NumServices",
                "SupportServices",
                "StreamingServices",
                "IsNewCustomer",
                "HasFamily",
            ],
        }

    @app.get("/model/card", response_class=PlainTextResponse, tags=["model"])
    def model_card() -> str:
        path = (Path(report_dir) if report_dir else config.REPORT_DIR) / "model_card.md"
        if not path.exists():
            raise HTTPException(status_code=404, detail="Model card not generated yet.")
        return path.read_text(encoding="utf-8")

    # ---------------------------- predictions --------------------------- #
    @app.post("/predict", response_model=PredictionOut, tags=["predictions"])
    def predict(
        customer: CustomerInput,
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        """Score one customer and return drivers plus a retention playbook."""
        return service.predict_one(customer.to_record())

    @app.post("/predict/batch", response_model=BatchPredictionOut, tags=["predictions"])
    def predict_batch(
        payload: BatchRequest,
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        """Score up to 1,000 customers in one request."""
        return service.predict_batch(
            [customer.to_record() for customer in payload.customers],
            include_drivers=payload.include_drivers,
            include_recommendations=payload.include_recommendations,
        )

    # ----------------------------- customer book ------------------------ #
    @app.get("/customers/high-risk", response_model=HighRiskListOut, tags=["customers"])
    def high_risk(
        limit: int = Query(20, ge=1, le=500),
        risk_level: str | None = Query("high", pattern="^(low|medium|high)$"),
        min_probability: float | None = Query(None, ge=0.0, le=1.0),
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        """Rank the customer book by churn probability (high risk by default).

        Pass ``risk_level=medium`` or ``risk_level=low`` to inspect other bands.
        """
        return service.high_risk_customers(
            limit=limit, risk_level=risk_level, min_probability=min_probability
        )

    @app.get("/customers/{customer_id}", response_model=PredictionOut, tags=["customers"])
    def customer_detail(
        customer_id: str,
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        result = service.customer_detail(customer_id)
        if result is None:
            raise HTTPException(status_code=404, detail=f"Customer {customer_id!r} not found")
        return result

    # --------------------------------- EDA ------------------------------ #
    @app.get("/eda/summary", tags=["analytics"])
    def eda_summary(service: ChurnService = Depends(get_service)) -> dict[str, Any]:
        return service.eda_summary()

    @app.get("/figures", tags=["meta"])
    @app.get("/figures/", include_in_schema=False)
    def list_figures() -> dict[str, Any]:
        """List generated report figures for the frontend gallery."""
        files = sorted(figures_dir.glob("*.png")) if figures_dir.exists() else []
        return {"figures": [{"name": path.name, "url": f"/figures/{path.name}"} for path in files]}

    # ------------------------------- static ----------------------------- #
    if mount_static:
        figures_dir.mkdir(parents=True, exist_ok=True)
        app.mount("/figures", StaticFiles(directory=figures_dir), name="figures")
        app.mount("/reports", StaticFiles(directory=reports_dir), name="reports")

    return app


app = create_app()


def run() -> None:
    """Console entry point: ``uv run churn-serve``."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )
    uvicorn.run(
        "churn.api.main:app",
        host=os.getenv("CHURN_HOST", "127.0.0.1"),
        port=int(os.getenv("CHURN_PORT", "8000")),
        reload=os.getenv("CHURN_RELOAD", "0") == "1",
    )


if __name__ == "__main__":
    run()
