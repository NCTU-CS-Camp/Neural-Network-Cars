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
    FONT_PATH,
    HIDDEN_LAYER,
    INPUT_LAYER,
    OUTPUT_LAYER,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    TRACK_HALF_WIDTH,
    TRACK_METADATA_PATH,
    TRAINING_DIFFICULTY_MAPS,
    WHITE,
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
    info = pygame.display.Info()
    win_w = int(info.current_w * 0.9)
    win_h = int(info.current_h * 0.9)
    screen = pygame.display.set_mode((win_w, win_h))

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

    W, H = screen.get_size()
    back_button = Button("Back", pygame.Rect(W - 200, 16, 180, 44))
    new_map_button = Button("新地圖", pygame.Rect(W - 200, 70, 180, 44)) if map_difficulty == 3 else None
    next_gen_button_y = 124 if new_map_button is not None else 70
    next_gen_button = Button(
        "下一代 (Next Gen)",
        pygame.Rect(W - 200, next_gen_button_y, 180, 44),
    )
    restart_button = Button(
        "Restart",
        pygame.Rect(W - 200, next_gen_button.rect.bottom + 10, 180, 44),
    )

    # Virtual canvas at the map's native resolution; rendered then scaled to the
    # physical window. This keeps car coordinates correct (they live in 1600×900
    # space) while the window can be any size.
    MAP_W, MAP_H = bg.get_size()
    map_canvas = pygame.Surface((MAP_W, MAP_H))
    _map_scale = min(W / MAP_W, H / MAP_H)
    _map_dst_w = int(MAP_W * _map_scale)
    _map_dst_h = int(MAP_H * _map_scale)
    _map_dst_x = (W - _map_dst_w) // 2
    _map_dst_y = (H - _map_dst_h) // 2

    def map_position(screen_position):
        screen_x, screen_y = screen_position
        return (
            (screen_x - _map_dst_x) * MAP_W / _map_dst_w,
            (screen_y - _map_dst_y) * MAP_H / _map_dst_h,
        )

    font = pygame.font.Font(str(FONT_PATH), 18)
    speed_text = font.render(f"Max Speed: {settings.max_speed}", True, WHITE)

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

    def display_texts():
        info_text_x = 20
        info_text_y = 600
        info_text1 = font.render(f"Gen {session.generation}", True, WHITE)
        info_text2 = font.render(f"Cars: {session.population_size}", True, WHITE)
        info_text3 = font.render(f"Alive: {session.alive_count}", True, WHITE)
        info_text4 = font.render(
            f"Selected: {len(session.selected_cars)}", True, WHITE
        )
        info_text5 = font.render(
            "Lines ON" if session.show_sensor_lines else "Lines OFF", True, WHITE
        )
        info_text6 = font.render(
            "Player ON" if session.show_player else "Player OFF", True, WHITE
        )
        info_text7 = font.render(
            f"Scene: {shell.current_scene.name}", True, WHITE
        )
        info_text8 = font.render(
            f"Fitness: {fitness_strategy.name}", True, WHITE
        )
        remaining_seconds = max(
            0.0,
            session.generation_duration_seconds - generation_elapsed_seconds(),
        )
        info_text9 = font.render(
            f"Next generation: {remaining_seconds:.1f}s", True, WHITE
        )
        info_text10 = font.render(submit_status, True, WHITE)
        info_text1_rect = info_text1.get_rect().move(info_text_x, info_text_y)
        info_text2_rect = info_text2.get_rect().move(
            info_text_x, info_text_y + info_text1_rect.height
        )
        info_text3_rect = info_text3.get_rect().move(
            info_text_x, info_text_y + 2 * info_text1_rect.height
        )
        info_text4_rect = info_text4.get_rect().move(
            info_text_x, info_text_y + 3 * info_text1_rect.height
        )
        info_text5_rect = info_text5.get_rect().move(
            info_text_x, info_text_y + 4 * info_text1_rect.height
        )
        info_text6_rect = info_text6.get_rect().move(
            info_text_x, info_text_y + 5 * info_text1_rect.height
        )
        info_text7_rect = info_text7.get_rect().move(
            info_text_x, info_text_y + 6 * info_text1_rect.height
        )
        info_text8_rect = info_text8.get_rect().move(
            info_text_x, info_text_y + 7 * info_text1_rect.height
        )
        info_text9_rect = info_text9.get_rect().move(
            info_text_x, info_text_y + 8 * info_text1_rect.height
        )
        info_text10_rect = info_text10.get_rect().move(
            info_text_x, info_text_y + 9 * info_text1_rect.height
        )

        game_display.blit(info_text1, info_text1_rect)
        game_display.blit(info_text2, info_text2_rect)
        game_display.blit(info_text3, info_text3_rect)
        game_display.blit(info_text4, info_text4_rect)
        game_display.blit(info_text5, info_text5_rect)
        game_display.blit(info_text6, info_text6_rect)
        game_display.blit(info_text7, info_text7_rect)
        game_display.blit(info_text8, info_text8_rect)
        game_display.blit(info_text9, info_text9_rect)
        game_display.blit(info_text10, info_text10_rect)

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

    def draw_fitness_leaders(target):
        if not nn_cars:
            return

        leader_colors = ((255, 215, 0), (80, 200, 255))
        leaders = select_best_cars(
            nn_cars,
            count=min(2, len(nn_cars)),
        )
        for rank, (leader, color) in enumerate(
            zip(leaders, leader_colors, strict=False),
            start=1,
        ):
            center = (round(leader.x), round(leader.y))
            radius = round(max(leader.width, leader.height) / 2) + 10
            pygame.draw.circle(target, color, center, radius, width=4)

            label = font.render(
                f"TOP {rank}  Fitness: {leader.fitness_score:.1f}",
                True,
                color,
            )
            label_rect = label.get_rect(
                midbottom=(center[0], center[1] - radius - 5)
            )
            pygame.draw.rect(
                target,
                (0, 0, 0),
                label_rect.inflate(8, 4),
                border_radius=4,
            )
            target.blit(label, label_rect)

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

        shell.current_scene.render_overlay(map_canvas, font)

        # Scale the game canvas to the physical window, then draw UI on top.
        game_display.fill((0, 0, 0))
        game_display.blit(
            pygame.transform.scale(map_canvas, (_map_dst_w, _map_dst_h)),
            (_map_dst_x, _map_dst_y),
        )
        if session.show_debug_overlay:
            display_texts()

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        back_button.draw(game_display, font)
        next_gen_button.update_hover(mouse_pos)
        next_gen_button.draw(game_display, font)
        restart_button.update_hover(mouse_pos)
        restart_button.draw(game_display, font)
        if new_map_button is not None:
            new_map_button.update_hover(mouse_pos)
            new_map_button.draw(game_display, font)
        seed_text = font.render(
            f"NN Seed: {session.evolution_seed}",
            True,
            WHITE,
        )
        game_display.blit(
            seed_text,
            seed_text.get_rect(topright=(W - 20, restart_button.rect.bottom + 12)),
        )
        game_display.blit(
            speed_text,
            speed_text.get_rect(topright=(W - 20, restart_button.rect.bottom + 34)),
        )

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

    def save_training_record():
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
        record_name = run_record_name_screen(screen)
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
            save_record, save_as_preset = run_save_confirm_screen(screen)
            if save_record:
                save_training_record()
            if save_as_preset:
                preset_name = run_record_name_screen(
                    screen, title="幫這組 Fitness 參數命名"
                )
                FitnessPresetStore().save_preset(preset_name, fitness_config)
            return

        redraw_game_window()
        if session.should_end_generation(generation_elapsed_seconds()):
            breed_selected()
        clock.tick(settings.fps)
