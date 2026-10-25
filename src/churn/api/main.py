"""FastAPI backend for churn scoring, explanations and retention playbooks."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .. import config
from ..db import ActionRepository, PredictionStore
from .schemas import (
    INPUT_FIELDS,
    ActionCreate,
    ActionListOut,
    ActionOut,
    ActionUpdate,
    BatchPredictionOut,
    BatchRequest,
    CustomerInput,
    FeedbackIn,
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


def get_store(request: Request) -> PredictionStore:
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="Prediction history database is unavailable.")
    return store


def get_actions(request: Request) -> ActionRepository:
    actions = getattr(request.app.state, "actions", None)
    if actions is None:
        raise HTTPException(status_code=503, detail="Retention action database is unavailable.")
    return actions


def _record_prediction(store: PredictionStore | None, prediction: dict[str, Any]) -> None:
    """Audit-log a score without ever failing the prediction request."""
    if store is None:
        return
    try:
        store.log_prediction(prediction)
    except Exception:  # pragma: no cover - persistence must not break scoring
        logger.exception("Could not write to the prediction history database")


def create_app(
    *,
    bundle_path: str | Path | None = None,
    scored_path: str | Path | None = None,
    data_path: str | Path | None = None,
    report_dir: str | Path | None = None,
    db_path: str | Path | None = None,
    mount_static: bool = True,
) -> FastAPI:
    """Application factory (useful for tests and multiple deployments)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Keep test databases next to the injected fixtures instead of the repo.
        resolved_db = db_path
        if resolved_db is None:
            resolved_db = Path(scored_path).parent / "churn.db" if scored_path else config.DB_PATH
        try:
            app.state.store = PredictionStore(resolved_db)
            app.state.actions = ActionRepository(resolved_db)
            logger.info("Operational database stored at %s", resolved_db)
        except Exception:  # pragma: no cover - history is non-critical for scoring
            logger.exception("Could not initialise the operational database")
            app.state.store = None
            app.state.actions = None

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
            "ui": "/app/",
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
                "history": "/history",
                "history_stats": "/history/stats",
                "feedback": "POST /feedback",
                "database": "/db/status",
                "dashboard": "/dashboard/summary",
                "actions": "/actions",
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

    # ----------------------------- dashboard ---------------------------- #
    @app.get("/dashboard/summary", tags=["analytics"])
    def dashboard_summary(
        request: Request,
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        """One call for the overview page's KPI cards and charts."""
        summary = service.dashboard_summary()
        actions = getattr(request.app.state, "actions", None)
        store = getattr(request.app.state, "store", None)
        summary["actions"] = (
            actions.summary()
            if actions is not None
            else {"pending": 0, "contacted": 0, "accepted": 0, "declined": 0, "total": 0}
        )
        summary["history"] = store.stats() if store is not None else {}
        return summary

    # ---------------------------- predictions --------------------------- #
    @app.post("/predict", response_model=PredictionOut, tags=["predictions"])
    def predict(
        customer: CustomerInput,
        request: Request,
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        """Score one customer and return drivers plus a retention playbook."""
        prediction = service.predict_one(customer.to_record())
        _record_prediction(getattr(request.app.state, "store", None), prediction)
        return prediction

    @app.post("/predict/batch", response_model=BatchPredictionOut, tags=["predictions"])
    def predict_batch(
        payload: BatchRequest,
        request: Request,
        service: ChurnService = Depends(get_service),
    ) -> dict[str, Any]:
        """Score up to 1,000 customers in one request."""
        result = service.predict_batch(
            [customer.to_record() for customer in payload.customers],
            include_drivers=payload.include_drivers,
            include_recommendations=payload.include_recommendations,
        )
        store = getattr(request.app.state, "store", None)
        for prediction in result["predictions"]:
            _record_prediction(store, prediction)
        return result

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

    # ------------------------------ history ----------------------------- #
    @app.get("/history", tags=["history"])
    def history(
        limit: int = Query(20, ge=1, le=200),
        store: PredictionStore = Depends(get_store),
    ) -> dict[str, Any]:
        """Most recent scores from the audit trail (newest first)."""
        items = store.recent(limit)
        return {"returned": len(items), "items": items}

    @app.get("/history/stats", tags=["history"])
    def history_stats(store: PredictionStore = Depends(get_store)) -> dict[str, Any]:
        return store.stats()

    @app.post("/feedback", status_code=201, tags=["history"])
    def feedback(
        payload: FeedbackIn, store: PredictionStore = Depends(get_store)
    ) -> dict[str, Any]:
        """Record the observed outcome for a previously scored customer."""
        return store.add_feedback(payload.prediction_id, payload.actual_churn, payload.notes)

    @app.get("/db/status", tags=["history"])
    def db_status(store: PredictionStore = Depends(get_store)) -> dict[str, Any]:
        return store.status()

    # -------------------------- retention actions ----------------------- #
    @app.post("/actions", response_model=ActionOut, status_code=201, tags=["retention"])
    def create_action(
        payload: ActionCreate,
        service: ChurnService = Depends(get_service),
        actions: ActionRepository = Depends(get_actions),
    ) -> dict[str, Any]:
        """Save a recommended playbook action for the retention team."""
        detail = service.customer_detail(payload.customer_id)
        if detail is not None:
            recommendation = next(
                (
                    item
                    for item in detail["recommendations"]
                    if item["id"] == payload.recommendation_id
                ),
                None,
            )
            if recommendation is None:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"Recommendation {payload.recommendation_id!r} is not active for "
                        f"customer {payload.customer_id!r}"
                    ),
                )
            title = recommendation["title"]
            offer = recommendation["offer"]
            risk_level = detail["risk_level"]
            churn_probability = detail["churn_probability"]
        else:
            # Ad-hoc scores (for example the demo profile) are not in the scored
            # book. Accept a validated snapshot from the client so the team can
            # still save the action; book customers always use server values.
            if not (
                payload.title
                and payload.offer
                and payload.risk_level
                and payload.churn_probability is not None
            ):
                raise HTTPException(
                    status_code=404,
                    detail=f"Customer {payload.customer_id!r} not found in the scored book",
                )
            title = payload.title
            offer = payload.offer
            risk_level = payload.risk_level
            churn_probability = payload.churn_probability
        return actions.save_action(
            customer_id=payload.customer_id,
            recommendation_id=payload.recommendation_id,
            title=title,
            offer=offer,
            risk_level=risk_level,
            churn_probability=churn_probability,
            status=payload.status,
            note=payload.note,
        )

    @app.get("/actions", response_model=ActionListOut, tags=["retention"])
    def list_actions(
        status: str | None = Query(None, pattern="^(pending|contacted|accepted|declined)$"),
        customer_id: str | None = Query(None),
        limit: int = Query(100, ge=1, le=500),
        actions: ActionRepository = Depends(get_actions),
    ) -> dict[str, Any]:
        rows = actions.list_actions(status=status, customer_id=customer_id, limit=limit)
        return {"total": len(rows), "actions": rows}

    @app.get("/actions/summary", tags=["retention"])
    def actions_summary(actions: ActionRepository = Depends(get_actions)) -> dict[str, int]:
        return actions.summary()

    @app.patch("/actions/{action_id}", response_model=ActionOut, tags=["retention"])
    def update_action(
        action_id: int,
        payload: ActionUpdate,
        actions: ActionRepository = Depends(get_actions),
    ) -> dict[str, Any]:
        updated = actions.update_action(action_id, status=payload.status, note=payload.note)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
        return updated

    @app.delete("/actions/{action_id}", status_code=204, tags=["retention"])
    def delete_action(
        action_id: int,
        actions: ActionRepository = Depends(get_actions),
    ) -> Response:
        if not actions.delete_action(action_id):
            raise HTTPException(status_code=404, detail=f"Action {action_id} not found")
        return Response(status_code=204)

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
        if config.FRONTEND_DIR.exists():
            app.mount(
                "/app",
                StaticFiles(directory=config.FRONTEND_DIR, html=True),
                name="ui",
            )

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
