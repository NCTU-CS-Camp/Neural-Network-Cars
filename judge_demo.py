from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np
import pygame

from game_engine.backend.car import Car
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import FPS, SCREEN_SIZE
from server.competition_config import FRAME_LIMIT
from server.competition_maps import get_competition_map
from shared.contracts import ClientResult, SubmissionPayload


@dataclass(frozen=True, slots=True)
class DemoProfile:
    group_id: str
    username: str
    seed: int
    fixture: ClientResult


PROFILES = [
    DemoProfile("1", "ada", 101, ClientResult(False, None, 2_600.0, 470)),
    DemoProfile("1", "ben", 202, ClientResult(True, 524, 4_380.0, 524)),
    DemoProfile("2", "cy", 303, ClientResult(False, None, 3_120.0, 560)),
    DemoProfile("2", "dia", 404, ClientResult(True, 488, 4_380.0, 488)),
]


def run(server_url: str | None = None) -> None:
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Neural Cars Judge Demo")
    clock = pygame.time.Clock()
    title_font = pygame.font.SysFont("Arial", 30, bold=True)
    body_font = pygame.font.SysFont("Arial", 20)
    small_font = pygame.font.SysFont("Arial", 16)
    selected_profile = 0
    competition_id = "easy"
    use_fixture = True
    status = "Select a profile, then press Space to check eligibility and submit."
    competition_server_url = server_url or os.environ.get(
        "COMPETITION_SERVER_URL", "http://127.0.0.1:8000"
    )

    try:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return
                if event.type == pygame.KEYDOWN:
                    if pygame.K_1 <= event.key <= pygame.K_4:
                        selected_profile = event.key - pygame.K_1
                    elif event.key == pygame.K_e:
                        competition_id = "easy"
                    elif event.key == pygame.K_h:
                        competition_id = "hard"
                    elif event.key == pygame.K_f:
                        competition_id = "final"
                    elif event.key == pygame.K_r:
                        use_fixture = not use_fixture
                    elif event.key == pygame.K_SPACE:
                        profile = PROFILES[selected_profile]
                        try:
                            status = submit_profile(
                                competition_server_url,
                                profile,
                                competition_id,
                                use_fixture=use_fixture,
                            )
                        except (HTTPError, URLError, ValueError, TimeoutError) as exc:
                            status = f"Submission failed: {exc}"

            profile = PROFILES[selected_profile]
            competition_map = get_competition_map(competition_id)
            screen.blit(pygame.image.load(competition_map.front_path), (0, 0))
            shade = pygame.Surface(SCREEN_SIZE, pygame.SRCALPHA)
            shade.fill((7, 13, 20, 205))
            screen.blit(shade, (0, 0))
            _draw(screen, title_font, "JUDGE DEMO", (36, 34), (244, 247, 251))
            _draw(screen, body_font, f"Competition: {competition_id.upper()}", (36, 92), (87, 211, 207))
            _draw(screen, body_font, f"Profile: {profile.username}  /  Group {profile.group_id}", (36, 126), (244, 247, 251))
            _draw(screen, body_font, f"Result mode: {'fixture' if use_fixture else 'local demo run'}", (36, 160), (244, 247, 251))
            _draw(screen, small_font, "1-4 profile   E easy   H hard   F final   R result mode   Space submit", (36, 210), (184, 199, 213))
            _draw_wrapped(screen, small_font, status, pygame.Rect(36, 260, 760, 120), (244, 247, 251))
            pygame.display.flip()
            clock.tick(FPS)
    finally:
        pygame.quit()


def submit_profile(
    server_url: str,
    profile: DemoProfile,
    competition_id: str,
    *,
    use_fixture: bool,
) -> str:
    identity = {"group_id": profile.group_id, "username": profile.username}
    if competition_id == "final":
        eligibility_path = "/v2/finals/eligibility"
        submission_path = "/v2/finals/submissions"
    else:
        eligibility_path = f"/v2/competitions/{competition_id}/eligibility"
        submission_path = f"/v2/competitions/{competition_id}/submissions"

    eligibility = _post_json(server_url + eligibility_path, identity)
    if not eligibility.get("eligible"):
        return f"Not eligible: {eligibility.get('reason')}  {eligibility.get('next_submission_at', '')}"

    payload = _payload_for(profile)
    result = profile.fixture if use_fixture else run_local_demo(payload, competition_id)
    body = {**payload.to_dict(), "client_result": result.to_dict()}
    response = _post_json(server_url + submission_path, body)
    return f"{response['status']} {response['submission_id']} for {competition_id}"


def run_local_demo(payload: SubmissionPayload, competition_id: str) -> ClientResult:
    """Small local scorer for exercising the request path, not an official contract."""
    pygame.init()
    competition_map = get_competition_map(competition_id)
    car = Car([6, 6, 4])
    apply_weight_payload(car, payload)
    car.set_collision_surface(competition_map.build_collision_surface())
    spawn = competition_map.spawn
    car.reset_state(spawn["x"], spawn["y"], angle=spawn["angle"])
    max_progress = 0.0
    ticks_to_max_progress = 0
    for tick in range(FRAME_LIMIT):
        car.update()
        if car.collision():
            break
        car.feedforward()
        car.takeAction()
        if car.score >= max_progress:
            max_progress = float(car.score)
            ticks_to_max_progress = tick + 1
    return ClientResult(False, None, max_progress, ticks_to_max_progress)


def _payload_for(profile: DemoProfile) -> SubmissionPayload:
    rng = np.random.default_rng(profile.seed)
    return SubmissionPayload(
        group_id=profile.group_id,
        username=profile.username,
        weights=[rng.normal(0.0, 0.08, 36).tolist(), rng.normal(0.0, 0.08, 24).tolist()],
        biases=[rng.normal(0.0, 0.08, 6).tolist(), rng.normal(0.0, 0.08, 4).tolist()],
    )


def _post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"HTTP {exc.code}: {detail}") from exc


def _draw(screen: pygame.Surface, font: pygame.font.Font, text: str, pos: tuple[int, int], color: tuple[int, int, int]) -> None:
    screen.blit(font.render(text, True, color), pos)


def _draw_wrapped(
    screen: pygame.Surface,
    font: pygame.font.Font,
    text: str,
    rect: pygame.Rect,
    color: tuple[int, int, int],
) -> None:
    words = text.split()
    line = ""
    y = rect.y
    for word in words:
        candidate = f"{line} {word}".strip()
        if font.size(candidate)[0] > rect.width and line:
            _draw(screen, font, line, (rect.x, y), color)
            y += font.get_linesize()
            line = word
        else:
            line = candidate
    if line:
        _draw(screen, font, line, (rect.x, y), color)


if __name__ == "__main__":
    run()
