from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pygame
from shapely.geometry import Point  # type: ignore[import-untyped]
from shapely.geometry.polygon import Polygon  # type: ignore[import-untyped]

from GA.fitness import get_fitness_strategy
from game_engine.backend.assets import GameAssets, load_game_assets
from game_engine.backend.car import Car, configure_car, set_collision_map
from game_engine.backend.competition_track import CompetitionRunTracker
from game_engine.backend.settings import (
    HIDDEN_LAYER,
    INPUT_LAYER,
    MAX_SPEED,
    OUTPUT_LAYER,
    SCREEN_SIZE,
)
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.config_store import load_runtime_settings
from game_engine.frontend.submission_client import submit_car
from server.competition_config import FRAME_LIMIT
from server.competition_maps import CompetitionMap, get_competition_map
from shared.contracts import ClientResult, RuntimeSettings, SubmissionPayload


CompetitionName = str
LAYER_SIZES = [INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]


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

PANEL = pygame.Rect(1110, 24, 466, 852)
FIELD_W = 238
FIELD_H = 30

BG = (11, 17, 24)
PANEL_BG = (8, 14, 22, 218)
WHITE = (244, 247, 251)
MUTED = (148, 163, 184)
BORDER = (51, 65, 85)
CYAN = (87, 211, 207)
AMBER = (245, 158, 11)
GREEN = (52, 211, 153)


@dataclass(slots=True)
class TextField:
    label: str
    value: str
    rect: pygame.Rect
    secret: bool = False
    active: bool = False

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            return self.active
        if not self.active or event.type != pygame.KEYDOWN:
            return False
        if event.key == pygame.K_BACKSPACE:
            self.value = self.value[:-1]
            return True
        if event.key in (pygame.K_RETURN, pygame.K_ESCAPE):
            self.active = False
            return True
        if event.key == pygame.K_TAB:
            return False
        if event.unicode and event.unicode.isprintable():
            self.value += event.unicode
            return True
        return False

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        label = font.render(self.label, True, MUTED)
        surface.blit(label, (self.rect.x, self.rect.y - 19))
        border = CYAN if self.active else BORDER
        pygame.draw.rect(surface, (15, 23, 34), self.rect, border_radius=5)
        pygame.draw.rect(surface, border, self.rect, width=1, border_radius=5)
        value = "*" * len(self.value) if self.secret and self.value else self.value
        clipped = _clip_text(value, font, self.rect.width - 14)
        surface.blit(font.render(clipped, True, WHITE), (self.rect.x + 7, self.rect.y + 7))


@dataclass(slots=True)
class CompetitionTrainingClient:
    settings: RuntimeSettings
    assets: GameAssets
    screen: pygame.Surface
    clock: pygame.time.Clock
    font: pygame.font.Font
    small_font: pygame.font.Font
    title_font: pygame.font.Font
    session: TrainingSession
    competition_id: CompetitionName = "easy"
    competition_map: CompetitionMap | None = None
    background: pygame.Surface | None = None
    collision: pygame.Surface | None = None
    cars: list[Car] | None = None
    aux_car: Car | None = None
    generated_result: ClientResult | None = None
    manual_override: bool = False
    status: str = "Ready. Train, press V to score, press U to submit."
    field_index: int = 0
    fitness_strategy: Any = None
    fields: list[TextField] = field(default_factory=list)
    result_fields: list[TextField] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fitness_strategy = get_fitness_strategy(self.session.fitness_strategy)
        self.fields = _build_fields(self.settings)
        self.result_fields = _build_result_fields()
        self.fields[0].active = True
        self.load_competition("easy", reset_weights=True)

    @property
    def all_fields(self) -> list[TextField]:
        return self.fields + self.result_fields

    @property
    def user_id(self) -> str:
        return self.fields[0].value.strip() or "player1"

    @property
    def group_id(self) -> str:
        return self.fields[1].value.strip() or "1"

    @property
    def server_url(self) -> str:
        return (self.fields[2].value.strip() or self.settings.server_url).rstrip("/")

    @property
    def admin_token(self) -> str:
        return self.fields[3].value.strip()

    def load_competition(self, competition_id: CompetitionName, *, reset_weights: bool) -> None:
        self.competition_id = competition_id
        self.competition_map = get_competition_map(competition_id)
        self.background = pygame.image.load(self.competition_map.front_path)
        self.collision = self.competition_map.build_collision_surface()
        set_collision_map(self.collision)
        configure_car(self.collision, self.assets.white_small_car, MAX_SPEED)
        if reset_weights or self.cars is None:
            self.cars = [Car(LAYER_SIZES) for _ in range(self.session.population_size)]
            self.aux_car = Car(LAYER_SIZES)
            self.session.reset_generation()
        self.reset_positions(reset_images=True)
        self.generated_result = None
        self.status = f"Loaded {competition_id.upper()} map."

    def reset_positions(self, *, reset_images: bool = False) -> None:
        if self.competition_map is None or self.collision is None or self.cars is None:
            return
        spawn = self.competition_map.spawn
        for car in self.cars:
            image = self.assets.white_small_car if reset_images else None
            car.reset_state(spawn["x"], spawn["y"], angle=spawn["angle"], car_image=image)
            car.set_collision_surface(self.collision)
            car.showlines = self.session.show_sensor_lines
        self.session.alive_count = len(self.cars)
        self.session.clear_selection()

    def run(self) -> None:
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    return
                self.handle_event(event)
            self.step()
            self.draw()
            self.clock.tick(self.settings.fps)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.handle_mouse(event)
            return
        if event.type != pygame.KEYDOWN:
            return
        key = event.key
        if self._handle_global_shortcut(key):
            return
        if self._handle_fields(event):
            return

    def _handle_global_shortcut(self, key: int) -> bool:
        if key == pygame.K_TAB:
            self.focus_next_field()
            return True
        elif key == pygame.K_e:
            self.load_competition("easy", reset_weights=False)
            return True
        elif key == pygame.K_h:
            self.load_competition("hard", reset_weights=False)
            return True
        elif key == pygame.K_f:
            self.load_competition("final", reset_weights=False)
            return True
        elif key == pygame.K_l:
            self.toggle_lines()
            return True
        elif key == pygame.K_c:
            self.clean_collided_cars()
            return True
        elif key == pygame.K_b:
            self.manual_breed()
            return True
        elif key == pygame.K_g:
            self.auto_breed()
            return True
        elif key == pygame.K_r:
            self.reset_population()
            return True
        elif key == pygame.K_o:
            self.manual_override = not self.manual_override
            mode = "manual override" if self.manual_override else "generated result"
            self.status = f"Result mode: {mode}."
            return True
        elif key == pygame.K_v:
            self.score_best_car()
            return True
        elif key == pygame.K_u:
            self.submit_best_car()
            return True
        elif key == pygame.K_p:
            self.run_batch_now()
            return True
        return False

    def _handle_fields(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_TAB:
            return False
        handled = False
        for index, text_field in enumerate(self.all_fields):
            if text_field.handle_event(event):
                self.field_index = index
                handled = True
        return handled

    def handle_mouse(self, event: pygame.event.Event) -> None:
        if self.cars is None or PANEL.collidepoint(event.pos):
            return
        point = Point(event.pos[0], event.pos[1])
        if event.button == 1:
            for car in self.cars:
                if Polygon([car.a, car.b, car.c, car.d]).contains(point):
                    self.toggle_selected_car(car)
                    return
        if event.button == 3:
            for car in list(self.cars):
                if Polygon([car.a, car.b, car.c, car.d]).contains(point):
                    self.remove_car(car)
                    return

    def focus_next_field(self) -> None:
        fields = self.all_fields
        fields[self.field_index].active = False
        self.field_index = (self.field_index + 1) % len(fields)
        fields[self.field_index].active = True

    def toggle_lines(self) -> None:
        self.session.show_sensor_lines = not self.session.show_sensor_lines
        if self.cars is not None:
            for car in self.cars:
                car.showlines = self.session.show_sensor_lines

    def toggle_selected_car(self, car: Car) -> None:
        was_selected = car in self.session.selected_cars
        self.session.toggle_selected_car(car)
        if was_selected:
            car.car_image = self.assets.white_small_car
        elif car in self.session.selected_cars:
            car.car_image = self.assets.white_big_car

    def remove_car(self, car: Car) -> None:
        if self.cars is None:
            return
        if car in self.session.selected_cars:
            self.session.selected_cars.remove(car)
        self.cars.remove(car)
        if not car.collided:
            self.session.alive_count = max(0, self.session.alive_count - 1)

    def clean_collided_cars(self) -> None:
        if self.cars is None:
            return
        self.cars = [car for car in self.cars if not car.collided]
        self.session.selected_cars = [
            car for car in self.session.selected_cars if car in self.cars
        ]
        self.session.alive_count = len([car for car in self.cars if not car.collided])
        self.status = f"Kept {len(self.cars)} cars."

    def manual_breed(self) -> None:
        if self.cars is None or self.aux_car is None:
            return
        before = self.session.generation
        self.cars = self.session.breed_population(
            population=self.cars,
            aux_car=self.aux_car,
            car_factory=Car,
            layer_sizes=LAYER_SIZES,
            assets=self.assets,
        )
        if self.session.generation == before:
            self.status = "Select exactly two cars before manual breed."
            return
        self.reset_positions(reset_images=False)
        self.status = f"Generation {self.session.generation}: manual breed."

    def auto_breed(self) -> None:
        if self.cars is None or len(self.cars) < 2:
            self.status = "Need at least two cars to auto-breed."
            return
        ranked = sorted(self.cars, key=rank_car, reverse=True)
        self.session.selected_cars = ranked[:2]
        self.manual_breed()
        self.status = f"Generation {self.session.generation}: auto-bred top two cars."

    def reset_population(self) -> None:
        self.cars = [Car(LAYER_SIZES) for _ in range(self.session.population_size)]
        self.aux_car = Car(LAYER_SIZES)
        self.session.reset_generation()
        self.reset_positions(reset_images=True)
        self.generated_result = None
        self.status = "Population reset."

    def best_car(self) -> Car | None:
        if not self.cars:
            return None
        return max(self.cars, key=rank_car)

    def score_best_car(self) -> None:
        best = self.best_car()
        if best is None:
            self.status = "No cars to score."
            return
        try:
            self.generated_result = evaluate_car_result(best, self.competition_id)
        except ValueError as exc:
            self.status = f"Scoring failed: {exc}"
            return
        self._sync_result_fields(self.generated_result)
        self.status = "Generated client_result from best car."

    def current_client_result(self) -> ClientResult:
        if self.manual_override:
            return build_manual_client_result(
                completed=self.result_fields[0].value,
                lap_ticks=self.result_fields[1].value,
                max_progress=self.result_fields[2].value,
                ticks_to_max_progress=self.result_fields[3].value,
            )
        if self.generated_result is None:
            self.score_best_car()
        if self.generated_result is None:
            raise ValueError("no generated client_result available")
        return self.generated_result

    def submit_best_car(self) -> None:
        best = self.best_car()
        if best is None:
            self.status = "No cars to submit."
            return
        try:
            eligibility = _check_eligibility_raw(
                self.server_url,
                self.competition_id,
                group_id=self.group_id,
                username=self.user_id,
            )
            if not eligibility.get("eligible"):
                reason = eligibility.get("reason", "not eligible")
                next_at = eligibility.get("next_submission_at", "")
                self.status = f"Not eligible: {reason} {next_at}"
                return
            result = self.current_client_result()
            submission = submit_car(
                server_url=self.server_url,
                car=best,
                group_id=self.group_id,
                username=self.user_id,
                competition_id=self.competition_id,
                client_result=result,
                timeout=8.0,
            )
        except (ValueError, HTTPError, URLError, TimeoutError) as exc:
            self.status = f"Submit failed: {exc}"
            return
        self.status = submission.message

    def run_batch_now(self) -> None:
        if not self.admin_token:
            self.status = "Admin token required to run batch now."
            return
        try:
            response = post_admin(
                self.server_url,
                "/v2/admin/batches/run-now",
                token=self.admin_token,
            )
        except (HTTPError, URLError, ValueError, TimeoutError) as exc:
            self.status = f"Run batch failed: {exc}"
            return
        self.status = f"Batch processed {response.get('processed', 0)} submissions."

    def _sync_result_fields(self, result: ClientResult) -> None:
        self.result_fields[0].value = "true" if result.completed else "false"
        self.result_fields[1].value = "" if result.lap_ticks is None else str(result.lap_ticks)
        self.result_fields[2].value = f"{result.max_progress:.1f}"
        self.result_fields[3].value = str(result.ticks_to_max_progress)

    def step(self) -> None:
        if self.cars is None:
            return
        for car in self.cars:
            if car.collided:
                continue
            try:
                car.update()
                if car.collision():
                    car.collided = True
                    setattr(car, "fitness_score", self.fitness_strategy(car))
                    self.session.mark_collision(car)
                    continue
                car.feedforward()
                car.takeAction()
            except (IndexError, pygame.error):
                car.collided = True
                setattr(car, "fitness_score", self.fitness_strategy(car))
                self.session.mark_collision(car)

    def draw(self) -> None:
        self.screen.fill(BG)
        if self.background is not None:
            self.screen.blit(self.background, (0, 0))
        if self.cars is not None:
            for car in self.cars:
                car.draw(self.screen)
        self._draw_panel()
        pygame.display.flip()

    def _draw_panel(self) -> None:
        overlay = pygame.Surface((PANEL.width, PANEL.height), pygame.SRCALPHA)
        overlay.fill(PANEL_BG)
        self.screen.blit(overlay, PANEL.topleft)
        pygame.draw.rect(self.screen, BORDER, PANEL, width=1, border_radius=8)
        self._text("Competition Test Main", PANEL.x + 18, PANEL.y + 18, self.title_font)
        self._text(
            f"Map: {self.competition_id.upper()}   Gen: {self.session.generation}",
            PANEL.x + 18,
            PANEL.y + 58,
            self.font,
            CYAN if self.competition_id == "easy" else AMBER,
        )
        alive = self.session.alive_count
        total = len(self.cars or [])
        selected = len(self.session.selected_cars)
        self._text(
            f"Cars {total}  Alive {alive}  Selected {selected}",
            PANEL.x + 18,
            PANEL.y + 84,
            self.small_font,
            MUTED,
        )
        for text_field in self.fields:
            text_field.draw(self.screen, self.small_font)
        y = PANEL.y + 246
        self._text("Shortcuts", PANEL.x + 18, y, self.font)
        shortcuts = [
            "E/H/F map   L lines   R reset",
            "LMB select   RMB remove   C clean",
            "B breed selected   G auto-breed",
            "V score best   O manual result",
            "U submit best   P run batch now",
            "Tab moves between fields",
        ]
        for index, text in enumerate(shortcuts):
            self._text(text, PANEL.x + 18, y + 28 + index * 20, self.small_font, MUTED)
        y += 172
        mode = "Manual override" if self.manual_override else "Generated result"
        self._text(f"client_result: {mode}", PANEL.x + 18, y, self.font, GREEN)
        for text_field in self.result_fields:
            text_field.draw(self.screen, self.small_font)
        y += 190
        result = self.current_result_preview()
        self._text(result, PANEL.x + 18, y, self.small_font, WHITE)
        status_rect = pygame.Rect(PANEL.x + 18, PANEL.y + PANEL.height - 112, 430, 84)
        _draw_wrapped(self.screen, self.small_font, self.status, status_rect, WHITE)

    def current_result_preview(self) -> str:
        try:
            result = self.current_client_result() if self.manual_override else self.generated_result
        except ValueError as exc:
            return f"Invalid manual result: {exc}"
        if result is None:
            return "Press V to generate a client_result."
        if result.completed:
            return f"completed lap_ticks={result.lap_ticks}"
        return f"incomplete progress={result.max_progress:.1f} tick={result.ticks_to_max_progress}"

    def _text(
        self,
        text: str,
        x: int,
        y: int,
        font: pygame.font.Font,
        color: tuple[int, int, int] = WHITE,
    ) -> None:
        self.screen.blit(font.render(text, True, color), (x, y))


def run(server_url: str | None = None) -> None:
    pygame.init()
    settings = load_runtime_settings()
    if server_url is not None:
        settings.server_url = server_url
    elif os.environ.get("COMPETITION_SERVER_URL"):
        settings.server_url = str(os.environ["COMPETITION_SERVER_URL"])
    screen = pygame.display.set_mode(SCREEN_SIZE)
    pygame.display.set_caption("Neural Cars Competition Test Main")
    client = CompetitionTrainingClient(
        settings=settings,
        assets=load_game_assets(),
        screen=screen,
        clock=pygame.time.Clock(),
        font=pygame.font.SysFont("Arial", 18),
        small_font=pygame.font.SysFont("Arial", 15),
        title_font=pygame.font.SysFont("Arial", 26, bold=True),
        session=TrainingSession.from_settings(settings),
    )
    client.run()


def evaluate_car_result(car: Car, competition_id: CompetitionName) -> ClientResult:
    competition_map = get_competition_map(competition_id)
    tracker = CompetitionRunTracker.from_metadata_path(competition_map.metadata_path)
    test_car = Car(LAYER_SIZES)
    test_car.weights = [layer.copy() for layer in car.weights]
    test_car.biases = [layer.copy() for layer in car.biases]
    collision = competition_map.build_collision_surface()
    test_car.set_collision_surface(collision)
    spawn = competition_map.spawn
    test_car.reset_state(spawn["x"], spawn["y"], angle=spawn["angle"])

    max_progress = 0.0
    ticks_to_max_progress = 0
    for tick in range(FRAME_LIMIT):
        previous = (float(test_car.x), float(test_car.y))
        try:
            test_car.update()
            if test_car.collision():
                break
            current = (float(test_car.x), float(test_car.y))
            tracker.advance(previous, current, tick=tick + 1)
            if tracker.completed:
                return ClientResult(
                    completed=True,
                    lap_ticks=tracker.lap_ticks,
                    max_progress=tracker.max_progress,
                    ticks_to_max_progress=tracker.ticks_to_max_progress,
                )
            test_car.feedforward()
            test_car.takeAction()
        except (IndexError, pygame.error):
            break
        progress = tracker.max_progress
        if progress >= max_progress:
            max_progress = progress
            ticks_to_max_progress = tracker.ticks_to_max_progress
    return ClientResult(
        completed=False,
        lap_ticks=None,
        max_progress=max_progress,
        ticks_to_max_progress=ticks_to_max_progress,
    )


def build_manual_client_result(
    *,
    completed: str,
    lap_ticks: str,
    max_progress: str,
    ticks_to_max_progress: str,
) -> ClientResult:
    is_completed = parse_bool(completed)
    lap_value = None if not lap_ticks.strip() else int(lap_ticks)
    return ClientResult.from_dict(
        {
            "completed": is_completed,
            "lap_ticks": lap_value,
            "max_progress": float(max_progress),
            "ticks_to_max_progress": int(ticks_to_max_progress),
        }
    )


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "t", "yes", "y", "completed"}:
        return True
    if lowered in {"0", "false", "f", "no", "n", "incomplete", ""}:
        return False
    raise ValueError("completed must be true or false")


def rank_car(car: Car) -> float:
    return float(getattr(car, "fitness_score", getattr(car, "score", 0.0)))


def _check_eligibility_raw(
    server_url: str,
    competition_id: CompetitionName,
    *,
    group_id: str,
    username: str,
) -> dict[str, Any]:
    body = {"group_id": group_id, "username": username}
    if competition_id == "final":
        path = "/v2/finals/eligibility"
    else:
        path = f"/v2/competitions/{competition_id}/eligibility"
    return post_json(server_url.rstrip("/") + path, body)


def _post_json(
    url: str,
    payload: dict[str, Any],
    timeout: float = 10.0,
) -> tuple[int, dict[str, Any]] | NetworkError:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            body = json.loads(raw.decode("utf-8")) if raw else {}
            return response.status, body
    except HTTPError as exc:
        raw = exc.read()
        body = json.loads(raw.decode("utf-8")) if raw else {}
        return exc.code, body
    except (URLError, TimeoutError, ConnectionError, OSError) as exc:
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
    server_url: str,
    competition_id: str,
    group_id: str,
    username: str,
) -> EligibilityResult | NetworkError:
    url = f"{server_url.rstrip('/')}{_eligibility_path(competition_id)}"
    result = _post_json(
        url,
        {"group_id": group_id, "username": username},
    )
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
        competition_config_version=str(
            body.get("competition_config_version", "")
        ),
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
    if status in (409, 429):
        return SubmissionRejected(
            error=str(response_body.get("error", "rejected")),
            next_submission_at=response_body.get("next_submission_at"),
        )
    return NetworkError(message=f"server 回應非預期狀態碼: {status}")


def post_admin(server_url: str, path: str, *, token: str) -> dict[str, Any]:
    request = Request(
        server_url.rstrip("/") + path,
        data=b"",
        headers={"X-Admin-Token": token},
        method="POST",
    )
    try:
        with urlopen(request, timeout=8.0) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError(f"HTTP {exc.code}: {detail}") from exc


def post_json(url: str, body: dict[str, Any]) -> dict[str, Any]:
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


def _build_fields(settings: RuntimeSettings) -> list[TextField]:
    x = PANEL.x + 18
    y = PANEL.y + 130
    server_url = os.environ.get("COMPETITION_SERVER_URL", settings.server_url)
    admin_token = os.environ.get("COMPETITION_ADMIN_TOKEN", "admin")
    return [
        TextField("User ID", settings.username, pygame.Rect(x, y, FIELD_W, FIELD_H)),
        TextField("Group ID", settings.group_id, pygame.Rect(x + 250, y, 178, FIELD_H)),
        TextField("Server URL", server_url, pygame.Rect(x, y + 58, 428, FIELD_H)),
        TextField("Admin Token", admin_token, pygame.Rect(x, y + 116, 428, FIELD_H), True),
    ]


def _build_result_fields() -> list[TextField]:
    x = PANEL.x + 18
    y = PANEL.y + 470
    return [
        TextField("Completed", "false", pygame.Rect(x, y, 118, FIELD_H)),
        TextField("Lap Ticks", "", pygame.Rect(x + 132, y, 118, FIELD_H)),
        TextField("Max Progress", "0.0", pygame.Rect(x, y + 58, 170, FIELD_H)),
        TextField("Ticks To Max", "0", pygame.Rect(x + 184, y + 58, 170, FIELD_H)),
    ]


def _clip_text(text: str, font: pygame.font.Font, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text
    clipped = text
    while clipped and font.size("..." + clipped)[0] > max_width:
        clipped = clipped[1:]
    return "..." + clipped


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
            screen.blit(font.render(line, True, color), (rect.x, y))
            y += font.get_linesize()
            line = word
        else:
            line = candidate
    if line:
        screen.blit(font.render(line, True, color), (rect.x, y))


__all__ = [
    "EligibilityResult",
    "NetworkError",
    "SubmissionAccepted",
    "SubmissionRejected",
    "build_manual_client_result",
    "check_eligibility",
    "evaluate_car_result",
    "parse_bool",
    "run",
    "submit",
]
