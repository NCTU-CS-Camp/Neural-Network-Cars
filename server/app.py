from __future__ import annotations

import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from server.evaluation_worker import EvaluationWorker, Evaluator
from server.evaluator import OfficialEvaluator
from server.schemas import AdminReplayRequest, SubmissionCreateResponse, SubmissionIn
from server.storage import CompetitionStorage


DEFAULT_ADMIN_TOKEN = "admin"


def create_app(
    *,
    storage: CompetitionStorage | None = None,
    evaluator: Evaluator | None = None,
    start_worker: bool = True,
    admin_token: str | None = None,
) -> FastAPI:
    app_storage = storage or CompetitionStorage()
    app_evaluator = evaluator or OfficialEvaluator()
    worker = EvaluationWorker(app_storage, app_evaluator)
    token = admin_token or os.environ.get("COMPETITION_ADMIN_TOKEN", DEFAULT_ADMIN_TOKEN)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.storage = app_storage
        app.state.worker = worker
        app.state.admin_token = token
        if start_worker:
            worker.start()
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="Neural Network Cars Competition", lifespan=lifespan)

    def require_admin(x_admin_token: str | None) -> None:
        if x_admin_token != token:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="invalid admin token",
            )

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/api/submissions",
        response_model=SubmissionCreateResponse,
        status_code=HTTPStatus.CREATED,
    )
    def create_submission(payload: SubmissionIn) -> SubmissionCreateResponse:
        try:
            weight_payload = payload.to_weight_payload()
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=str(exc),
            ) from exc

        submission = app_storage.create_submission(weight_payload)
        return SubmissionCreateResponse(
            submission_id=submission["submission_id"],
            status=submission["status"],
        )

    @app.get("/api/submissions")
    def list_submissions() -> list[dict[str, Any]]:
        return app_storage.list_submissions()

    @app.get("/api/submissions/{submission_id}")
    def get_submission(submission_id: str) -> dict[str, Any]:
        submission = app_storage.get_submission(submission_id)
        if submission is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="submission not found",
            )
        return submission

    @app.get("/api/leaderboard")
    def leaderboard() -> list[dict[str, Any]]:
        return app_storage.leaderboard()

    @app.get("/api/replay/top")
    def replay_top(n: int = Query(default=5, ge=1, le=20)) -> dict[str, Any]:
        return {"items": app_storage.replay_top(n)}

    @app.post("/api/admin/reset")
    def admin_reset(x_admin_token: str | None = Header(default=None)) -> dict[str, str]:
        require_admin(x_admin_token)
        app_storage.reset()
        return {"status": "reset"}

    @app.post("/api/admin/replay")
    def admin_replay(
        payload: AdminReplayRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        result = app_storage.set_featured_submission(payload.submission_id)
        if result is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="submission not found",
            )
        return result

    @app.get("/leaderboard", response_class=HTMLResponse)
    def leaderboard_page() -> str:
        return _load_html("leaderboard.html")

    @app.get("/admin", response_class=HTMLResponse)
    def admin_page() -> str:
        return _load_html("admin.html")

    return app


def _load_html(filename: str) -> str:
    path = Path(__file__).resolve().parent / "static" / filename
    return path.read_text(encoding="utf-8")


app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run("server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
