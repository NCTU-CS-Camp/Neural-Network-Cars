from datetime import UTC, datetime

import pygame
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from game_engine.backend.assets import load_game_assets
from game_engine.backend.car import Car, configure_car, set_collision_map
from GA.fitness import get_fitness_strategy, select_best_car
from game_engine.backend.record_store import RecordStore
from game_engine.backend.serialization import export_weight_payload
from game_engine.backend.settings import (
    CJK_FONT_PATH,
    HIDDEN_LAYER,
    INPUT_LAYER,
    MAX_SPEED,
    OUTPUT_LAYER,
    SCREEN_SIZE,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    TRAINING_DIFFICULTY_MAPS,
    WHITE,
)
from game_engine.backend.track_generator import generate_random_map
from game_engine.backend.training_session import TrainingSession
from game_engine.frontend.config_store import load_runtime_settings, save_runtime_settings
from game_engine.frontend.profile_store import load_login_profile
from game_engine.frontend.scenes import AppShell
from game_engine.frontend.screens import (
    AppQuit,
    run_login_screen,
    run_main_menu_screen,
    run_record_name_screen,
    run_save_confirm_screen,
    run_training_config_screen,
    run_validation_list_screen,
)
from game_engine.frontend.widgets import Button
from shared.contracts import TrainingRecord


def run():
    pygame.init()
    info = pygame.display.Info()
    screen = pygame.display.set_mode((info.current_w - 40, info.current_h - 80))

    try:
        profile = load_login_profile() or run_login_screen(screen)
        settings = load_runtime_settings()
        settings.nickname = profile.username

        while True:
            choice = run_main_menu_screen(screen, profile)
            if choice == "training":
                result = run_training_config_screen(screen)
                if result is not None:
                    fitness_config, map_difficulty, parent_record = result
                    if map_difficulty == 3:
                        generate_random_map(screen)
                    run_training_loop(screen, settings, profile, fitness_config, map_difficulty)
            else:
                run_validation_list_screen(screen, profile.server_url)
    except AppQuit:
        pass

    pygame.quit()


def run_training_loop(screen, settings, profile, fitness_config, map_difficulty):
    session = TrainingSession.from_settings(settings)
    shell = AppShell(settings)

    assets = load_game_assets()
    game_display = screen
    clock = pygame.time.Clock()

    front_path, back_path = TRAINING_DIFFICULTY_MAPS[map_difficulty]
    bg = pygame.image.load(front_path)
    bg4 = pygame.image.load(back_path)
    configure_car(bg4, assets.white_small_car, MAX_SPEED)
    fitness_strategy = get_fitness_strategy(session.fitness_strategy)

    number_track = 1
    frames = 0
    layer_sizes = [INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]

    car = Car(layer_sizes)
    aux_car = Car(layer_sizes)
    nn_cars = [Car(layer_sizes) for _ in range(session.population_size)]

    W, H = screen.get_size()
    back_button = Button("Back (Esc)", pygame.Rect(W - 200, 16, 180, 44))
    new_map_button = Button("新地圖 (M)", pygame.Rect(W - 200, 70, 180, 44)) if map_difficulty == 3 else None

    info_x = max(W - 235, 1200)
    info_y = 600
    font = pygame.font.Font(CJK_FONT_PATH, 18)
    text1 = font.render("0..9 - Change Mutation", True, WHITE)
    text2 = font.render("LMB - Select/Unselect", True, WHITE)
    text3 = font.render("RMB - Delete", True, WHITE)
    text4 = font.render("L - Show/Hide Lines", True, WHITE)
    text5 = font.render("R - Reset", True, WHITE)
    text6 = font.render("B - Breed", True, WHITE)
    text7 = font.render("C - Clean", True, WHITE)
    text8 = font.render("N - Next Track", True, WHITE)
    text9 = font.render("A - Toggle Player", True, WHITE)
    text10 = font.render("D - Toggle Info", True, WHITE)
    text11 = font.render(
        "M - 新隨機地圖" if map_difficulty == 3 else "M - Breed and Next Track", True, WHITE
    )
    text12 = font.render("F1..F4 - Switch Scenes", True, WHITE)
    text1_rect = text1.get_rect().move(info_x, info_y)
    text2_rect = text2.get_rect().move(info_x, info_y + text1_rect.height)
    text3_rect = text3.get_rect().move(info_x, info_y + 2 * text1_rect.height)
    text4_rect = text4.get_rect().move(info_x, info_y + 3 * text1_rect.height)
    text5_rect = text5.get_rect().move(info_x, info_y + 4 * text1_rect.height)
    text6_rect = text6.get_rect().move(info_x, info_y + 5 * text1_rect.height)
    text7_rect = text7.get_rect().move(info_x, info_y + 6 * text1_rect.height)
    text8_rect = text8.get_rect().move(info_x, info_y + 7 * text1_rect.height)
    text9_rect = text9.get_rect().move(info_x, info_y + 8 * text1_rect.height)
    text10_rect = text10.get_rect().move(info_x, info_y + 9 * text1_rect.height)
    text11_rect = text11.get_rect().move(info_x, info_y + 10 * text1_rect.height)
    text12_rect = text12.get_rect().move(info_x, info_y + 11 * text1_rect.height)

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

    def apply_track_spawn(reset_player=False, reset_images=False):
        spawn_x, spawn_y = track_spawn()
        for nn_car in nn_cars:
            car_image = assets.white_small_car if reset_images else None
            nn_car.reset_state(spawn_x, spawn_y, car_image=car_image)
            nn_car.showlines = session.show_sensor_lines
        if reset_player:
            car.reset_state(spawn_x, spawn_y)
            car.showlines = session.show_sensor_lines
        session.alive_count = len(nn_cars)

    def remove_selected_car(nn_car):
        if nn_car in session.selected_cars:
            session.selected_cars.remove(nn_car)

    def clean_collided_cars():
        nonlocal nn_cars
        kept_cars = []
        for nn_car in nn_cars:
            if nn_car.collided:
                remove_selected_car(nn_car)
            else:
                kept_cars.append(nn_car)
        nn_cars = kept_cars
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
            f"Mutation: {session.mutation_rate}", True, WHITE
        )
        info_text8 = font.render(
            f"Scene: {shell.current_scene.name}", True, WHITE
        )
        info_text9 = font.render(
            f"Fitness: {session.fitness_strategy}", True, WHITE
        )
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

        game_display.blit(text1, text1_rect)
        game_display.blit(text2, text2_rect)
        game_display.blit(text3, text3_rect)
        game_display.blit(text4, text4_rect)
        game_display.blit(text5, text5_rect)
        game_display.blit(text6, text6_rect)
        game_display.blit(text7, text7_rect)
        game_display.blit(text8, text8_rect)
        game_display.blit(text9, text9_rect)
        game_display.blit(text10, text10_rect)
        game_display.blit(text11, text11_rect)
        game_display.blit(text12, text12_rect)

        game_display.blit(info_text1, info_text1_rect)
        game_display.blit(info_text2, info_text2_rect)
        game_display.blit(info_text3, info_text3_rect)
        game_display.blit(info_text4, info_text4_rect)
        game_display.blit(info_text5, info_text5_rect)
        game_display.blit(info_text6, info_text6_rect)
        game_display.blit(info_text7, info_text7_rect)
        game_display.blit(info_text8, info_text8_rect)
        game_display.blit(info_text9, info_text9_rect)

    def breed_selected():
        nonlocal nn_cars
        if len(session.selected_cars) != 2:
            return False
        nn_cars = session.breed_population(
            population=nn_cars,
            aux_car=aux_car,
            car_factory=Car,
            layer_sizes=layer_sizes,
            assets=assets,
        )
        apply_track_spawn()
        return True

    def redraw_game_window():
        nonlocal frames

        frames += 1
        game_display.blit(bg, (0, 0))

        for nn_car in nn_cars:
            if not nn_car.collided:
                nn_car.update()

            if nn_car.collision():
                nn_car.collided = True
                setattr(nn_car, "fitness_score", fitness_strategy(nn_car))
                session.mark_collision(nn_car)
            else:
                nn_car.feedforward()
                nn_car.takeAction()
            nn_car.draw(game_display)

        if session.show_player:
            car.update()
            if car.collision():
                car.resetPosition()
                car.update()
            car.draw(game_display)

        shell.current_scene.render_overlay(game_display, font)
        if session.show_debug_overlay:
            display_texts()

        mouse_pos = pygame.mouse.get_pos()
        back_button.update_hover(mouse_pos)
        back_button.draw(game_display, font)
        if new_map_button is not None:
            new_map_button.update_hover(mouse_pos)
            new_map_button.draw(game_display, font)

        pygame.display.update()

    def do_new_random_map():
        nonlocal bg, bg4
        generate_random_map(game_display)
        bg = pygame.image.load(TRACK_FRONT_PATH)
        bg4 = pygame.image.load(TRACK_BACK_PATH)
        set_collision_map(bg4)
        configure_car(bg4, assets.white_small_car, MAX_SPEED)
        apply_track_spawn(reset_player=True)

    def save_training_record():
        best_car = select_best_car(nn_cars, fitness_config)
        payload = export_weight_payload(
            best_car,
            generation=session.generation,
            track_id=f"training-{map_difficulty}",
            track_seed=settings.track_seed,
            nickname=profile.username,
        )
        record_name = run_record_name_screen(screen)
        record = TrainingRecord(
            record_id="",
            record_name=record_name,
            saved_at=datetime.now(UTC).isoformat(),
            group_id=profile.group_id,
            username=profile.username,
            layer_sizes=payload.layer_sizes,
            weights=payload.weights,
            biases=payload.biases,
            fitness_config=fitness_config,
            map_difficulty=map_difficulty,
        )
        RecordStore().save_record(record)

    apply_sensor_line_state()

    while True:
        leave_requested = False

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                persist_settings()
                raise AppQuit()

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    leave_requested = True
                if event.key == pygame.K_F1:
                    shell.set_scene("home")
                if event.key == pygame.K_F2:
                    shell.set_scene("settings")
                if event.key == pygame.K_F3:
                    shell.set_scene("training")
                if event.key == pygame.K_F4:
                    shell.set_scene("replay")
                if event.key == ord("l"):
                    session.show_sensor_lines = not session.show_sensor_lines
                    apply_sensor_line_state()
                if event.key == ord("c"):
                    clean_collided_cars()
                if event.key == ord("a"):
                    session.show_player = not session.show_player
                if event.key == ord("d"):
                    session.show_debug_overlay = not session.show_debug_overlay
                if event.key == ord("n"):
                    number_track = 2
                    session.track_index = 2
                    generate_random_map(game_display)
                    bg = pygame.image.load(TRACK_FRONT_PATH)
                    bg4 = pygame.image.load(TRACK_BACK_PATH)
                    set_collision_map(bg4)
                    apply_track_spawn(reset_player=True)
                if event.key == ord("b"):
                    breed_selected()
                if event.key == ord("m"):
                    if map_difficulty == 3:
                        do_new_random_map()
                    elif breed_selected():
                        number_track = 2
                        session.track_index = 2
                        generate_random_map(game_display)
                        bg = pygame.image.load(TRACK_FRONT_PATH)
                        bg4 = pygame.image.load(TRACK_BACK_PATH)
                        set_collision_map(bg4)
                        apply_track_spawn(reset_player=True)
                if event.key == ord("r"):
                    session.reset_generation()
                    nn_cars.clear()
                    for _ in range(session.population_size):
                        nn_cars.append(Car(layer_sizes))
                    apply_track_spawn(reset_player=True, reset_images=True)
                if event.key == ord("0"):
                    session.mutation_rate = 0
                if event.key == ord("1"):
                    session.mutation_rate = 10
                if event.key == ord("2"):
                    session.mutation_rate = 20
                if event.key == ord("3"):
                    session.mutation_rate = 30
                if event.key == ord("4"):
                    session.mutation_rate = 40
                if event.key == ord("5"):
                    session.mutation_rate = 50
                if event.key == ord("6"):
                    session.mutation_rate = 60
                if event.key == ord("7"):
                    session.mutation_rate = 70
                if event.key == ord("8"):
                    session.mutation_rate = 80
                if event.key == ord("9"):
                    session.mutation_rate = 90

            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_buttons = pygame.mouse.get_pressed()
                if mouse_buttons[0]:
                    pos = pygame.mouse.get_pos()
                    if back_button.contains(pos):
                        leave_requested = True
                    elif new_map_button is not None and new_map_button.contains(pos):
                        do_new_random_map()
                    else:
                        point = Point(pos[0], pos[1])
                        for nn_car in nn_cars:
                            polygon = Polygon([nn_car.a, nn_car.b, nn_car.c, nn_car.d])
                            if polygon.contains(point):
                                was_selected = nn_car in session.selected_cars
                                session.toggle_selected_car(nn_car)
                                if was_selected:
                                    if nn_car.car_image == assets.white_big_car:
                                        nn_car.car_image = assets.white_small_car
                                    if nn_car.car_image == assets.green_big_car:
                                        nn_car.car_image = assets.green_small_car
                                elif nn_car in session.selected_cars:
                                    if nn_car.car_image == assets.white_small_car:
                                        nn_car.car_image = assets.white_big_car
                                    if nn_car.car_image == assets.green_small_car:
                                        nn_car.car_image = assets.green_big_car
                                if nn_car.collided:
                                    nn_car.velocity = 0
                                    nn_car.acceleration = 0
                                if not nn_car.collided:
                                    nn_car.update()
                                break

                if mouse_buttons[2]:
                    pos = pygame.mouse.get_pos()
                    point = Point(pos[0], pos[1])
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
            if run_save_confirm_screen(screen):
                save_training_record()
            return

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            car.rotate(-5)
        if keys[pygame.K_RIGHT]:
            car.rotate(5)
        if keys[pygame.K_UP]:
            car.set_accel(0.2)
        else:
            car.set_accel(0)
        if keys[pygame.K_DOWN]:
            car.set_accel(-0.2)

        redraw_game_window()
        clock.tick(settings.fps)
