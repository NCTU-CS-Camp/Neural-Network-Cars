from __future__ import annotations

import asyncio
import csv
import io
import json
import os
from contextlib import asynccontextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from server.competition_maps import get_competition_map, list_competition_maps
from server.evaluation_worker import BatchWorker
from server.events import EventBroadcaster
from server.models import CompetitionId
from server.schemas import (
    AdminConfigRequest,
    AdminStageRequest,
    AdminUserImportRequest,
    AdminUserRequest,
    IdentityIn,
    LoginIn,
    SubmissionIn,
)
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

    def require_user(authorization: str | None) -> dict[str, str]:
        prefix = "Bearer "
        if authorization is None or not authorization.startswith(prefix):
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="missing bearer token",
            )
        identity = app_storage.authenticate_token(authorization[len(prefix) :].strip())
        if identity is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="invalid or expired bearer token",
            )
        return identity

    def require_matching_identity(
        token_identity: dict[str, str],
        *,
        group_id: str,
        username: str,
    ) -> None:
        if (
            token_identity["group_id"] != group_id
            or token_identity["username"] != username
        ):
            raise HTTPException(
                status_code=HTTPStatus.FORBIDDEN,
                detail="token identity does not match request body",
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

    @app.post("/v2/auth/login")
    def login(body: LoginIn) -> dict[str, Any]:
        try:
            group_id, username, password = body.clean_login()
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        session = app_storage.login_user(
            group_id=group_id,
            username=username,
            password=password,
        )
        if session is None:
            raise HTTPException(
                status_code=HTTPStatus.UNAUTHORIZED,
                detail="invalid credentials",
            )
        return session

    @app.get("/v2/me/submissions")
    def my_submissions(
        competition_id: str | None = Query(default=None),
        authorization: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        identity = require_user(authorization)
        identifier = None if competition_id is None else competition_identifier(competition_id)
        return app_storage.user_submissions(
            group_id=identity["group_id"],
            username=identity["username"],
            competition_id=identifier,
        )

    @app.get("/v2/admin/state")
    def admin_state(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
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

    @app.get("/v2/admin/users")
    def admin_users(
        x_admin_token: str | None = Header(default=None),
    ) -> list[dict[str, Any]]:
        require_admin(x_admin_token)
        return app_storage.list_users()

    @app.post("/v2/admin/users")
    def admin_upsert_user(
        body: AdminUserRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        try:
            group_id, username, password = body.clean_login()
            return app_storage.upsert_user(
                group_id=group_id,
                username=username,
                password=password,
                disabled=body.disabled,
            )
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc

    @app.post("/v2/admin/users/import")
    def admin_import_users(
        body: AdminUserImportRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        try:
            users = _admin_import_users(body)
            saved = [
                app_storage.upsert_user(
                    group_id=user["group_id"],
                    username=user["username"],
                    password=user["password"],
                    disabled=bool(user.get("disabled", False)),
                )
                for user in users
            ]
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        return {"imported": len(saved), "users": saved}

    @app.post("/v2/admin/users/{group_id}/{username}/disable")
    def admin_disable_user(
        group_id: str,
        username: str,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        user = app_storage.set_user_disabled(
            group_id=group_id,
            username=username,
            disabled=True,
        )
        if user is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="user not found")
        return user

    @app.post("/v2/admin/users/{group_id}/{username}/enable")
    def admin_enable_user(
        group_id: str,
        username: str,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        user = app_storage.set_user_disabled(
            group_id=group_id,
            username=username,
            disabled=False,
        )
        if user is None:
            raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="user not found")
        return user

    @app.post("/v2/competitions/{competition_id}/eligibility")
    def phase_one_eligibility(
        competition_id: str,
        identity: IdentityIn,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        identifier = phase_one_identifier(competition_id)
        token_identity = require_user(authorization)
        try:
            group_id, username = identity.clean_identity()
            require_matching_identity(
                token_identity,
                group_id=group_id,
                username=username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        return app_storage.eligibility(identifier, group_id=group_id, username=username)

    @app.post(
        "/v2/competitions/{competition_id}/submissions",
        status_code=HTTPStatus.CREATED,
    )
    def create_phase_one_submission(
        competition_id: str,
        body: SubmissionIn,
        authorization: str | None = Header(default=None),
    ) -> Any:
        identifier = phase_one_identifier(competition_id)
        try:
            payload, client_result = body.to_submission()
            token_identity = require_user(authorization)
            require_matching_identity(
                token_identity,
                group_id=payload.group_id,
                username=payload.username,
            )
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
    def final_eligibility(
        identity: IdentityIn,
        authorization: str | None = Header(default=None),
    ) -> dict[str, Any]:
        token_identity = require_user(authorization)
        try:
            group_id, username = identity.clean_identity()
            require_matching_identity(
                token_identity,
                group_id=group_id,
                username=username,
            )
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        return app_storage.eligibility(
            CompetitionId.FINAL,
            group_id=group_id,
            username=username,
        )

    @app.post("/v2/finals/submissions", status_code=HTTPStatus.CREATED)
    def create_final_submission(
        body: SubmissionIn,
        authorization: str | None = Header(default=None),
    ) -> Any:
        try:
            payload, client_result = body.to_submission()
            token_identity = require_user(authorization)
            require_matching_identity(
                token_identity,
                group_id=payload.group_id,
                username=payload.username,
            )
            submission = app_storage.create_submission(
                CompetitionId.FINAL,
                payload,
                client_result,
            )
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        except SubmissionRejected as exc:
            return rejected_response(exc)
        submission["next_submission_at"] = app_storage.eligibility(
            CompetitionId.FINAL,
            group_id=payload.group_id,
            username=payload.username,
        )["next_submission_at"]
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

    @app.delete("/v2/admin/submissions/{submission_id}")
    def admin_delete_submission(
        submission_id: str,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        submission = app_storage.delete_submission(submission_id)
        if submission is None:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND,
                detail="submission not found",
            )
        broadcaster.publish(app_storage.competition_update_payload())
        return submission

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

    @app.post("/v2/admin/config")
    def admin_config(
        request: AdminConfigRequest,
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, Any]:
        require_admin(x_admin_token)
        try:
            minutes = request.clean_phase_one_batch_minutes()
        except ValueError as exc:
            raise HTTPException(status_code=HTTPStatus.BAD_REQUEST, detail=str(exc)) from exc
        state = app_storage.set_phase_one_batch_minutes(minutes)
        broadcaster.publish(app_storage.competition_update_payload())
        return state

    @app.post("/v2/admin/batches/run-now")
    def admin_run_batch(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, int]:
        require_admin(x_admin_token)
        return {"processed": worker.process_now()}

    @app.post("/v2/admin/batches/process-due")
    def admin_process_due_batches(
        x_admin_token: str | None = Header(default=None),
    ) -> dict[str, int]:
        require_admin(x_admin_token)
        return {"processed": worker.process_due()}

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


def _admin_import_users(request: AdminUserImportRequest) -> list[dict[str, Any]]:
    if request.users is not None:
        users = []
        for user in request.users:
            group_id, username, password = user.clean_login()
            users.append(
                {
                    "group_id": group_id,
                    "username": username,
                    "password": password,
                    "disabled": user.disabled,
                }
            )
        return users

    raw_text = (request.text or "").strip()
    if not raw_text:
        raise ValueError("users or text is required")
    if raw_text[0] in "[{":
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError("JSON import text is invalid") from exc
        rows = parsed.get("users", parsed) if isinstance(parsed, dict) else parsed
        if not isinstance(rows, list):
            raise ValueError("JSON import must be a list or an object with users")
        users = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("JSON import rows must be objects")
            try:
                users.append(
                    {
                        "group_id": str(row["group_id"]).strip(),
                        "username": str(row["username"]).strip(),
                        "password": str(row["password"]).strip(),
                        "disabled": bool(row.get("disabled", False)),
                    }
                )
            except KeyError as exc:
                raise ValueError("JSON import rows require group_id, username, password") from exc
        return users

    first_line = raw_text.splitlines()[0].lower()
    if "group" in first_line and "username" in first_line:
        reader = csv.DictReader(io.StringIO(raw_text))
        return [
            {
                "group_id": str(row["group_id"]).strip(),
                "username": str(row["username"]).strip(),
                "password": str(row["password"]).strip(),
                "disabled": str(row.get("disabled", "")).strip().lower()
                in {"1", "true", "yes", "disabled"},
            }
            for row in reader
        ]

    users = []
    for row in csv.reader(io.StringIO(raw_text)):
        if not row or len(row) < 3:
            continue
        users.append(
            {
                "group_id": row[0].strip(),
                "username": row[1].strip(),
                "password": row[2].strip(),
                "disabled": len(row) >= 4
                and row[3].strip().lower() in {"1", "true", "yes", "disabled"},
            }
        )
    if not users:
        raise ValueError("no importable users found")
    return users


def _load_html(filename: str) -> str:
    path = Path(__file__).resolve().parent / "static" / filename
    return path.read_text(encoding="utf-8")


app = create_app()


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    uvicorn.run("server.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
