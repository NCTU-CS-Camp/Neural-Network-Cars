from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from server.competition_maps import get_competition_map, list_competition_maps
from server.evaluation_worker import BatchWorker
from server.events import EventBroadcaster
from server.models import CompetitionId
from server.schemas import AdminStageRequest, IdentityIn, SubmissionIn
from server.storage import CompetitionStorage, SubmissionRejected


DEFAULT_ADMIN_TOKEN = "admin"


def create_app(
    *,
    storage: CompetitionStorage | None = None,
    start_worker: bool = True,
    admin_token: str | None = None,
    worker_poll_interval: float = 5.0,
) -> FastAPI:
    app_storage = storage or CompetitionStorage()
    broadcaster = EventBroadcaster()
    worker = BatchWorker(
        app_storage,
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
        broadcaster.publish(app_storage.competition_update_payload())
        try:
            yield
        finally:
            worker.stop()

    app = FastAPI(title="Neural Network Cars Trusted Competition", lifespan=lifespan)

    def require_admin(x_admin_token: str | None) -> None:
        if x_admin_token != token:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="invalid admin token",
            )

    def competition_identifier(value: str) -> CompetitionId:
        try:
            return CompetitionId(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="competition not found",
            ) from exc

    def phase_one_identifier(value: str) -> CompetitionId:
        identifier = competition_identifier(value)
        if identifier is CompetitionId.FINAL:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="use the finals endpoint",
            )
        return identifier

    def rejected_response(error: SubmissionRejected) -> JSONResponse:
        body: dict[str, Any] = {"error": error.code}
        if error.next_submission_at is not None:
            body["next_submission_at"] = error.next_submission_at
        return JSONResponse(status_code=error.status_code, content=body)

    @app.get("/health")
    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v2/state")
    def competition_state() -> dict[str, Any]:
        return app_storage.state()

    @app.get("/v2/maps")
    def maps() -> list[dict[str, Any]]:
        return [item.to_public_dict() for item in list_competition_maps()]

    @app.get("/v2/maps/{competition_id}/preview")
    def map_preview(competition_id: str) -> FileResponse:
        identifier = competition_identifier(competition_id)
        competition_map = get_competition_map(identifier)
        if not competition_map.front_path.exists():
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="map preview not found",
            )
        return FileResponse(competition_map.front_path, media_type="image/png")

    @app.post("/v2/competitions/{competition_id}/eligibility")
    def phase_one_eligibility(competition_id: str, identity: IdentityIn) -> dict[str, Any]:
        identifier = phase_one_identifier(competition_id)
        try:
            group_id, username = identity.clean_identity()
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        return app_storage.eligibility(identifier, group_id=group_id, username=username)

    @app.post(
        "/v2/competitions/{competition_id}/submissions",
        status_code=HTTPStatus.CREATED,
    )
    def create_phase_one_submission(competition_id: str, body: SubmissionIn) -> Any:
        identifier = phase_one_identifier(competition_id)
        try:
            payload, client_result = body.to_submission()
            submission = app_storage.create_submission(identifier, payload, client_result)
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        except SubmissionRejected as exc:
            return rejected_response(exc)
        submission["next_submission_at"] = app_storage.eligibility(
            identifier,
            group_id=payload.group_id,
            username=payload.username,
        )["next_submission_at"]
        return submission

    @app.post("/v2/finals/eligibility")
    def final_eligibility(identity: IdentityIn) -> dict[str, Any]:
        try:
            group_id, username = identity.clean_identity()
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        return app_storage.eligibility(
            CompetitionId.FINAL,
            group_id=group_id,
            username=username,
        )

    @app.post("/v2/finals/submissions", status_code=HTTPStatus.CREATED)
    def create_final_submission(body: SubmissionIn) -> Any:
        try:
            payload, client_result = body.to_submission()
            submission = app_storage.create_submission(
                CompetitionId.FINAL,
                payload,
                client_result,
            )
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        except SubmissionRejected as exc:
            return rejected_response(exc)
        broadcaster.publish(app_storage.competition_update_payload())
        return submission

    @app.get("/v2/competitions/{competition_id}/leaderboard")
    def leaderboard(competition_id: str) -> list[dict[str, Any]]:
        return app_storage.leaderboard(competition_identifier(competition_id))

    @app.get("/v2/competitions/{competition_id}/submissions/{submission_id}")
    def submission_status(competition_id: str, submission_id: str) -> dict[str, Any]:
        submission = app_storage.get_submission(competition_identifier(competition_id), submission_id)
        if submission is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="submission not found")
        return submission

    @app.get("/v2/admin/submissions")
    def admin_submissions(
        x_admin_token: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        require_admin(x_admin_token)
        return app_storage.list_submissions()

    @app.get("/v2/admin/replay")
    def admin_replay(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        return app_storage.replay_payload()

    @app.post("/v2/admin/stage")
    def admin_stage(
        request: AdminStageRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        state = app_storage.set_stage(request.stage)
        broadcaster.publish(app_storage.competition_update_payload())
        return state

    @app.post("/v2/admin/batches/run-now")
    def admin_run_batch(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, int]:
        require_admin(x_admin_token)
        return {"processed": worker.process_now()}

    @app.post("/v2/admin/replay/restart")
    def admin_restart_replay(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        state = app_storage.restart_replay()
        broadcaster.publish(app_storage.competition_update_payload())
        return state

    @app.post("/v2/admin/reset-all")
    def admin_reset_all(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, str]:
        require_admin(x_admin_token)
        app_storage.reset()
        broadcaster.publish(app_storage.competition_update_payload())
        return {"status": "reset", "scope": "competition"}

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
