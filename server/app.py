from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from server.evaluation_worker import EvaluationWorker, Evaluator
from server.evaluator import OfficialEvaluator
from server.events import EventBroadcaster
from server.schemas import (
    AdminMapRequest,
    AdminPhaseRequest,
    SubmissionCreateResponse,
    SubmissionIn,
)
from server.storage import CompetitionStorage


DEFAULT_ADMIN_TOKEN = "admin"


def create_app(
    *,
    storage: CompetitionStorage | None = None,
    evaluator: Evaluator | None = None,
    start_worker: bool = True,
    admin_token: str | None = None,
    worker_poll_interval: float = 60.0,
) -> FastAPI:
    app_storage = storage or CompetitionStorage()
    app_evaluator = evaluator or OfficialEvaluator()
    broadcaster = EventBroadcaster()
    worker = EvaluationWorker(
        app_storage,
        app_evaluator,
        poll_interval=worker_poll_interval,
        publish_update=broadcaster.publish,
    )
    token = admin_token or os.environ.get("COMPETITION_ADMIN_TOKEN", DEFAULT_ADMIN_TOKEN)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        broadcaster.set_loop(asyncio.get_running_loop())
        app.state.storage = app_storage
        app.state.worker = worker
        app.state.admin_token = token
        app.state.broadcaster = broadcaster
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

    def publish_current_update() -> None:
        broadcaster.publish(app_storage.competition_update_payload())

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/state")
    def competition_state() -> dict[str, Any]:
        return app_storage.competition_state()

    @app.get("/api/maps")
    def maps() -> list[dict[str, Any]]:
        return app_storage.list_official_maps()

    @app.post(
        "/api/submissions",
        response_model=SubmissionCreateResponse,
        status_code=HTTPStatus.CREATED,
    )
    def create_submission(payload: SubmissionIn) -> SubmissionCreateResponse:
        try:
            submission_payload = payload.to_submission_payload()
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.BAD_REQUEST,
                detail=str(exc),
            ) from exc

        submission = app_storage.create_submission(submission_payload)
        return SubmissionCreateResponse(
            submission_id=submission["submission_id"],
            status=submission["status"],
            phase=submission["phase"],
        )

    @app.get("/api/submissions")
    def list_submissions(
        x_admin_token: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        require_admin(x_admin_token)
        return app_storage.list_submissions()

    @app.get("/api/submissions/{submission_id}")
    def get_submission(
        submission_id: str,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        submission = app_storage.get_submission(submission_id)
        if submission is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="submission not found",
            )
        return submission

    @app.get("/api/leaderboard")
    def leaderboard() -> list[dict[str, Any]]:
        return app_storage.leaderboard(limit=30)

    @app.get("/api/replay/top")
    def replay_top(n: int = Query(default=10, ge=1, le=30)) -> dict[str, Any]:
        active_map = app_storage.active_map()
        return {
            "phase": app_storage.active_phase().value,
            "map": active_map.to_dict(),
            "items": app_storage.replay_top(n),
        }

    @app.post("/api/admin/phase")
    def admin_set_phase(
        payload: AdminPhaseRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        state = app_storage.set_active_phase(payload.phase)
        publish_current_update()
        return state

    @app.post("/api/admin/map")
    def admin_set_map(
        payload: AdminMapRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        state = app_storage.set_phase_map(payload.phase, payload.map_id)
        worker.rerun_best_for_phase(payload.phase.value)
        return state

    @app.post("/api/admin/reset")
    def admin_reset(x_admin_token: str | None = Header(default=None)) -> dict[str, str]:
        require_admin(x_admin_token)
        phase = app_storage.active_phase()
        app_storage.reset_phase(phase)
        publish_current_update()
        return {"status": "reset", "phase": phase.value}

    @app.post("/api/admin/process-pending")
    def admin_process_pending(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, int]:
        require_admin(x_admin_token)
        return {"processed": worker.process_pending_batch()}

    @app.websocket("/ws/events")
    async def websocket_events(websocket: WebSocket) -> None:
        await broadcaster.connect(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            broadcaster.disconnect(websocket)

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
