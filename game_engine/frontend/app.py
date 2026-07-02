from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
import secrets

import numpy as np
import pygame
from shapely.geometry import Point  # type: ignore[import-untyped]
from shapely.geometry.polygon import Polygon  # type: ignore[import-untyped]

from game_engine.backend.assets import load_game_assets
from game_engine.backend.environment import load_server_url
from game_engine.backend.car import (
    DEFAULT_MLP_INIT_SEED,
    Car,
    configure_car,
    set_collision_map,
)
from GA.fitness import FitnessStrategy, select_best_cars
from game_engine.backend.record_store import RecordStore
from game_engine.backend.serialization import export_weight_payload
from game_engine.backend.simulator import Simulator
from game_engine.backend.settings import (
    BG,
    CARBON,
    CYAN,
    DIM,
    F1_GREEN,
    F1_RED,
    FONT_PATH,
    HEAD_FONT_PATH,
    HIDDEN_LAYER,
    INK,
    INPUT_LAYER,
    LINE,
    MONO_FONT_PATH,
    OUTPUT_LAYER,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    TRACK_HALF_WIDTH,
    TRACK_METADATA_PATH,
    TRAINING_DIFFICULTY_MAPS,
    YELLOW,
)
from game_engine.backend.track import TrackGeometry
from game_engine.backend.track_generator import generate_random_map
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.config_store import load_runtime_settings, save_runtime_settings
from game_engine.frontend.profile_store import (
    clear_login_profile,
    load_login_profile,
)
from game_engine.frontend.scenes import AppShell
from game_engine.frontend.submission_client import submit_car
from game_engine.frontend.screens import (
    AppQuit,
    run_clear_user_confirm_screen,
    run_loading_screen,
    run_login_screen,
    run_main_menu_screen,
    run_record_name_screen,
    run_save_confirm_screen,
    run_training_config_screen,
    run_validation_list_screen,
)
from game_engine.backend.fitness_preset_store import FitnessPresetStore
from game_engine.frontend.widgets import Button
from shared.contracts import TrainingRecord


UTC_PLUS_8 = timezone(timedelta(hours=8))


def _set_collision_surface(
    cars: Iterable[Car],
    surface: pygame.Surface,
) -> None:
    for target_car in cars:
        target_car.set_collision_surface(surface)


def _car_from_flat_weights(
    layer_sizes: list[int],
    flat_weights: list[list[float]],
    flat_biases: list[list[float]],
    mlp_init_seed: int = DEFAULT_MLP_INIT_SEED,
) -> Car:
    """Reconstruct a Car from the flat weight/bias lists stored in a TrainingRecord."""
    car = Car(layer_sizes, mlp_init_seed=mlp_init_seed)
    for i in range(len(layer_sizes) - 1):
        rows, cols = layer_sizes[i + 1], layer_sizes[i]
        car.weights[i] = np.array(flat_weights[i]).reshape(rows, cols)
        car.biases[i] = np.array(flat_biases[i]).reshape(rows, 1)
    return car


def run():
    pygame.init()
    pygame.scrap.init()
    info = pygame.display.Info()
    win_w = int(info.current_w * 0.9)
    win_h = int(info.current_h * 0.9)
    screen = pygame.display.set_mode((win_w, win_h), pygame.RESIZABLE)

    try:
        settings = load_runtime_settings()
        settings.server_url = load_server_url()
        profile = load_login_profile()
        should_save_settings = profile is None
        if profile is None:
            profile = run_login_screen(screen, settings.server_url)
        else:
            profile.server_url = settings.server_url
        settings.nickname = profile.username
        if should_save_settings:
            save_runtime_settings(settings)

        while True:
            choice = run_main_menu_screen(screen, profile)
            if choice == "clear_user":
                if run_clear_user_confirm_screen(screen):
                    clear_login_profile()
                    RecordStore().clear()
                    profile = run_login_screen(screen, settings.server_url)
                    settings.nickname = profile.username
                    save_runtime_settings(settings)
                continue
            if choice == "training":
                result = run_training_config_screen(
                    screen, settings.max_speed, settings.auto_breed_seconds
                )
                if result is not None:
                    (
                        fitness_strategy,
                        map_difficulty,
                        parent_record,
                        max_speed,
                        auto_breed_seconds,
                    ) = result
                    settings.max_speed = max_speed
                    settings.auto_breed_seconds = auto_breed_seconds
                    save_runtime_settings(settings)
                    run_loading_screen(screen)
                    if map_difficulty == 3:
                        generate_random_map(screen)
                    run_training_loop(
                        screen,
                        settings,
                        profile,
                        fitness_strategy,
                        map_difficulty,
                        parent_record,
                    )
            else:
                run_validation_list_screen(screen, profile.server_url)
    except AppQuit:
        pass

    pygame.quit()


def run_training_loop(
    screen,
    settings,
    profile,
    fitness_strategy: FitnessStrategy,
    map_difficulty,
    parent_record: TrainingRecord | None = None,
):
    session = TrainingSession.from_settings(settings)
    shell = AppShell(settings)
    fitness_config = fitness_strategy.config

    assets = load_game_assets()
    game_display = screen
    clock = pygame.time.Clock()

    front_path, back_path, metadata_path = TRAINING_DIFFICULTY_MAPS[map_difficulty]
    bg = pygame.image.load(front_path)
    bg4 = pygame.image.load(back_path)
    configure_car(bg4, assets.white_small_car, settings.max_speed)
    track = TrackGeometry.from_json(
        metadata_path,
        default_half_width=TRACK_HALF_WIDTH,
    )
    simulator = Simulator(track, settings.fps)

    number_track = 2 if map_difficulty == 3 else 1
    generation_started_at = pygame.time.get_ticks()
    submit_status = "Submit: not sent"
    layer_sizes = [INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]

    car = Car(layer_sizes)
    aux_car = Car(layer_sizes)
    nn_cars = [
        Car(
            layer_sizes,
            mlp_init_seed=session.evolution_seed,
            mlp_init_rng=session.mlp_init_rng,
        )
        for _ in range(session.population_size)
    ]

    if parent_record is not None:
        saved_pa = _car_from_flat_weights(
            layer_sizes,
            parent_record.parent_a_weights,
            parent_record.parent_a_biases,
            parent_record.mlp_init_seed,
        )
        saved_pb = _car_from_flat_weights(
            layer_sizes,
            parent_record.parent_b_weights,
            parent_record.parent_b_biases,
            parent_record.mlp_init_seed,
        )
        session.selected_cars = [saved_pa, saved_pb]
        nn_cars = session.breed_population(nn_cars, aux_car, Car, layer_sizes, assets)
        session.generation = 1

    # Virtual canvas at the map's native resolution; rendered then scaled to the
    # physical window. This keeps car coordinates correct (they live in 1600×900
    # space) while the window can be any size.
    MAP_W, MAP_H = bg.get_size()
    map_canvas = pygame.Surface((MAP_W, MAP_H))

    W, H = screen.get_size()
    _map_scale = 1.0
    _map_dst_w = MAP_W
    _map_dst_h = MAP_H
    _map_dst_x = 0
    _map_dst_y = 0
    back_button = Button("Back", pygame.Rect(0, 0, 180, 44))
    new_map_button = Button("新地圖", pygame.Rect(0, 0, 180, 44)) if map_difficulty == 3 else None
    next_gen_button = Button("下一代 (Next Gen)", pygame.Rect(0, 0, 180, 44))
    restart_button = Button("Restart", pygame.Rect(0, 0, 180, 44))

    def recalculate_layout() -> None:
        nonlocal W, H, _map_scale, _map_dst_w, _map_dst_h, _map_dst_x, _map_dst_y
        W, H = game_display.get_size()
        _map_scale = min(W / MAP_W, H / MAP_H)
        _map_dst_w = int(MAP_W * _map_scale)
        _map_dst_h = int(MAP_H * _map_scale)
        _map_dst_x = (W - _map_dst_w) // 2
        _map_dst_y = (H - _map_dst_h) // 2
        back_button.rect = pygame.Rect(W - 200, 16, 180, 44)
        if new_map_button is not None:
            new_map_button.rect = pygame.Rect(W - 200, 70, 180, 44)
        _ngy = 124 if new_map_button is not None else 70
        next_gen_button.rect = pygame.Rect(W - 200, _ngy, 180, 44)
        restart_button.rect = pygame.Rect(W - 200, next_gen_button.rect.bottom + 10, 180, 44)

    recalculate_layout()

    def map_position(screen_position):
        screen_x, screen_y = screen_position
        dst_w = _map_dst_w or 1
        dst_h = _map_dst_h or 1
        return (
            (screen_x - _map_dst_x) * MAP_W / dst_w,
            (screen_y - _map_dst_y) * MAP_H / dst_h,
        )

    font = pygame.font.Font(str(FONT_PATH), 18)
    _bar_head = pygame.font.Font(str(HEAD_FONT_PATH), 14)
    _bar_mono = pygame.font.Font(str(MONO_FONT_PATH), 14)
    _next_gen_mono = pygame.font.Font(str(MONO_FONT_PATH), 18)
    _badge_font = pygame.font.Font(str(HEAD_FONT_PATH), 14)
    _tower_font = pygame.font.Font(str(MONO_FONT_PATH), 14)
    _tower_head = pygame.font.Font(str(HEAD_FONT_PATH), 14)

    def persist_settings():
        settings.mutation_rate = session.mutation_rate
        settings.show_player = session.show_player
        settings.show_debug_overlay = session.show_debug_overlay
        save_runtime_settings(settings)

    def track_spawn():
        return (120, 480) if number_track == 1 else (140, 610)

    def apply_sensor_line_state():
        car.showlines = session.show_sensor_lines
        for nn_car in nn_cars:
            nn_car.showlines = session.show_sensor_lines

    def generation_elapsed_seconds():
        return (pygame.time.get_ticks() - generation_started_at) / 1000.0

    def restart_generation_timer():
        nonlocal generation_started_at
        generation_started_at = pygame.time.get_ticks()

    def apply_track_spawn(reset_player=False, reset_images=False):
        spawn_x, spawn_y = track_spawn()
        for nn_car in nn_cars:
            car_image = assets.white_small_car if reset_images else None
            nn_car.reset_state(spawn_x, spawn_y, car_image=car_image)
            nn_car.showlines = session.show_sensor_lines
        if reset_player:
            car.reset_state(spawn_x, spawn_y)
            car.showlines = session.show_sensor_lines
            car.refresh_track_state(track)
        simulator.reset_population(nn_cars)
        session.alive_count = len(nn_cars)

    _mono = pygame.font.Font(str(MONO_FONT_PATH), 15)
    _head = pygame.font.Font(str(HEAD_FONT_PATH), 15)

    def display_texts():
        remaining_seconds = max(
            0.0,
            session.generation_duration_seconds - generation_elapsed_seconds(),
        )
        rows = [
            ("GEN",      str(session.generation),          INK),
            ("CARS",     str(session.population_size),     INK),
            ("ALIVE",    str(session.alive_count),         F1_GREEN),
            ("FITNESS",  fitness_strategy.name,            INK),
            ("NEXT GEN", f"{remaining_seconds:.3f}s",      YELLOW),
        ]
        panel_w = 220
        panel_h = len(rows) * 22 + 16
        panel_x, panel_y = 16, H - panel_h - 16
        panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)
        pygame.draw.rect(game_display, CARBON, panel_rect)
        pygame.draw.rect(game_display, LINE, panel_rect, 1)
        pygame.draw.rect(game_display, CYAN, pygame.Rect(panel_x, panel_y, 3, panel_h))
        for i, (label, value, val_color) in enumerate(rows):
            y = panel_y + 8 + i * 22
            lbl_surf = _mono.render(label, True, DIM)
            game_display.blit(lbl_surf, (panel_x + 8, y))
            val_surf = _mono.render(value, True, val_color)
            game_display.blit(val_surf, val_surf.get_rect(right=panel_x + panel_w - 8, y=y))

    def breed_selected():
        nonlocal nn_cars
        if len(nn_cars) < 2:
            return False
        session.selected_cars = select_best_cars(
            nn_cars,
            count=2,
        )
        nn_cars = session.breed_population(
            population=nn_cars,
            aux_car=aux_car,
            car_factory=Car,
            layer_sizes=layer_sizes,
            assets=assets,
        )
        apply_track_spawn()
        restart_generation_timer()
        return True

    def restart_training():
        nonlocal nn_cars
        new_seed = secrets.randbits(32)
        while new_seed == session.evolution_seed:
            new_seed = secrets.randbits(32)
        session.restart_with_seed(new_seed)
        settings.evolution_seed = new_seed
        save_runtime_settings(settings)
        nn_cars = [
            Car(
                layer_sizes,
                mlp_init_seed=session.evolution_seed,
                mlp_init_rng=session.mlp_init_rng,
            )
            for _ in range(session.population_size)
        ]
        apply_track_spawn(reset_player=True, reset_images=True)
        restart_generation_timer()

    _leader_colors = (F1_RED, CYAN)
    _leader_labels = ("P1", "P2")

    def draw_fitness_leaders(target):
        if not nn_cars:
            return

        leaders = select_best_cars(
            nn_cars,
            count=min(2, len(nn_cars)),
        )
        # 反轉繪製順序讓 P1 蓋在最上層
        for rank_idx, (leader, color, p_label) in reversed(list(enumerate(
            zip(leaders, _leader_colors, _leader_labels, strict=False)
        ))):
            center = (round(leader.x), round(leader.y))
            radius = round(max(leader.width, leader.height) / 2) + 10
            pygame.draw.circle(target, color, center, radius, width=3)

            label_text = f"{p_label}  {leader.fitness_score:.1f}"
            label = _badge_font.render(label_text, True, INK)
            badge_w = label.get_width() + 16
            badge_h = label.get_height() + 6
            badge_rect = pygame.Rect(center[0] - badge_w // 2, center[1] - radius - badge_h - 6, badge_w, badge_h)
            badge_pts = [
                (badge_rect.left + 6, badge_rect.top),
                (badge_rect.right, badge_rect.top),
                (badge_rect.right, badge_rect.bottom - 6),
                (badge_rect.right - 6, badge_rect.bottom),
                (badge_rect.left, badge_rect.bottom),
                (badge_rect.left, badge_rect.top + 6),
            ]
            pygame.draw.polygon(target, color, badge_pts)
            target.blit(label, label.get_rect(center=badge_rect.center))

    def submit_best_car():
        nonlocal submit_status
        if not nn_cars:
            submit_status = "Submit: no cars"
            return

        best_car = max(
            nn_cars,
            key=lambda nn_car: float(
                getattr(nn_car, "fitness_score", getattr(nn_car, "score", 0.0))
            ),
        )
        result = submit_car(
            server_url=settings.server_url,
            car=best_car,
            group_id=profile.group_id,
            username=profile.username,
        )
        submit_status = result.message

    def redraw_game_window():
        # Draw map + cars on the 1600×900 virtual canvas.
        map_canvas.blit(bg, (0, 0))

        for nn_car in nn_cars:
            if not nn_car.collided:
                step_result = simulator.step(nn_car, fitness_strategy.score_frame)
                if step_result.telemetry.collided:
                    session.mark_collision(nn_car)

        for nn_car in nn_cars:
            nn_car.draw(map_canvas)

        if session.show_player:
            car.update(track)
            if car.collision(track):
                car.resetPosition()
                car.refresh_track_state(track)
            car.draw(map_canvas)

        draw_fitness_leaders(map_canvas)

        # Scale the game canvas to the physical window, then draw UI on top.
        game_display.fill(BG)
        game_display.blit(
            pygame.transform.scale(map_canvas, (_map_dst_w, _map_dst_h)),
            (_map_dst_x, _map_dst_y),
        )
        if session.show_debug_overlay:
            display_texts()

        # --- 頂部狀態條 ---
        bar_h = 36
        pygame.draw.rect(game_display, (8, 9, 12, 210), pygame.Rect(0, 0, W, bar_h))
        pygame.draw.line(game_display, LINE, (0, bar_h), (W, bar_h))
        training_surf = _bar_head.render("TRAINING", True, F1_RED)
        game_display.blit(training_surf, training_surf.get_rect(midleft=(12, bar_h // 2)))
        player_surf = _bar_mono.render(f"{profile.username}  Group {profile.group_id}", True, DIM)
        game_display.blit(player_surf, player_surf.get_rect(midleft=(training_surf.get_width() + 24, bar_h // 2)))
        remaining_seconds = max(0.0, session.generation_duration_seconds - generation_elapsed_seconds())
        _ng_right = back_button.rect.left - 12
        _cy = bar_h // 2
        _GAP = 22  # space between items

        # Render all label+value surfaces (unified _bar_mono labels / _next_gen_mono values)
        _ng_lbl_s   = _bar_mono.render("NEXT GEN", True, DIM)
        _ng_val_s   = _next_gen_mono.render(f"{remaining_seconds:.3f}s", True, YELLOW)
        _spd_lbl_s  = _bar_mono.render("MAX SPD", True, DIM)
        _spd_val_s  = _next_gen_mono.render(str(settings.max_speed), True, CYAN)
        _seed_lbl_s = _bar_mono.render("NN SEED", True, DIM)
        _seed_val_s = _next_gen_mono.render(str(session.evolution_seed), True, CYAN)

        # Lay out right-to-left: NEXT GEN → MAX SPD → NN SEED
        _cur = _ng_right
        for _lbl_s, _val_s in (
            (_ng_lbl_s, _ng_val_s),
            (_spd_lbl_s, _spd_val_s),
            (_seed_lbl_s, _seed_val_s),
        ):
            _vr = _val_s.get_rect(midright=(_cur, _cy))
            game_display.blit(_val_s, _vr)
            _lr = _lbl_s.get_rect(midright=(_vr.left - 6, _cy))
            game_display.blit(_lbl_s, _lr)
            _cur = _lr.left - _GAP

        # --- 右上按鈕 ---
        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        back_button.draw(game_display, font)
        next_gen_button.fill_color = F1_RED
        next_gen_button.update_hover(mouse_pos)
        next_gen_button.draw(game_display, font)
        restart_button.update_hover(mouse_pos)
        restart_button.draw(game_display, font)
        if new_map_button is not None:
            new_map_button.update_hover(mouse_pos)
            new_map_button.draw(game_display, font)

        # --- 計時塔（左上，依 draw_fitness_leaders 的 leader 列出 P1/P2 fitness）---
        if nn_cars:
            tower_leaders = select_best_cars(nn_cars, count=min(2, len(nn_cars)))
            tower_x, tower_y = 16, bar_h + 8
            tower_w = 180
            tower_colors = (F1_RED, CYAN)
            tower_labels = ("P1", "P2")
            for ti, (ldr, tc, tl) in enumerate(zip(tower_leaders, tower_colors, tower_labels, strict=False)):
                row_rect = pygame.Rect(tower_x, tower_y + ti * 30, tower_w, 26)
                pygame.draw.rect(game_display, CARBON, row_rect)
                pygame.draw.rect(game_display, LINE, row_rect, 1)
                pygame.draw.rect(game_display, tc, pygame.Rect(row_rect.x, row_rect.y, 3, row_rect.height))
                p_surf = _tower_head.render(tl, True, tc)
                game_display.blit(p_surf, p_surf.get_rect(midleft=(row_rect.x + 8, row_rect.centery)))
                fit_surf = _tower_font.render(f"{ldr.fitness_score:.1f}", True, INK)
                game_display.blit(fit_surf, fit_surf.get_rect(midright=(row_rect.right - 8, row_rect.centery)))

        pygame.display.update()

    def do_new_random_map():
        nonlocal bg, bg4, simulator, track
        generate_random_map(game_display)
        bg = pygame.image.load(TRACK_FRONT_PATH)
        bg4 = pygame.image.load(TRACK_BACK_PATH)
        track = TrackGeometry.from_json(
            TRACK_METADATA_PATH,
            default_half_width=TRACK_HALF_WIDTH,
        )
        simulator = Simulator(track, settings.fps)
        set_collision_map(bg4)
        configure_car(bg4, assets.white_small_car, settings.max_speed)
        _set_collision_surface((car, aux_car, *nn_cars), bg4)
        apply_track_spawn(reset_player=True)
        restart_generation_timer()

    def save_training_record(record_name: str) -> None:
        top2 = select_best_cars(nn_cars, count=2)
        parent_a = top2[0]
        parent_b = top2[1] if len(top2) >= 2 else top2[0]
        common = dict(
            generation=session.generation,
            track_id=f"training-{map_difficulty}",
            track_seed=settings.track_seed,
            nickname=profile.username,
        )
        pa_payload = export_weight_payload(parent_a, **common)
        pb_payload = export_weight_payload(parent_b, **common)
        mlp_init_rng_state, mutation_rng_state = (
            session.snapshot_evolution_rngs()
        )
        record = TrainingRecord(
            record_id="",
            record_name=record_name,
            saved_at=datetime.now(UTC_PLUS_8).isoformat(timespec="seconds"),
            group_id=profile.group_id,
            username=profile.username,
            layer_sizes=pa_payload.layer_sizes,
            parent_a_weights=pa_payload.weights,
            parent_a_biases=pa_payload.biases,
            parent_b_weights=pb_payload.weights,
            parent_b_biases=pb_payload.biases,
            fitness_config=fitness_config,
            map_difficulty=map_difficulty,
            max_speed=settings.max_speed,
            best_fitness_score=max(
                pa_payload.fitness_score,
                pb_payload.fitness_score,
            ),
            mlp_init_seed=(
                parent_a.mlp_init_seed
                if parent_a.mlp_init_seed is not None
                else settings.evolution_seed
            ),
            mlp_init_rng_state=mlp_init_rng_state,
            mutation_rng_state=mutation_rng_state,
        )
        RecordStore().save_record(record)

    apply_sensor_line_state()
    simulator.reset_population(nn_cars)
    car.refresh_track_state(track)

    while True:
        leave_requested = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                persist_settings()
                raise AppQuit()

            if event.type == pygame.VIDEORESIZE:
                recalculate_layout()

            if event.type == pygame.KEYDOWN and event.key == pygame.K_u:
                submit_best_car()

            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_buttons = pygame.mouse.get_pressed()
                if mouse_buttons[0]:
                    pos = pygame.mouse.get_pos()
                    if back_button.contains(pos):
                        leave_requested = True
                    elif new_map_button is not None and new_map_button.contains(pos):
                        do_new_random_map()
                    elif next_gen_button.contains(pos):
                        breed_selected()
                    elif restart_button.contains(pos):
                        restart_training()
                    else:
                        point = Point(*map_position(pos))
                        for nn_car in nn_cars:
                            polygon = Polygon([nn_car.a, nn_car.b, nn_car.c, nn_car.d])
                            if polygon.contains(point):
                                session.toggle_selected_car(nn_car)
                                if nn_car.collided:
                                    nn_car.velocity = 0
                                    nn_car.acceleration = 0
                                break

                if mouse_buttons[2]:
                    pos = pygame.mouse.get_pos()
                    point = Point(*map_position(pos))
                    for nn_car in nn_cars:
                        polygon = Polygon([nn_car.a, nn_car.b, nn_car.c, nn_car.d])
                        if polygon.contains(point):
                            if nn_car not in session.selected_cars:
                                nn_cars.remove(nn_car)
                                if not nn_car.collided:
                                    session.alive_count = max(0, session.alive_count - 1)
                            break

        if leave_requested:
            persist_settings()
            while True:  # loop so cancelling naming returns to save confirm
                confirm_result = run_save_confirm_screen(screen)
                if confirm_result is None:
                    break  # user pressed 取消 → stay in training
                save_record, save_as_preset = confirm_result
                if save_record:
                    record_name = run_record_name_screen(screen)
                    if record_name is None:
                        continue  # go back to save confirm
                    save_training_record(record_name)
                if save_as_preset:
                    preset_name = run_record_name_screen(
                        screen, title="幫這組 Fitness 參數命名"
                    )
                    if preset_name is not None:
                        FitnessPresetStore().save_preset(preset_name, fitness_config)
                return

        redraw_game_window()
        if session.should_end_generation(generation_elapsed_seconds()):
            breed_selected()
        clock.tick(settings.fps)
