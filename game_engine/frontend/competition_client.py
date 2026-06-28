from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from shared.contracts import ClientResult, SubmissionPayload


@dataclass(slots=True)
class NetworkError:
    message: str


@dataclass(slots=True)
class EligibilityResult:
    eligible: bool
    reason: str | None
    stage: str
    next_submission_at: str
    competition_config_version: str


@dataclass(slots=True)
class SubmissionAccepted:
    body: dict[str, Any]


@dataclass(slots=True)
class SubmissionRejected:
    error: str
    next_submission_at: str | None


def _post_json(url: str, payload: dict[str, Any], timeout: float = 10.0) -> tuple[int, dict[str, Any]] | NetworkError:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8")) if response.length != 0 else {}
            return response.status, body
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        body = json.loads(raw.decode("utf-8")) if raw else {}
        return exc.code, body
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        return NetworkError(message=str(exc))
    except json.JSONDecodeError as exc:
        return NetworkError(message=f"server 回應格式錯誤: {exc}")


def _eligibility_path(competition_id: str) -> str:
    if competition_id == "final":
        return "/v2/finals/eligibility"
    return f"/v2/competitions/{competition_id}/eligibility"


def _submission_path(competition_id: str) -> str:
    if competition_id == "final":
        return "/v2/finals/submissions"
    return f"/v2/competitions/{competition_id}/submissions"


def check_eligibility(
    server_url: str, competition_id: str, group_id: str, username: str
) -> EligibilityResult | NetworkError:
    url = f"{server_url.rstrip('/')}{_eligibility_path(competition_id)}"
    result = _post_json(url, {"group_id": group_id, "username": username})
    if isinstance(result, NetworkError):
        return result

    status, body = result
    if status != 200:
        return NetworkError(message=f"server 回應非預期狀態碼: {status}")
    return EligibilityResult(
        eligible=bool(body.get("eligible", False)),
        reason=body.get("reason"),
        stage=str(body.get("stage", "")),
        next_submission_at=str(body.get("next_submission_at", "")),
        competition_config_version=str(body.get("competition_config_version", "")),
    )


def submit(
    server_url: str,
    competition_id: str,
    payload: SubmissionPayload,
    client_result: ClientResult,
) -> SubmissionAccepted | SubmissionRejected | NetworkError:
    url = f"{server_url.rstrip('/')}{_submission_path(competition_id)}"
    body = {**payload.to_dict(), "client_result": client_result.to_dict()}
    result = _post_json(url, body)
    if isinstance(result, NetworkError):
        return result

    status, response_body = result
    if status == 201:
        return SubmissionAccepted(body=response_body)
    if status in (429, 409):
        return SubmissionRejected(
            error=str(response_body.get("error", "rejected")),
            next_submission_at=response_body.get("next_submission_at"),
        )
    return NetworkError(message=f"server 回應非預期狀態碼: {status}")
