from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from game_engine.backend.serialization import export_submission_payload
from shared.contracts import ClientResult


@dataclass(slots=True)
class SubmissionResult:
    ok: bool
    message: str
    submission_id: str | None = None


def submit_car(
    *,
    server_url: str,
    car: Any,
    group_id: str,
    username: str,
    competition_id: str = "easy",
    client_result: ClientResult | None = None,
    token: str | None = None,
    skin_id: int = 0,
    max_speed: float = 10.0,
    timeout: float = 5.0,
) -> SubmissionResult:
    if client_result is None:
        return SubmissionResult(
            False,
            "競賽提交必須包含本機評測結果。請使用 competition_main.py。",
        )
    payload = export_submission_payload(
        car=car,
        group_id=group_id,
        username=username,
    )
    data = {**payload.to_dict(), "client_result": client_result.to_dict()}
    data["skin_id"] = skin_id
    data["max_speed"] = max_speed
    body = json.dumps(data).encode("utf-8")
    if competition_id == "final":
        url = server_url.rstrip("/") + "/v2/finals/submissions"
    else:
        url = server_url.rstrip("/") + f"/v2/competitions/{competition_id}/submissions"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )

    try:
        with urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return SubmissionResult(False, f"提交失敗：HTTP {exc.code} {detail}")
    except (TimeoutError, URLError) as exc:
        return SubmissionResult(False, f"提交失敗：{exc}")

    submission_id = data.get("submission_id")
    if not submission_id:
        return SubmissionResult(False, "提交失敗：伺服器未回傳提交編號")
    competition_labels = {"easy": "簡單", "hard": "困難", "final": "決賽"}
    competition_id = str(data.get("competition_id", competition_id))
    return SubmissionResult(
        True,
        f"已提交 {submission_id}（{competition_labels.get(competition_id, competition_id)}）",
        submission_id,
    )
