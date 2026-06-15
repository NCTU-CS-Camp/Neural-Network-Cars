import pygame
from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from backend.assets import load_game_assets
from backend.car import Car, configure_car, set_collision_map
from backend.genetic import (
    mutateOneBiasesGene,
    mutateOneWeightGene,
    uniformCrossOverBiases,
    uniformCrossOverWeights,
)
from backend.settings import (
    FPS,
    HIDDEN_LAYER,
    INPUT_LAYER,
    MAX_SPEED,
    NUM_OF_NN_CARS,
    OUTPUT_LAYER,
    SCREEN_SIZE,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    WHITE,
)
from backend.track_generator import generate_random_map


def run():
    pygame.init()

    assets = load_game_assets()
    gameDisplay = pygame.display.set_mode(SCREEN_SIZE)
    clock = pygame.time.Clock()

    configure_car(assets.bg4, assets.white_small_car, MAX_SPEED)

    bg = assets.bg
    bg4 = assets.bg4
    generation = 1
    mutationRate = 90
    selectedCars = []
    selected = 0
    lines = True
    player = True
    display_info = True
    frames = 0
    number_track = 1
    alive = NUM_OF_NN_CARS

    car = Car([INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER])
    auxcar = Car([INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER])
    nnCars = [Car([INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]) for _ in range(NUM_OF_NN_CARS)]

    infoX = 1365
    infoY = 600
    font = pygame.font.Font('freesansbold.ttf', 18)
    text1 = font.render('0..9 - Change Mutation', True, WHITE)
    text2 = font.render('LMB - Select/Unselect', True, WHITE)
    text3 = font.render('RMB - Delete', True, WHITE)
    text4 = font.render('L - Show/Hide Lines', True, WHITE)
    text5 = font.render('R - Reset', True, WHITE)
    text6 = font.render('B - Breed', True, WHITE)
    text7 = font.render('C - Clean', True, WHITE)
    text8 = font.render('N - Next Track', True, WHITE)
    text9 = font.render('A - Toggle Player', True, WHITE)
    text10 = font.render('D - Toggle Info', True, WHITE)
    text11 = font.render('M - Breed and Next Track', True, WHITE)
    text1Rect = text1.get_rect().move(infoX, infoY)
    text2Rect = text2.get_rect().move(infoX, infoY+text1Rect.height)
    text3Rect = text3.get_rect().move(infoX, infoY+2*text1Rect.height)
    text4Rect = text4.get_rect().move(infoX, infoY+3*text1Rect.height)
    text5Rect = text5.get_rect().move(infoX, infoY+4*text1Rect.height)
    text6Rect = text6.get_rect().move(infoX, infoY+5*text1Rect.height)
    text7Rect = text7.get_rect().move(infoX, infoY+6*text1Rect.height)
    text8Rect = text8.get_rect().move(infoX, infoY+7*text1Rect.height)
    text9Rect = text9.get_rect().move(infoX, infoY+8*text1Rect.height)
    text10Rect = text10.get_rect().move(infoX, infoY+9*text1Rect.height)
    text11Rect = text11.get_rect().move(infoX, infoY+10*text1Rect.height)

    def displayTexts():
        infotextX = 20
        infotextY = 600
        infotext1 = font.render('Gen ' + str(generation), True, WHITE)
        infotext2 = font.render('Cars: ' + str(NUM_OF_NN_CARS), True, WHITE)
        infotext3 = font.render('Alive: ' + str(alive), True, WHITE)
        infotext4 = font.render('Selected: ' + str(selected), True, WHITE)
        if lines == True:
            infotext5 = font.render('Lines ON', True, WHITE)
        else:
            infotext5 = font.render('Lines OFF', True, WHITE)
        if player == True:
            infotext6 = font.render('Player ON', True, WHITE)
        else:
            infotext6 = font.render('Player OFF', True, WHITE)
        infotext9 = font.render('FPS: 30', True, WHITE)
        infotext1Rect = infotext1.get_rect().move(infotextX, infotextY)
        infotext2Rect = infotext2.get_rect().move(infotextX, infotextY+infotext1Rect.height)
        infotext3Rect = infotext3.get_rect().move(infotextX, infotextY+2*infotext1Rect.height)
        infotext4Rect = infotext4.get_rect().move(infotextX, infotextY+3*infotext1Rect.height)
        infotext5Rect = infotext5.get_rect().move(infotextX, infotextY+4*infotext1Rect.height)
        infotext6Rect = infotext6.get_rect().move(infotextX, infotextY+5*infotext1Rect.height)
        infotext9Rect = infotext9.get_rect().move(infotextX, infotextY+6*infotext1Rect.height)

        gameDisplay.blit(text1, text1Rect)
        gameDisplay.blit(text2, text2Rect)
        gameDisplay.blit(text3, text3Rect)
        gameDisplay.blit(text4, text4Rect)
        gameDisplay.blit(text5, text5Rect)
        gameDisplay.blit(text6, text6Rect)
        gameDisplay.blit(text7, text7Rect)
        gameDisplay.blit(text8, text8Rect)
        gameDisplay.blit(text9, text9Rect)
        gameDisplay.blit(text10, text10Rect)
        gameDisplay.blit(text11, text11Rect)

        gameDisplay.blit(infotext1, infotext1Rect)
        gameDisplay.blit(infotext2, infotext2Rect)
        gameDisplay.blit(infotext3, infotext3Rect)
        gameDisplay.blit(infotext4, infotext4Rect)
        gameDisplay.blit(infotext5, infotext5Rect)
        gameDisplay.blit(infotext6, infotext6Rect)
        gameDisplay.blit(infotext9, infotext9Rect)

    def breed_selected():
        nonlocal alive, generation, selected
        if len(selectedCars) != 2:
            return

        for nncar in nnCars:
            nncar.score = 0

        alive = NUM_OF_NN_CARS
        generation += 1
        selected = 0
        nnCars.clear()

        for _ in range(NUM_OF_NN_CARS):
            nnCars.append(Car([INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]))

        for i in range(0, NUM_OF_NN_CARS-2, 2):
            uniformCrossOverWeights(selectedCars[0], selectedCars[1], nnCars[i], nnCars[i+1])
            uniformCrossOverBiases(selectedCars[0], selectedCars[1], nnCars[i], nnCars[i+1])

        nnCars[NUM_OF_NN_CARS-2] = selectedCars[0]
        nnCars[NUM_OF_NN_CARS-1] = selectedCars[1]

        nnCars[NUM_OF_NN_CARS-2].car_image = assets.green_small_car
        nnCars[NUM_OF_NN_CARS-1].car_image = assets.green_small_car

        nnCars[NUM_OF_NN_CARS-2].resetPosition()
        nnCars[NUM_OF_NN_CARS-1].resetPosition()

        nnCars[NUM_OF_NN_CARS-2].collided = False
        nnCars[NUM_OF_NN_CARS-1].collided = False

        for i in range(NUM_OF_NN_CARS-2):
            for _ in range(mutationRate):
                mutateOneWeightGene(nnCars[i], auxcar)
                mutateOneWeightGene(auxcar, nnCars[i])
                mutateOneBiasesGene(nnCars[i], auxcar)
                mutateOneBiasesGene(auxcar, nnCars[i])

        if number_track != 1:
            for nncar in nnCars:
                nncar.x = 140
                nncar.y = 610

        selectedCars.clear()

    def redrawGameWindow():
        nonlocal alive, frames

        frames += 1
        gameDisplay.blit(bg, (0, 0))

        for nncar in nnCars:
            if not nncar.collided:
                nncar.update()

            if nncar.collision():
                nncar.collided = True
                if nncar.yaReste == False:
                    alive -= 1
                    nncar.yaReste = True
            else:
                nncar.feedforward()
                nncar.takeAction()
            nncar.draw(gameDisplay)

        if player:
            car.update()
            if car.collision():
                car.resetPosition()
                car.update()
            car.draw(gameDisplay)
        if display_info:
            displayTexts()
        pygame.display.update()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

            if event.type == pygame.KEYDOWN:
                if event.key == ord("l"):
                    car.showLines()
                    lines = not lines
                if event.key == ord("c"):
                    for nncar in nnCars:
                        if nncar.collided == True:
                            nnCars.remove(nncar)
                            if nncar.yaReste == False:
                                alive -= 1
                if event.key == ord("a"):
                    player = not player
                if event.key == ord("d"):
                    display_info = not display_info
                if event.key == ord("n"):
                    number_track = 2
                    for nncar in nnCars:
                        nncar.velocity = 0
                        nncar.acceleration = 0
                        nncar.x = 140
                        nncar.y = 610
                        nncar.angle = 180
                        nncar.collided = False
                    generate_random_map(gameDisplay)
                    bg = pygame.image.load(TRACK_FRONT_PATH)
                    bg4 = pygame.image.load(TRACK_BACK_PATH)
                    set_collision_map(bg4)

                if event.key == ord("b"):
                    breed_selected()

                if event.key == ord("m"):
                    breed_selected()

                    for nncar in nnCars:
                        nncar.x = 140
                        nncar.y = 610

                    number_track = 2
                    for nncar in nnCars:
                        nncar.velocity = 0
                        nncar.acceleration = 0
                        nncar.x = 140
                        nncar.y = 610
                        nncar.angle = 180
                        nncar.collided = False
                    generate_random_map(gameDisplay)
                    bg = pygame.image.load(TRACK_FRONT_PATH)
                    bg4 = pygame.image.load(TRACK_BACK_PATH)
                    set_collision_map(bg4)
                if event.key == ord("r"):
                    generation = 1
                    alive = NUM_OF_NN_CARS
                    nnCars.clear()
                    selectedCars.clear()
                    for _ in range(NUM_OF_NN_CARS):
                        nnCars.append(Car([INPUT_LAYER, HIDDEN_LAYER, OUTPUT_LAYER]))
                    for nncar in nnCars:
                        if number_track == 1:
                            nncar.x = 120
                            nncar.y = 480
                        elif number_track == 2:
                            nncar.x = 100
                            nncar.y = 300
                if event.key == ord("0"):
                    mutationRate = 0
                if event.key == ord("1"):
                    mutationRate = 10
                if event.key == ord("2"):
                    mutationRate = 20
                if event.key == ord("3"):
                    mutationRate = 30
                if event.key == ord("4"):
                    mutationRate = 40
                if event.key == ord("5"):
                    mutationRate = 50
                if event.key == ord("6"):
                    mutationRate = 60
                if event.key == ord("7"):
                    mutationRate = 70
                if event.key == ord("8"):
                    mutationRate = 80
                if event.key == ord("9"):
                    mutationRate = 90

            if event.type == pygame.MOUSEBUTTONDOWN:
                mouses = pygame.mouse.get_pressed()
                if mouses[0]:
                    pos = pygame.mouse.get_pos()
                    point = Point(pos[0], pos[1])
                    for nncar in nnCars:
                        polygon = Polygon([nncar.a, nncar.b, nncar.c, nncar.d])
                        if polygon.contains(point):
                            if nncar in selectedCars:
                                selectedCars.remove(nncar)
                                selected -= 1
                                if nncar.car_image == assets.white_big_car:
                                    nncar.car_image = assets.white_small_car
                                if nncar.car_image == assets.green_big_car:
                                    nncar.car_image = assets.green_small_car
                                if nncar.collided:
                                    nncar.velocity = 0
                                    nncar.acceleration = 0
                                nncar.update()
                            else:
                                if len(selectedCars) < 2:
                                    selectedCars.append(nncar)
                                    selected += 1
                                    if nncar.car_image == assets.white_small_car:
                                        nncar.car_image = assets.white_big_car
                                    if nncar.car_image == assets.green_small_car:
                                        nncar.car_image = assets.green_big_car
                                    if nncar.collided:
                                        nncar.velocity = 0
                                        nncar.acceleration = 0
                                    nncar.update()
                            break

                if mouses[2]:
                    pos = pygame.mouse.get_pos()
                    point = Point(pos[0], pos[1])
                    for nncar in nnCars:
                        polygon = Polygon([nncar.a, nncar.b, nncar.c, nncar.d])
                        if polygon.contains(point):
                            if nncar not in selectedCars:
                                nnCars.remove(nncar)
                                alive -= 1
                            break

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

        redrawGameWindow()
        clock.tick(FPS)
