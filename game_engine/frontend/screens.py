from __future__ import annotations

import json
from typing import Any, Literal

import pygame

from GA.fitness import (
    BeginnerMix,
    FitnessStrategy,
    fitness_strategy_names,
    get_fitness_strategy,
)
from GA.genetic import (
    mutateOneBiasesGene,
    mutateOneWeightGene,
    uniformCrossOverBiases,
    uniformCrossOverWeights,
)
from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import DEFAULT_MLP_INIT_SEED, Car, configure_car
from game_engine.backend.competition_maps import load_competition_map, load_validation_map
from game_engine.backend.competition_track import (
    CompetitionRunTracker,
    reconstruct_route_cells,
)
from game_engine.backend.record_store import RecordStore
from game_engine.backend.serialization import apply_weight_payload, export_weight_payload
from game_engine.backend.settings import (
    BLACK,
    FONT_PATH,
    FPS,
    MAX_SPEED,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    TRACK_METADATA_PATH,
    TRAINING_DIFFICULTY_MAPS,
    VALIDATION_DIFFICULTY_MAPS,
    VALIDATION_FRAME_LIMIT,
    WHITE,
)
from game_engine.backend.track_generator import generate_random_map
from game_engine.backend.track_layout import (
    BLOCK_SIZE,
    TrackLayout,
    build_boundary_checkpoints,
)
from game_engine.backend.training_session import create_evolution_rngs
from game_engine.frontend.competition_client import (
    EligibilityResult,
    NetworkError,
    SubmissionAccepted,
    SubmissionRejected,
    check_eligibility,
)
from game_engine.frontend.competition_client import submit as submit_to_competition_server
from game_engine.frontend.profile_store import save_login_profile
from game_engine.frontend.widgets import Button, Dropdown, Slider, TextInput
from shared.contracts import (
    ClientResult,
    FitnessConfig,
    LoginProfile,
    SubmissionPayload,
    TrainingRecord,
    WeightPayload,
)


# Mirrors Competition Server's server/competition_config.py::FRAME_LIMIT. Kept
# as a plain constant here since the client does not depend on the server package.
FRAME_LIMIT = 900

_REASON_MESSAGES = {
    "submission_cooldown": "冷卻中，請稍後再試",
    "competition_closed": "目前未開放提交",
    "final_locked": "Final 已提交過或已鎖定",
}

# Deliberately low: uploading an already-trained record should mostly resubmit
# that record's car, not breed something new from it.
UPLOAD_MUTATION_RATE = 5
SUBMISSION_POPULATION_SIZE = 100

# Validation breeds a fresh generation from the record's two parents to probe
# generalization, so it mutates more aggressively than the upload resubmit path.
VALIDATION_MUTATION_RATE = 15
VALIDATION_POPULATION_SIZE = 100
VALID_FITNESS_INPUT_COLOR = (90, 90, 90)
INVALID_FITNESS_INPUT_COLOR = (255, 90, 90)


class AppQuit(Exception):
    """Raised when the user closes the window from within a blocking screen."""


GROUP_COUNT = 10
MenuChoice = Literal["training", "validation", "clear_user"]
TrainingConfigResult = tuple[FitnessStrategy, int, TrainingRecord | None, int]

BONUS_FITNESS_PLACEHOLDERS = [
    "speed",
    "progress",
    "centered",
    "alignment",
    "safety",
]

PENALTY_FITNESS_PLACEHOLDERS = [
    "stall",
    "spin",
    "wrong_way",
    "time",
    "crash",
]


def _font(size: int = 22) -> pygame.font.Font:
    return pygame.font.Font(str(FONT_PATH), size)


def _check_quit(event: pygame.event.Event) -> None:
    if event.type == pygame.QUIT:
        raise AppQuit()


def _fitness_summary(fitness_config: FitnessConfig) -> str:
    return "  ".join(f"{name}:{value}" for name, value in fitness_config.weights.items())


def _ellipsize(font: pygame.font.Font, text: str, max_width: int) -> str:
    if font.size(text)[0] <= max_width:
        return text
    suffix = "…"
    while text and font.size(text + suffix)[0] > max_width:
        text = text[:-1]
    return text + suffix


def format_ticks_as_seconds(ticks: int | None, fps: int = FPS) -> str:
    if ticks is None:
        return "--"
    return f"{ticks / fps:.1f} 秒"


def run_login_screen(screen: pygame.Surface, server_url: str) -> LoginProfile:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(36)

    group_buttons = [
        Button(str(group_id), pygame.Rect(60 + (group_id - 1) * 70, 220, 56, 56))
        for group_id in range(1, GROUP_COUNT + 1)
    ]
    selected_group: str | None = None
    name_input = TextInput(pygame.Rect(60, 340, 360, 48))
    register_button = Button("註冊", pygame.Rect(60, 430, 160, 52))
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
                        profile = LoginProfile(
                            group_id=selected_group, username=username, server_url=server_url
                        )
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
            screen.blit(font.render(error_message, True, (255, 90, 90)), (60, 500))

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
    clear_user_button = Button(
        "清除使用者資料",
        pygame.Rect(width // 2 - 160, height // 2 + 140, 320, 56),
        fill_color=(100, 30, 30),
        hover_color=(145, 40, 40),
        border_color=(190, 70, 70),
    )

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if training_button.contains(event.pos):
                    return "training"
                if validation_button.contains(event.pos):
                    return "validation"
                if clear_user_button.contains(event.pos):
                    return "clear_user"

        mouse_pos = pygame.mouse.get_pos()
        training_button.update_hover(mouse_pos)
        validation_button.update_hover(mouse_pos)
        clear_user_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(
            title_font.render(f"歡迎, {profile.username} (組 {profile.group_id})", True, WHITE),
            (60, 60),
        )
        training_button.draw(screen, font)
        validation_button.draw(screen, font)
        clear_user_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def run_clear_user_confirm_screen(screen: pygame.Surface) -> bool:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    confirm_button = Button(
        "確認清除",
        pygame.Rect(width // 2 - 180, height // 2 + 60, 160, 56),
        fill_color=(110, 30, 30),
        hover_color=(155, 40, 40),
        border_color=(200, 70, 70),
    )
    cancel_button = Button(
        "取消",
        pygame.Rect(width // 2 + 20, height // 2 + 60, 160, 56),
    )

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if confirm_button.contains(event.pos):
                    return True
                if cancel_button.contains(event.pos):
                    return False

        mouse_pos = pygame.mouse.get_pos()
        confirm_button.update_hover(mouse_pos)
        cancel_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        title = title_font.render("確定要清除使用者資料？", True, WHITE)
        warning = font.render(
            "profile 與所有本機訓練紀錄都會刪除，且無法復原。",
            True,
            (255, 120, 120),
        )
        screen.blit(title, title.get_rect(center=(width // 2, height // 2 - 50)))
        screen.blit(
            warning,
            warning.get_rect(center=(width // 2, height // 2)),
        )
        confirm_button.draw(screen, font)
        cancel_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def run_training_config_screen(
    screen: pygame.Surface,
    default_max_speed: int = MAX_SPEED,
) -> TrainingConfigResult | None:
    clock = pygame.time.Clock()
    W, H = screen.get_size()

    font = _font(max(14, H // 50))
    title_font = _font(max(16, H // 40))
    subtitle_font = _font(max(15, H // 45))

    M = max(16, W // 100)          # base margin
    left_w = W * 2 // 3            # left 2/3
    right_x = left_w               # right block starts
    right_w = W - right_x          # right 1/3
    map_bottom = H * 2 // 5        # top 2/5 → map cards
    record_y = map_bottom           # bottom 3/5 → record section

    back_button = Button("← 返回", pygame.Rect(M, M, max(100, W // 14), max(36, H // 24)))
    max_speed_input = TextInput(
        pygame.Rect(left_w - M - max(64, W // 24), M, max(64, W // 24), back_button.rect.height),
        text=str(max(5, min(30, default_max_speed))),
        max_length=2,
        allowed_characters="0123456789",
        clear_on_focus=True,
    )

    # Map cards (left 2/3, top 2/5)
    card_area_top = back_button.rect.bottom + M
    card_area_h = map_bottom - card_area_top - M
    CARD_W = (left_w - M * 4) // 3
    CARD_H = card_area_h
    THUMB_W = CARD_W - M * 2
    THUMB_H = THUMB_W * 9 // 16
    easy_thumb = pygame.transform.scale(
        pygame.image.load(str(TRAINING_DIFFICULTY_MAPS[1][0])), (THUMB_W, THUMB_H)
    )
    hard_thumb = pygame.transform.scale(
        pygame.image.load(str(TRAINING_DIFFICULTY_MAPS[2][0])), (THUMB_W, THUMB_H)
    )
    map_cards: list[tuple[int, str, pygame.Surface | None, pygame.Rect]] = [
        (1, "Easy",   easy_thumb, pygame.Rect(M + i * (CARD_W + M), card_area_top, CARD_W, CARD_H))
        for i in range(3)
    ][0:1] + [
        (2, "Hard",   hard_thumb, pygame.Rect(M + 1 * (CARD_W + M), card_area_top, CARD_W, CARD_H)),
        (3, "隨機",   None,       pygame.Rect(M + 2 * (CARD_W + M), card_area_top, CARD_W, CARD_H)),
    ]
    map_cards = [
        (1, "Easy",   easy_thumb, pygame.Rect(M,                   card_area_top, CARD_W, CARD_H)),
        (2, "Hard",   hard_thumb, pygame.Rect(M * 2 + CARD_W,     card_area_top, CARD_W, CARD_H)),
        (3, "隨機",   None,       pygame.Rect(M * 3 + CARD_W * 2, card_area_top, CARD_W, CARD_H)),
    ]
    selected_difficulty: int = 1

    # Fitness preset, sliders, and numeric inputs (right 1/3, full height)
    slider_label_x = right_x + M
    slider_label_w = max(100, right_w // 5)
    value_input_w = max(56, right_w // 10)
    control_gap = max(10, M // 2)
    slider_x = slider_label_x + slider_label_w
    slider_right = W - M - value_input_w - control_gap
    slider_w = max(80, slider_right - slider_x)
    fitness_top = back_button.rect.bottom + M
    fitness_bottom = H - M
    dropdown_h = max(34, H // 26)
    selected_strategy = BeginnerMix.copy()
    preset_dropdown = Dropdown(
        pygame.Rect(right_x + M, fitness_top, right_w - M * 2, dropdown_h),
        fitness_strategy_names(),
        placeholder="載入 Fitness preset",
        selected=selected_strategy.name,
    )
    sliders_top = preset_dropdown.rect.bottom + M // 2
    fitness_step = (fitness_bottom - sliders_top) // 10
    slider_track_height = max(12, min(18, fitness_step // 4))
    slider_handle_radius = max(16, min(20, fitness_step // 3))
    value_input_h = max(30, min(38, fitness_step - 8))

    def slider_for_row(row: int, value: int) -> Slider:
        center_y = sliders_top + row * fitness_step + fitness_step // 2
        return Slider(
            pygame.Rect(
                slider_x,
                center_y - slider_track_height // 2,
                slider_w,
                slider_track_height,
            ),
            0,
            100,
            value,
            handle_radius=slider_handle_radius,
            show_value=False,
        )

    bonus_sliders = {
        name: slider_for_row(i, int(selected_strategy.config.get_weight(name)))
        for i, name in enumerate(BONUS_FITNESS_PLACEHOLDERS)
    }
    penalty_sliders = {
        name: slider_for_row(
            5 + i,
            int(selected_strategy.config.get_weight(name)),
        )
        for i, name in enumerate(PENALTY_FITNESS_PLACEHOLDERS)
    }
    all_sliders = {**bonus_sliders, **penalty_sliders}
    value_inputs = {
        name: TextInput(
            pygame.Rect(
                slider.rect.right + control_gap,
                slider.rect.centery - value_input_h // 2,
                value_input_w,
                value_input_h,
            ),
            text=str(slider.value),
            max_length=3,
            allowed_characters="0123456789",
            clear_on_focus=True,
        )
        for name, slider in all_sliders.items()
    }

    # Record section (left 2/3, bottom 3/5)
    records = RecordStore().list_records()
    record_title_y = record_y + M
    rec_btn_y = record_title_y + title_font.size("A")[1] + M // 2
    rec_row_h = max(30, H // 28)
    btn_h = max(36, H // 24)
    action_y = H - M - btn_h
    available_record_h = max(0, action_y - M - rec_btn_y)
    max_records = min(
        len(records),
        available_record_h // (rec_row_h + 4),
    )
    record_buttons: list[tuple[TrainingRecord, Button]] = [
        (record, Button(
            f"{record.record_name}  |  {record.saved_at[:10]}",
            pygame.Rect(M, rec_btn_y + i * (rec_row_h + 4), left_w - M * 2, rec_row_h),
        ))
        for i, record in enumerate(records[:max_records])
    ]
    action_gap = M
    btn_w = (left_w - M * 2 - action_gap * 2) // 3
    fresh_button = Button("重新開始", pygame.Rect(M, action_y, btn_w, btn_h))
    from_record_button = Button(
        "使用舊有紀錄",
        pygame.Rect(M + btn_w + action_gap, action_y, btn_w, btn_h),
    )
    go_button = Button(
        "GO",
        pygame.Rect(M + (btn_w + action_gap) * 2, action_y, btn_w, btn_h),
    )

    start_mode: str | None = None
    selected_record: TrainingRecord | None = None

    def go_enabled() -> bool:
        if start_mode is None:
            return False
        if start_mode == "record" and selected_record is None:
            return False
        fitness_values_are_valid = all(
            input_value.text.isdigit()
            and 0 <= int(input_value.text) <= 100
            for input_value in value_inputs.values()
        )
        max_speed_is_valid = (
            max_speed_input.text.isdigit()
            and 5 <= int(max_speed_input.text) <= 30
        )
        return fitness_values_are_valid and max_speed_is_valid

    BLUE = (60, 120, 200)
    DARK = (30, 30, 30)
    GRAY = (50, 50, 50)

    while True:
        for event in pygame.event.get():
            _check_quit(event)

            dropdown_was_open = preset_dropdown.is_open
            dropdown_captured_click = (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and preset_dropdown.contains(
                    event.pos,
                    include_options=dropdown_was_open,
                )
            )
            selected_strategy_name = preset_dropdown.handle_event(event)
            if selected_strategy_name is not None:
                selected_strategy = get_fitness_strategy(selected_strategy_name)
                for name, slider in all_sliders.items():
                    slider.value = int(selected_strategy.config.get_weight(name))
                    value_inputs[name].text = str(slider.value)

            input_captured_click = (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and any(
                    input_value.rect.collidepoint(event.pos)
                    for input_value in value_inputs.values()
                )
            )
            for name, input_value in value_inputs.items():
                if input_value.handle_event(event):
                    text = input_value.text
                    if text.isdigit() and 0 <= int(text) <= 100:
                        all_sliders[name].value = int(text)
            max_speed_input.handle_event(event)

            if not dropdown_captured_click and not input_captured_click:
                for name, slider in all_sliders.items():
                    if slider.handle_event(event):
                        value_inputs[name].text = str(slider.value)

            if event.type == pygame.MOUSEBUTTONDOWN:
                pos = event.pos

                if back_button.contains(pos):
                    return None

                for diff_id, _, _, card_rect in map_cards:
                    if card_rect.collidepoint(pos):
                        selected_difficulty = diff_id

                if fresh_button.contains(pos):
                    start_mode = "fresh"
                    selected_record = None
                elif from_record_button.contains(pos) and records:
                    start_mode = "record"

                if start_mode == "record":
                    for record, btn in record_buttons:
                        if btn.contains(pos):
                            selected_record = record

                if go_button.contains(pos) and go_enabled():
                    weights = {name: s.value for name, s in all_sliders.items()}
                    selected_strategy.config.update_weights(weights)
                    return (
                        selected_strategy,
                        selected_difficulty,
                        selected_record,
                        int(max_speed_input.text),
                    )

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        go_button.update_hover(mouse_pos)
        fresh_button.update_hover(mouse_pos)
        from_record_button.update_hover(mouse_pos)
        for _, btn in record_buttons:
            btn.update_hover(mouse_pos)
        for input_value in value_inputs.values():
            is_valid = (
                input_value.text.isdigit()
                and 0 <= int(input_value.text) <= 100
            )
            border_color = (
                VALID_FITNESS_INPUT_COLOR
                if is_valid
                else INVALID_FITNESS_INPUT_COLOR
            )
            input_value.border_color = border_color
            input_value.active_border_color = (
                (120, 170, 255) if is_valid else INVALID_FITNESS_INPUT_COLOR
            )
        max_speed_is_valid = (
            max_speed_input.text.isdigit()
            and 5 <= int(max_speed_input.text) <= 30
        )
        max_speed_input.border_color = (
            VALID_FITNESS_INPUT_COLOR
            if max_speed_is_valid
            else INVALID_FITNESS_INPUT_COLOR
        )
        max_speed_input.active_border_color = (
            (120, 170, 255)
            if max_speed_is_valid
            else INVALID_FITNESS_INPUT_COLOR
        )

        fresh_button.fill_color = BLUE if start_mode == "fresh" else DARK
        from_record_button.fill_color = BLUE if start_mode == "record" else DARK
        go_button.fill_color = BLUE if go_enabled() else GRAY

        screen.fill(BLACK)
        back_button.draw(screen, font)

        # Left-top: map cards
        map_title = title_font.render("選擇地圖", True, WHITE)
        screen.blit(
            map_title,
            map_title.get_rect(
                midleft=(back_button.rect.right + M, back_button.rect.centery)
            ),
        )
        speed_label = font.render("Max Speed (5–30)", True, WHITE)
        screen.blit(
            speed_label,
            speed_label.get_rect(
                midright=(max_speed_input.rect.left - M // 2, max_speed_input.rect.centery)
            ),
        )
        max_speed_input.draw(screen, font)
        for diff_id, label, thumb, card_rect in map_cards:
            selected = diff_id == selected_difficulty
            hovered = card_rect.collidepoint(mouse_pos)
            border_color = BLUE if selected else ((110, 110, 110) if hovered else (55, 55, 55))
            fill_color = (25, 35, 60) if selected else ((28, 28, 28) if hovered else (18, 18, 18))
            border_w = 3 if selected else 1
            pygame.draw.rect(screen, fill_color, card_rect, border_radius=10)
            pygame.draw.rect(screen, border_color, card_rect, border_w, border_radius=10)
            img_rect = pygame.Rect(card_rect.x + M // 2, card_rect.y + M // 2, THUMB_W, THUMB_H)
            if thumb is not None:
                screen.blit(thumb, img_rect)
                pygame.draw.rect(screen, (50, 50, 50), img_rect, 1)
            else:
                pygame.draw.rect(screen, (22, 22, 32), img_rect, border_radius=4)
                rng_surf = subtitle_font.render("隨機生成", True, (140, 140, 200))
                screen.blit(rng_surf, rng_surf.get_rect(center=img_rect.center))
            label_color = WHITE if selected else (180, 180, 180)
            label_surf = font.render(label, True, label_color)
            screen.blit(label_surf, label_surf.get_rect(centerx=card_rect.centerx, y=img_rect.bottom + M // 2))

        # Left-bottom: record section
        screen.blit(title_font.render("選擇紀錄", True, WHITE), (M, record_title_y))
        if not records:
            screen.blit(font.render("（尚無紀錄）", True, (120, 120, 120)), (M, rec_btn_y))
        if start_mode == "record":
            for record, btn in record_buttons:
                btn.fill_color = BLUE if record is selected_record else DARK
                btn.draw(screen, font)
        fresh_button.draw(screen, font)
        if records:
            from_record_button.draw(screen, font)

        # Right: fitness sliders
        screen.blit(title_font.render("Fitness 函數設定", True, WHITE),
                    (right_x + M, back_button.rect.bottom - title_font.size("A")[1] - M // 2))
        for name, slider in all_sliders.items():
            is_bonus = name in BONUS_FITNESS_PLACEHOLDERS
            label_color = (100, 220, 100) if is_bonus else (220, 100, 100)
            label_y = slider.rect.centery - font.size(name)[1] // 2
            screen.blit(font.render(name, True, label_color), (slider_label_x, label_y))
            slider.draw(screen, font)
            value_inputs[name].draw(screen, font)

        go_button.draw(screen, font)
        preset_dropdown.draw(screen, font)
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
    pygame.key.start_text_input()
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


def _rebuild_car(
    layer_sizes: list[int],
    weights: list[list[float]],
    biases: list[list[float]],
    nickname: str,
    mlp_init_seed: int = DEFAULT_MLP_INIT_SEED,
) -> Car:
    """Reconstruct a Car from saved flat weight/bias payloads."""
    car = Car(layer_sizes, mlp_init_seed=mlp_init_seed)
    payload = WeightPayload(
        model_version="v1",
        layer_sizes=layer_sizes,
        weights=weights,
        biases=biases,
        fitness_score=0.0,
        generation=0,
        track_id="rebuild",
        track_seed=0,
        nickname=nickname,
    )
    apply_weight_payload(car, payload)
    return car


def _run_record_submission_screen(
    screen: pygame.Surface, server_url: str, record: TrainingRecord
) -> None:
    """Upload entry point: rebuild the record's two parents and run the same
    competition submission flow used during live training."""
    parent_a = _rebuild_car(
        record.layer_sizes,
        record.parent_a_weights,
        record.parent_a_biases,
        record.username,
        record.mlp_init_seed,
    )
    parent_b = _rebuild_car(
        record.layer_sizes,
        record.parent_b_weights,
        record.parent_b_biases,
        record.username,
        record.mlp_init_seed,
    )
    run_submission_screen(
        screen,
        server_url,
        record.group_id,
        record.username,
        parent_a,
        parent_b,
        record.layer_sizes,
        UPLOAD_MUTATION_RATE,
        mlp_init_rng_state=record.mlp_init_rng_state,
        mutation_rng_state=record.mutation_rng_state,
    )


def run_validation_list_screen(screen: pygame.Surface, server_url: str) -> None:
    clock = pygame.time.Clock()
    font = _font(18)
    title_font = _font(32)
    width, height = screen.get_size()
    store = RecordStore()

    margin = 40
    back_button = Button("返回", pygame.Rect(margin, margin, 120, 48))
    row_height = 64
    list_top = back_button.rect.bottom + margin
    max_visible_records = max(1, (height - list_top - 80) // row_height)
    message = ""
    pending_delete_record_id: str | None = None

    while True:
        records = store.list_records()[:max_visible_records]

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

        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pending_delete_record_id = None
                if back_button.contains(event.pos):
                    return
                for record, validate_button, upload_button, delete_button in rows:
                    if validate_button.contains(event.pos):
                        _run_record_validation_screen(screen, record)
                        break
                    if upload_button.contains(event.pos):
                        _run_record_submission_screen(screen, server_url, record)
                        break
                    if delete_button.contains(event.pos):
                        pending_delete_record_id = record.record_id
                        break

            if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                for record, _, _, delete_button in rows:
                    if (
                        pending_delete_record_id == record.record_id
                        and delete_button.contains(event.pos)
                    ):
                        store.delete_record(record.record_id)
                        message = f"已刪除 {record.record_name}"
                        break
                pending_delete_record_id = None

        screen.fill(BLACK)
        title = title_font.render("Validation", True, WHITE)
        screen.blit(
            title,
            title.get_rect(
                midleft=(back_button.rect.right + margin, back_button.rect.centery)
            ),
        )
        back_button.draw(screen, font)
        for record, validate_button, upload_button, delete_button in rows:
            info = (
                f"{record.record_name}  |  {record.saved_at}  |  "
                f"{_fitness_summary(record.fitness_config)}"
            )
            info = _ellipsize(
                font,
                info,
                validate_button.rect.left - margin * 2,
            )
            screen.blit(
                font.render(info, True, WHITE),
                (margin, validate_button.rect.y + 12),
            )
            validate_button.draw(screen, font)
            upload_button.draw(screen, font)
            delete_button.draw(screen, font)
        if message:
            screen.blit(font.render(message, True, (120, 220, 120)), (60, height - 60))

        pygame.display.update()
        clock.tick(30)


def _pick_validation_map_screen(screen: pygame.Surface) -> str | None:
    """Easy / Hard / Random picker with map previews, mirroring the submission
    competition picker and the training-config map cards."""
    clock = pygame.time.Clock()
    W, H = screen.get_size()
    font = _font(max(16, H // 40))
    title_font = _font(max(20, H // 30))
    M = max(16, W // 100)

    back_button = Button("← 返回", pygame.Rect(M, M, max(100, W // 14), max(36, H // 24)))

    card_area_top = back_button.rect.bottom + M * 3
    CARD_W = (W - M * 4) // 3
    CARD_H = min(H // 2, CARD_W)
    THUMB_W = CARD_W - M * 2
    THUMB_H = THUMB_W * 9 // 16
    easy_thumb = pygame.transform.scale(
        pygame.image.load(str(VALIDATION_DIFFICULTY_MAPS["easy"][0])), (THUMB_W, THUMB_H)
    )
    hard_thumb = pygame.transform.scale(
        pygame.image.load(str(VALIDATION_DIFFICULTY_MAPS["hard"][0])), (THUMB_W, THUMB_H)
    )
    cards: list[tuple[str, str, pygame.Surface | None, pygame.Rect]] = [
        ("easy", "Easy", easy_thumb, pygame.Rect(M, card_area_top, CARD_W, CARD_H)),
        ("hard", "Hard", hard_thumb, pygame.Rect(M * 2 + CARD_W, card_area_top, CARD_W, CARD_H)),
        ("random", "隨機", None, pygame.Rect(M * 3 + CARD_W * 2, card_area_top, CARD_W, CARD_H)),
    ]

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.contains(event.pos):
                    return None
                for map_id, _, _, rect in cards:
                    if rect.collidepoint(event.pos):
                        return map_id
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        back_button.draw(screen, font)
        screen.blit(title_font.render("選擇 Validation 地圖", True, WHITE),
                    (M, back_button.rect.bottom + M))
        for map_id, label, thumb, rect in cards:
            hovered = rect.collidepoint(mouse_pos)
            border_color = (110, 110, 110) if hovered else (55, 55, 55)
            fill_color = (28, 28, 28) if hovered else (18, 18, 18)
            pygame.draw.rect(screen, fill_color, rect, border_radius=10)
            pygame.draw.rect(screen, border_color, rect, 2, border_radius=10)
            img_rect = pygame.Rect(rect.x + M, rect.y + M, THUMB_W, THUMB_H)
            if thumb is not None:
                screen.blit(thumb, img_rect)
                pygame.draw.rect(screen, (50, 50, 50), img_rect, 1)
            else:
                pygame.draw.rect(screen, (22, 22, 32), img_rect, border_radius=4)
                rng_surf = font.render("隨機生成", True, (140, 140, 200))
                screen.blit(rng_surf, rng_surf.get_rect(center=img_rect.center))
            label_surf = font.render(label, True, WHITE)
            screen.blit(label_surf, label_surf.get_rect(centerx=rect.centerx, y=img_rect.bottom + M))

        pygame.display.update()
        clock.tick(30)


def _run_record_validation_screen(screen: pygame.Surface, record: TrainingRecord) -> None:
    """Validation entry point: pick a map, breed one generation from the
    record's two parents, race all candidates, then show the run metrics."""
    map_id = _pick_validation_map_screen(screen)
    if map_id is None:
        return

    parent_a = _rebuild_car(
        record.layer_sizes,
        record.parent_a_weights,
        record.parent_a_biases,
        record.username,
        record.mlp_init_seed,
    )
    parent_b = _rebuild_car(
        record.layer_sizes,
        record.parent_b_weights,
        record.parent_b_biases,
        record.username,
        record.mlp_init_seed,
    )

    outcome = _run_validation_tournament_screen(
        screen,
        map_id,
        parent_a,
        parent_b,
        record.layer_sizes,
        record.max_speed,
    )
    if outcome is None:
        return
    client_result, survival_ticks = outcome
    _validation_result_screen(screen, map_id, client_result, survival_ticks)


def _clone_car(
    source: Any,
    layer_sizes: list[int],
    mlp_init_seed: int | None = None,
) -> Car:
    seed = mlp_init_seed
    if seed is None:
        seed = getattr(source, "mlp_init_seed", None)
    if seed is None:
        seed = DEFAULT_MLP_INIT_SEED
    clone = Car(layer_sizes, mlp_init_seed=seed)
    clone.weights = [weight.copy() for weight in source.weights]
    clone.biases = [bias.copy() for bias in source.biases]
    return clone


def _build_candidates(
    parent_a: Any,
    parent_b: Any,
    layer_sizes: list[int],
    mutation_rate: int,
    total: int = SUBMISSION_POPULATION_SIZE,
    mlp_init_rng_state: dict[str, Any] | None = None,
    mutation_rng_state: tuple[Any, ...] | list[Any] | None = None,
) -> list[Car]:
    seed = getattr(parent_a, "mlp_init_seed", None)
    if seed is None:
        seed = getattr(parent_b, "mlp_init_seed", None)
    if seed is None:
        seed = DEFAULT_MLP_INIT_SEED
    mlp_init_rng, mutation_rng = create_evolution_rngs(
        seed,
        mlp_init_rng_state=mlp_init_rng_state,
        mutation_rng_state=mutation_rng_state,
    )
    aux_car = Car(
        layer_sizes, mlp_init_seed=seed, mlp_init_rng=mlp_init_rng
    )
    candidates = [
        Car(layer_sizes, mlp_init_seed=seed, mlp_init_rng=mlp_init_rng)
        for _ in range(total)
    ]

    for index in range(0, total - 2, 2):
        uniformCrossOverWeights(parent_a, parent_b, candidates[index], candidates[index + 1])
        uniformCrossOverBiases(parent_a, parent_b, candidates[index], candidates[index + 1])

    candidates[total - 2] = _clone_car(parent_a, layer_sizes, seed)
    candidates[total - 1] = _clone_car(parent_b, layer_sizes, seed)

    for index in range(total - 2):
        for _ in range(mutation_rate):
            mutateOneWeightGene(candidates[index], aux_car, mutation_rng)
            mutateOneWeightGene(aux_car, candidates[index], mutation_rng)
            mutateOneBiasesGene(candidates[index], aux_car, mutation_rng)
            mutateOneBiasesGene(aux_car, candidates[index], mutation_rng)

    return candidates


def _pick_competition_screen(screen: pygame.Surface) -> str | None:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    back_button = Button("返回", pygame.Rect(60, 40, 120, 48))
    options = [("Easy", "easy"), ("Hard", "hard"), ("Final", "final")]
    buttons = [
        (competition_id, Button(label, pygame.Rect(width // 2 - 480 + i * 340, height // 2 - 80, 300, 160)))
        for i, (label, competition_id) in enumerate(options)
    ]

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.contains(event.pos):
                    return None
                for competition_id, button in buttons:
                    if button.contains(event.pos):
                        return competition_id
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        for _, button in buttons:
            button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render("選擇要提交的競賽", True, WHITE), (60, 140))
        back_button.draw(screen, font)
        for _, button in buttons:
            button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def _check_eligibility_screen(
    screen: pygame.Surface, server_url: str, competition_id: str, group_id: str, username: str
) -> bool:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    result = check_eligibility(server_url, competition_id, group_id, username)

    back_button = Button("返回", pygame.Rect(60, 40, 120, 48))
    start_button = Button("開始評測", pygame.Rect(width // 2 - 100, height // 2 + 80, 200, 56))
    can_start = isinstance(result, EligibilityResult) and result.eligible

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.contains(event.pos):
                    return False
                if can_start and start_button.contains(event.pos):
                    return True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return False

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        if can_start:
            start_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render(f"資格檢查：{competition_id}", True, WHITE), (60, 140))
        back_button.draw(screen, font)

        if isinstance(result, NetworkError):
            screen.blit(font.render(f"連線失敗：{result.message}", True, (255, 90, 90)), (60, 220))
        elif result.eligible:
            screen.blit(font.render(
                f"可以提交。stage={result.stage}，version={result.competition_config_version}",
                True, (120, 220, 120),
            ), (60, 220))
            start_button.draw(screen, font)
        else:
            reason_text = _REASON_MESSAGES.get(result.reason or "", result.reason or "未知原因")
            screen.blit(font.render(f"目前無法提交：{reason_text}", True, (255, 90, 90)), (60, 220))
            screen.blit(font.render(f"下次可提交時間：{result.next_submission_at}", True, WHITE), (60, 256))

        pygame.display.update()
        clock.tick(30)


def _simulate_candidates(
    screen: pygame.Surface,
    track_front: pygame.Surface,
    track_back: pygame.Surface,
    spawn: dict[str, float],
    candidates: list[Car],
    car_image: pygame.Surface,
    frame_limit: int,
    trackers: list[Any] | None,
    title: str,
    stop_on_first_completion: bool = False,
    max_speed: int = MAX_SPEED,
) -> list[int] | None:
    """Race every candidate on one track until all are eliminated/finished or
    the frame limit hits. A completion requires ordered checkpoint traversal
    without colliding on the finish frame. Advances `trackers` in place when
    provided. Returns each candidate's survival tick count (or None if the user
    pressed ESC)."""
    clock = pygame.time.Clock()
    font = _font(20)

    configure_car(track_back, car_image, max_speed)
    for car in candidates:
        car.reset_state(spawn["x"], spawn["y"], spawn["angle"], car_image=car_image)

    previous_positions = [car.center for car in candidates]
    active = [True] * len(candidates)
    survival = [frame_limit] * len(candidates)

    MAP_W, MAP_H = track_front.get_size()
    SCR_W, SCR_H = screen.get_size()
    scale = min(SCR_W / MAP_W, SCR_H / MAP_H)
    dst_w, dst_h = int(MAP_W * scale), int(MAP_H * scale)
    dst_x, dst_y = (SCR_W - dst_w) // 2, (SCR_H - dst_h) // 2
    canvas = pygame.Surface((MAP_W, MAP_H))

    tick = 0
    while tick < frame_limit and any(active):
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return None

        tick += 1
        completed_this_tick = False
        for index, car in enumerate(candidates):
            if not active[index]:
                continue
            previous = previous_positions[index]
            car.update()
            collided = car.collision()
            if collided:
                active[index] = False
                survival[index] = tick
            else:
                car.feedforward()
                car.takeAction()
                if trackers is not None:
                    trackers[index].advance(previous, car.center, tick=tick)
                    if trackers[index].completed:
                        active[index] = False
                        survival[index] = tick
                        completed_this_tick = True
            previous_positions[index] = car.center

        canvas.blit(track_front, (0, 0))
        for car in candidates:
            car.draw(canvas)
        canvas.blit(
            font.render(
                f"{title}  時間 {format_ticks_as_seconds(tick)}"
                f" / {format_ticks_as_seconds(frame_limit)}"
                f"  Active: {sum(active)}",
                True,
                WHITE,
            ),
            (20, 20),
        )
        screen.fill(BLACK)
        screen.blit(pygame.transform.scale(canvas, (dst_w, dst_h)), (dst_x, dst_y))
        pygame.display.update()
        clock.tick(30)
        if stop_on_first_completion and completed_this_tick:
            break

    return survival


def _client_results_from_trackers(trackers: list[Any]) -> list[ClientResult]:
    return [
        ClientResult(
            completed=tracker.completed,
            lap_ticks=tracker.lap_ticks,
            max_progress=tracker.max_progress,
            ticks_to_max_progress=tracker.ticks_to_max_progress,
        )
        for tracker in trackers
    ]


def _run_candidate_tournament_screen(
    screen: pygame.Surface,
    competition_id: str,
    parent_a: Any,
    parent_b: Any,
    layer_sizes: list[int],
    mutation_rate: int,
    mlp_init_rng_state: dict[str, Any] | None = None,
    mutation_rng_state: tuple[Any, ...] | list[Any] | None = None,
) -> tuple[Car, ClientResult] | None:
    assets = load_game_assets()
    competition_map = load_competition_map(competition_id)
    track_front = pygame.image.load(competition_map.front_path)
    track_back = pygame.image.load(competition_map.back_path)

    candidates = _build_candidates(
        parent_a,
        parent_b,
        layer_sizes,
        mutation_rate,
        mlp_init_rng_state=mlp_init_rng_state,
        mutation_rng_state=mutation_rng_state,
    )
    trackers = [competition_map.new_tracker() for _ in candidates]

    survival = _simulate_candidates(
        screen,
        track_front,
        track_back,
        competition_map.spawn,
        candidates,
        assets.white_small_car,
        FRAME_LIMIT,
        trackers,
        title=f"Competition：{competition_id}",
    )
    if survival is None:
        return None

    client_results = _client_results_from_trackers(trackers)
    winner_index = min(range(len(candidates)), key=lambda i: client_results[i].ranking_key())
    return candidates[winner_index], client_results[winner_index]


def _run_validation_tournament_screen(
    screen: pygame.Surface,
    map_id: str,
    parent_a: Any,
    parent_b: Any,
    layer_sizes: list[int],
    max_speed: int = MAX_SPEED,
) -> tuple[ClientResult | None, int] | None:
    """Breed candidates and race them through ordered map checkpoints.

    The first non-colliding candidate to complete the route ends validation.
    """
    assets = load_game_assets()
    candidates = _build_candidates(
        parent_a,
        parent_b,
        layer_sizes,
        VALIDATION_MUTATION_RATE,
        total=VALIDATION_POPULATION_SIZE,
    )

    if map_id == "random":
        generate_random_map(screen)
        track_front = pygame.image.load(TRACK_FRONT_PATH)
        track_back = pygame.image.load(TRACK_BACK_PATH)
        metadata = json.loads(TRACK_METADATA_PATH.read_text(encoding="utf-8"))
        route = reconstruct_route_cells(metadata)
        layout = TrackLayout(seed=0, route_cells=tuple(route))
        spawn = layout.spawn
        checkpoints = tuple(
            build_boundary_checkpoints(layout, TRACK_BACK_PATH)
        )
        trackers: list[Any] = [
            CompetitionRunTracker(
                checkpoints=checkpoints,
                total_length_px=len(route) * BLOCK_SIZE,
            )
            for _ in candidates
        ]
    else:
        validation_map = load_validation_map(map_id)
        track_front = pygame.image.load(validation_map.front_path)
        track_back = pygame.image.load(validation_map.back_path)
        spawn = validation_map.spawn
        trackers = [validation_map.new_tracker() for _ in candidates]

    survival = _simulate_candidates(
        screen,
        track_front,
        track_back,
        spawn,
        candidates,
        assets.green_small_car,
        VALIDATION_FRAME_LIMIT,
        trackers,
        title=f"Validation：{map_id}",
        stop_on_first_completion=True,
        max_speed=max_speed,
    )
    if survival is None:
        return None

    client_results = _client_results_from_trackers(trackers)
    winner = min(
        range(len(client_results)),
        key=lambda index: client_results[index].ranking_key(),
    )
    return client_results[winner], survival[winner]


def _validation_result_screen(
    screen: pygame.Surface,
    map_id: str,
    client_result: ClientResult | None,
    survival_ticks: int,
) -> None:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    back_button = Button("返回列表", pygame.Rect(60, 40, 160, 48))

    if client_result is not None:
        lines = [
            f"completed: {client_result.completed}",
            f"完賽時間: {format_ticks_as_seconds(client_result.lap_ticks)}",
            f"max_progress: {client_result.max_progress:.1f} px",
            "到達最遠進度時間: "
            f"{format_ticks_as_seconds(client_result.ticks_to_max_progress)}",
        ]
        note = ""
    else:
        lines = [f"存活時間: {format_ticks_as_seconds(survival_ticks)}"]
        note = "此地圖尚無 checkpoint，progress／完賽指標暫不適用"

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return
            if event.type == pygame.MOUSEBUTTONDOWN and back_button.contains(event.pos):
                return

        back_button.update_hover(pygame.mouse.get_pos())

        screen.fill(BLACK)
        screen.blit(title_font.render(f"Validation 成績：{map_id}", True, WHITE), (60, 120))
        for i, line in enumerate(lines):
            screen.blit(font.render(line, True, WHITE), (60, 200 + i * 44))
        if note:
            screen.blit(font.render(note, True, (220, 200, 120)), (60, 200 + len(lines) * 44 + 16))
        back_button.draw(screen, font)

        pygame.display.update()
        clock.tick(30)


def _submit_result_screen(
    screen: pygame.Surface,
    server_url: str,
    competition_id: str,
    group_id: str,
    username: str,
    winner_car: Car,
    layer_sizes: list[int],
    client_result: ClientResult,
) -> None:
    clock = pygame.time.Clock()
    font = _font()
    title_font = _font(32)
    width, height = screen.get_size()

    back_button = Button("返回", pygame.Rect(60, 40, 120, 48))
    submit_button = Button("送出", pygame.Rect(width // 2 - 100, height // 2 + 80, 200, 56))
    submitted = False
    response: SubmissionAccepted | SubmissionRejected | NetworkError | None = None

    if client_result.completed:
        summary = (
            "完賽！耗時 "
            f"{format_ticks_as_seconds(client_result.lap_ticks)}"
        )
    else:
        summary = (
            f"未完賽，最遠進度 {client_result.max_progress:.1f}px"
            f"（{format_ticks_as_seconds(client_result.ticks_to_max_progress)} 達到）"
        )

    while True:
        for event in pygame.event.get():
            _check_quit(event)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.contains(event.pos):
                    return
                if not submitted and submit_button.contains(event.pos):
                    weight_payload = export_weight_payload(
                        winner_car,
                        generation=0,
                        track_id=f"competition-{competition_id}",
                        track_seed=0,
                        nickname=username,
                    )
                    payload = SubmissionPayload(
                        group_id=group_id,
                        username=username,
                        weights=weight_payload.weights,
                        biases=weight_payload.biases,
                    )
                    response = submit_to_competition_server(
                        server_url, competition_id, payload, client_result
                    )
                    submitted = True
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        if not submitted:
            submit_button.update_hover(mouse_pos)

        screen.fill(BLACK)
        screen.blit(title_font.render(f"Local Winner：{competition_id}", True, WHITE), (60, 140))
        screen.blit(font.render(summary, True, WHITE), (60, 200))
        back_button.draw(screen, font)
        if not submitted:
            submit_button.draw(screen, font)

        if isinstance(response, SubmissionAccepted):
            status = response.body.get("status", "queued")
            submission_id = response.body.get("submission_id", "")
            screen.blit(font.render(
                f"已送出！submission_id={submission_id}，狀態：{status}", True, (120, 220, 120)
            ), (60, 260))
        elif isinstance(response, SubmissionRejected):
            reason_text = _REASON_MESSAGES.get(response.error, response.error)
            screen.blit(font.render(f"送出被拒絕：{reason_text}", True, (255, 90, 90)), (60, 260))
            if response.next_submission_at:
                screen.blit(
                    font.render(f"下次可提交時間：{response.next_submission_at}", True, WHITE),
                    (60, 296),
                )
        elif isinstance(response, NetworkError):
            screen.blit(font.render(f"連線失敗：{response.message}", True, (255, 90, 90)), (60, 260))

        pygame.display.update()
        clock.tick(30)


def run_submission_screen(
    screen: pygame.Surface,
    server_url: str,
    group_id: str,
    username: str,
    parent_a: Any,
    parent_b: Any,
    layer_sizes: list[int],
    mutation_rate: int,
    mlp_init_rng_state: dict[str, Any] | None = None,
    mutation_rng_state: tuple[Any, ...] | list[Any] | None = None,
) -> None:
    competition_id = _pick_competition_screen(screen)
    if competition_id is None:
        return

    can_proceed = _check_eligibility_screen(screen, server_url, competition_id, group_id, username)
    if not can_proceed:
        return

    tournament_result = _run_candidate_tournament_screen(
        screen,
        competition_id,
        parent_a,
        parent_b,
        layer_sizes,
        mutation_rate,
        mlp_init_rng_state=mlp_init_rng_state,
        mutation_rng_state=mutation_rng_state,
    )
    if tournament_result is None:
        return
    winner_car, client_result = tournament_result

    _submit_result_screen(
        screen, server_url, competition_id, group_id, username, winner_car, layer_sizes, client_result
    )
