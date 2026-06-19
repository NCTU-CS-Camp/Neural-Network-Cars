from __future__ import annotations

from typing import Literal

import pygame

from GA.fitness import FITNESS_STRATEGIES, score_with_config
from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car, configure_car
from game_engine.backend.record_store import RecordStore
from game_engine.backend.serialization import apply_weight_payload
from game_engine.backend.settings import (
    BLACK,
    MAX_SPEED,
    TRAINING_DIFFICULTY_MAPS,
    VALIDATION_DIFFICULTY_MAPS,
    WHITE,
)
from game_engine.frontend.profile_store import save_login_profile
from game_engine.frontend.widgets import Button, Slider, TextInput
from shared.contracts import FitnessConfig, LoginProfile, TrainingRecord, WeightPayload


class AppQuit(Exception):
    """Raised when the user closes the window from within a blocking screen."""


GROUP_COUNT = 10
MenuChoice = Literal["training", "validation"]
TrainingConfigResult = tuple[FitnessConfig, int]


def _font(size: int = 22) -> pygame.font.Font:
    return pygame.font.Font("freesansbold.ttf", size)


def _check_quit(event: pygame.event.Event) -> None:
    if event.type == pygame.QUIT:
        raise AppQuit()


def _fitness_summary(fitness_config: FitnessConfig) -> str:
    return "  ".join(f"{name}:{value}" for name, value in fitness_config.weights.items())


def run_login_screen(screen: pygame.Surface) -> LoginProfile:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(36)

    group_buttons = [
        Button(str(group_id), pygame.Rect(60 + (group_id - 1) * 70, 220, 56, 56))
        for group_id in range(1, GROUP_COUNT + 1)
    ]
    selected_group: str | None = None
    name_input = TextInput(pygame.Rect(60, 340, 360, 48))
    register_button = Button("註冊", pygame.Rect(60, 420, 160, 52))
    error_message = ""

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            name_input.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                for button in group_buttons:
                    if button.contains(event.pos):
                        selected_group = button.text
                if register_button.contains(event.pos):
                    username = name_input.text.strip()
                    if selected_group is None or not username:
                        error_message = "請選擇組別並輸入名字"
                    else:
                        profile = LoginProfile(group_id=selected_group, username=username)
                        save_login_profile(profile)
                        return profile

        mouse_pos = pygame.mouse.get_pos()
        for button in group_buttons:
            button.update_hover(mouse_pos)
            button.fill_color = (60, 120, 200) if button.text == selected_group else (30, 30, 30)
        register_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render("登入", True, WHITE), (60, 140))
        screen.blit(font.render("選擇組別 (1-10)", True, WHITE), (60, 190))
        for button in group_buttons:
            button.draw(screen, font)
        screen.blit(font.render("輸入名字", True, WHITE), (60, 312))
        name_input.draw(screen, font)
        register_button.draw(screen, font)
        if error_message:
            screen.blit(font.render(error_message, True, (255, 90, 90)), (60, 488))

        pygame.display.update()
        clock.tick(30)


def run_main_menu_screen(screen: pygame.Surface, profile: LoginProfile) -> MenuChoice:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(36)
    width, height = screen.get_size()

    training_button = Button(
        "Training", pygame.Rect(width // 2 - 360, height // 2 - 100, 320, 200)
    )
    validation_button = Button(
        "Validation", pygame.Rect(width // 2 + 40, height // 2 - 100, 320, 200)
    )

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if training_button.contains(event.pos):
                    return "training"
                if validation_button.contains(event.pos):
                    return "validation"

        mouse_pos = pygame.mouse.get_pos()
        training_button.update_hover(mouse_pos)
        validation_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(
            title_font.render(f"歡迎, {profile.username} (組 {profile.group_id})", True, WHITE),
            (60, 60),
        )
        training_button.draw(screen, font)
        validation_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def run_training_config_screen(screen: pygame.Surface) -> TrainingConfigResult:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    strategy_names = list(FITNESS_STRATEGIES.keys())
    sliders = {
        name: Slider(pygame.Rect(280, 160 + index * 60, 320, 12), 0, 100, 50)
        for index, name in enumerate(strategy_names)
    }

    difficulty_options = [
        (
            difficulty,
            Button("*" * difficulty, pygame.Rect(60 + (difficulty - 1) * 140, 440, 120, 60)),
        )
        for difficulty in TRAINING_DIFFICULTY_MAPS
    ]
    selected_difficulty = difficulty_options[0][0]

    go_button = Button("Go", pygame.Rect(width - 220, height - 100, 160, 60))

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            for slider in sliders.values():
                slider.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                for difficulty, button in difficulty_options:
                    if button.contains(event.pos):
                        selected_difficulty = difficulty
                if go_button.contains(event.pos):
                    fitness_config = FitnessConfig(
                        weights={name: slider.value for name, slider in sliders.items()}
                    )
                    return fitness_config, selected_difficulty

        mouse_pos = pygame.mouse.get_pos()
        for difficulty, button in difficulty_options:
            button.update_hover(mouse_pos)
            button.fill_color = (60, 120, 200) if difficulty == selected_difficulty else (30, 30, 30)
        go_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render("Training 設定", True, WHITE), (60, 60))
        screen.blit(font.render("Fitness 權重（佔位分類，之後會替換成真正類別）", True, WHITE), (60, 120))
        for name, slider in sliders.items():
            screen.blit(font.render(name, True, WHITE), (60, slider.rect.y - 4))
            slider.draw(screen, font)
        screen.blit(
            font.render("難度地圖（Training 專用地圖池，與 Validate 地圖池分開）", True, WHITE),
            (60, 400),
        )
        for _, button in difficulty_options:
            button.draw(screen, font)
        go_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def run_save_confirm_screen(screen: pygame.Surface) -> bool:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    yes_button = Button("存檔", pygame.Rect(width // 2 - 180, height // 2, 160, 60))
    no_button = Button("不存", pygame.Rect(width // 2 + 20, height // 2, 160, 60))

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if yes_button.contains(event.pos):
                    return True
                if no_button.contains(event.pos):
                    return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        mouse_pos = pygame.mouse.get_pos()
        yes_button.update_hover(mouse_pos)
        no_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(
            title_font.render("要儲存這次訓練結果嗎？", True, WHITE),
            (width // 2 - 260, height // 2 - 80),
        )
        yes_button.draw(screen, font)
        no_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def run_record_name_screen(screen: pygame.Surface) -> str:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    name_input = TextInput(pygame.Rect(width // 2 - 200, height // 2, 400, 48))
    name_input.active = True
    confirm_button = Button("確認", pygame.Rect(width // 2 - 80, height // 2 + 80, 160, 56))

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            name_input.handle_event(event)
            if event.type == pygame.MOUSEBUTTONDOWN and confirm_button.contains(event.pos):
                if name_input.text.strip():
                    return name_input.text.strip()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_RETURN:
                if name_input.text.strip():
                    return name_input.text.strip()

        mouse_pos = pygame.mouse.get_pos()
        confirm_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(
            title_font.render("幫這筆紀錄命名", True, WHITE), (width // 2 - 200, height // 2 - 80)
        )
        name_input.draw(screen, font)
        confirm_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def run_validation_list_screen(screen: pygame.Surface) -> None:
    clock = pygame.time.Clock()
    font = _font(18)
    title_font = _font(32)
    width, height = screen.get_size()
    store = RecordStore()

    back_button = Button("返回", pygame.Rect(60, 40, 120, 48))
    row_height = 64
    list_top = 140
    message = ""

    while True:
        records = store.list_records()

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)

        rows = []
        for index, record in enumerate(records):
            row_y = list_top + index * row_height
            validate_button = Button("Validate", pygame.Rect(width - 420, row_y, 110, 44))
            upload_button = Button("Upload", pygame.Rect(width - 300, row_y, 110, 44))
            delete_button = Button("Delete", pygame.Rect(width - 180, row_y, 110, 44))
            validate_button.update_hover(mouse_pos)
            upload_button.update_hover(mouse_pos)
            delete_button.update_hover(mouse_pos)
            rows.append((record, validate_button, upload_button, delete_button))

        hovered_row = next((row for row in rows if row[1].hovered), None)
        difficulty_buttons: list[tuple[int, Button]] = []
        if hovered_row is not None:
            validate_button = hovered_row[1]
            difficulty_buttons = [
                (
                    difficulty,
                    Button(
                        "*" * difficulty,
                        pygame.Rect(
                            validate_button.rect.x,
                            validate_button.rect.bottom + 6 + offset * 46,
                            validate_button.rect.width,
                            40,
                        ),
                    ),
                )
                for offset, difficulty in enumerate(VALIDATION_DIFFICULTY_MAPS)
            ]
            for _, button in difficulty_buttons:
                button.update_hover(mouse_pos)

        for event in pygame.event.get():
            _check_quit(event)
            if event.type != pygame.MOUSEBUTTONDOWN:
                continue
            if back_button.contains(event.pos):
                return
            if hovered_row is not None:
                clicked_difficulty = next(
                    (
                        difficulty
                        for difficulty, button in difficulty_buttons
                        if button.contains(event.pos)
                    ),
                    None,
                )
                if clicked_difficulty is not None:
                    run_validate_replay_screen(screen, hovered_row[0], clicked_difficulty)
                    continue
            for record, validate_button, upload_button, delete_button in rows:
                if upload_button.contains(event.pos):
                    message = f"{record.record_name} 已加入上傳佇列（尚未啟用）"
                elif delete_button.contains(event.pos):
                    store.delete_record(record.record_id)
                    message = f"已刪除 {record.record_name}"

        screen.fill(BLACK)
        screen.blit(title_font.render("Validation", True, WHITE), (60, 60))
        back_button.draw(screen, font)
        for record, validate_button, upload_button, delete_button in rows:
            info = (
                f"{record.record_name}  |  {record.saved_at}  |  "
                f"{_fitness_summary(record.fitness_config)}"
            )
            screen.blit(font.render(info, True, WHITE), (60, validate_button.rect.y + 12))
            validate_button.draw(screen, font)
            upload_button.draw(screen, font)
            delete_button.draw(screen, font)
        if hovered_row is not None:
            for _, button in difficulty_buttons:
                button.draw(screen, font)
        if message:
            screen.blit(font.render(message, True, (120, 220, 120)), (60, height - 60))

        pygame.display.update()
        clock.tick(30)


def run_validate_replay_screen(
    screen: pygame.Surface, record: TrainingRecord, difficulty: int
) -> None:
    clock = pygame.time.Clock()
    font = _font(20)

    front_path, back_path = VALIDATION_DIFFICULTY_MAPS[difficulty]
    track_front = pygame.image.load(front_path)
    track_back = pygame.image.load(back_path)
    assets = load_game_assets()
    configure_car(track_back, assets.white_small_car, MAX_SPEED)

    car = Car(record.layer_sizes)
    payload = WeightPayload(
        model_version="v1",
        layer_sizes=record.layer_sizes,
        weights=record.weights,
        biases=record.biases,
        fitness_score=0.0,
        generation=0,
        track_id=f"validation-{difficulty}",
        track_seed=0,
        nickname=record.username,
    )
    apply_weight_payload(car, payload)

    finished = False
    final_score = 0.0
    back_button = Button("返回列表", pygame.Rect(60, 40, 160, 48))

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEBUTTONDOWN and finished and back_button.contains(event.pos):
                return

        if not finished:
            car.update()
            if car.collision():
                finished = True
                final_score = score_with_config(car, record.fitness_config)
            else:
                car.feedforward()
                car.takeAction()

        screen.blit(track_front, (0, 0))
        car.draw(screen)
        if finished:
            screen.blit(font.render(f"Score: {final_score:.2f}", True, WHITE), (60, 100))
            back_button.update_hover(pygame.mouse.get_pos())
            back_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)
