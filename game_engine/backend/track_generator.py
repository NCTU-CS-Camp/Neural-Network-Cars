import json
import random

import pygame
from PIL import Image

from game_engine.backend.settings import (
    TRACK_ASSETS_DIR,
    TRACK_BACK_PATH,
    TRACK_FRONT_PATH,
    TRACK_HALF_WIDTH,
    TRACK_METADATA_PATH,
)


class Cell:
    wall_pairs = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.walls = {'N': True, 'S': True, 'E': True, 'W': True}
        self.color = 0, 0, 0
        self.track = ""

    def has_all_walls(self):
        return all(self.walls.values())

    def knock_down_wall(self, other, wall):
        self.walls[wall] = False
        other.walls[Cell.wall_pairs[wall]] = False


class Maze:
    def __init__(self, nx, ny, ix=0, iy=0):
        self.nx, self.ny = nx, ny
        self.ix, self.iy = ix, iy
        self.maze_map = [[Cell(x, y) for y in range(ny)] for x in range(nx)]

    def cell_at(self, x, y):
        return self.maze_map[x][y]

    def find_valid_neighbours(self, cell):
        delta = [('W', (-1, 0)),
                 ('E', (1, 0)),
                 ('S', (0, 1)),
                 ('N', (0, -1))]
        neighbours = []
        for direction, (dx, dy) in delta:
            x2, y2 = cell.x + dx, cell.y + dy
            if (0 <= x2 < self.nx) and (0 <= y2 < self.ny):
                neighbour = self.cell_at(x2, y2)
                if neighbour.has_all_walls():
                    neighbours.append((direction, neighbour))
        return neighbours


def _tile_name(cell, *, is_start=False):
    if is_start:
        return "Initial"
    if not cell.walls["N"] and not cell.walls["S"]:
        return "Straight2"
    if not cell.walls["E"] and not cell.walls["W"]:
        return "Straight1"
    if not cell.walls["N"] and not cell.walls["W"]:
        return "Curve3"
    if not cell.walls["W"] and not cell.walls["S"]:
        return "Curve2"
    if not cell.walls["S"] and not cell.walls["E"]:
        return "Curve1"
    if not cell.walls["E"] and not cell.walls["N"]:
        return "Curve4"
    return None


def _save_track_metadata(maze, *, block_size, offset_x, offset_y, start, finish):
    tiles = []
    for y in range(maze.ny):
        for x in range(maze.nx):
            tile_name = _tile_name(
                maze.cell_at(x, y),
                is_start=(x, y) == start,
            )
            if tile_name is not None:
                tiles.append({"x": x, "y": y, "tile": tile_name})

    metadata = {
        "schema_version": 1,
        "name": "random_generated_track",
        "grid": {
            "cols": maze.nx,
            "rows": maze.ny,
            "cell_size": block_size,
            "offset_x": offset_x,
            "offset_y": offset_y,
        },
        "start": {"x": start[0], "y": start[1]},
        "finish": {"x": finish[0], "y": finish[1]},
        "half_width_px": TRACK_HALF_WIDTH,
        "tiles": tiles,
    }
    TRACK_METADATA_PATH.write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )


def generate_random_map(screen):
    SCREEN = screen

    GREEN = (0, 255, 128)

    WINDOW_HEIGHT = 730
    WINDOW_WIDTH = 1460

    blockSize = 146
    rows, cols = (int(WINDOW_WIDTH/blockSize), int(WINDOW_HEIGHT/blockSize))
    maze = Maze(rows, cols, 0, 0)

    trackLenght = 1
    movex = 70
    movey = 85

    startx, starty = 0, 3
    currentCell = maze.cell_at(startx, starty)

    straight1 = pygame.image.load(TRACK_ASSETS_DIR / "Straight1.png")
    straight1Rect = straight1.get_rect()

    straight2 = pygame.image.load(TRACK_ASSETS_DIR / "Straight2.png")
    straight2Rect = straight2.get_rect()

    curve1 = pygame.image.load(TRACK_ASSETS_DIR / "Curve1.png")
    curve1Rect = curve1.get_rect()

    curve2 = pygame.image.load(TRACK_ASSETS_DIR / "Curve2.png")
    curve2Rect = curve2.get_rect()

    curve3 = pygame.image.load(TRACK_ASSETS_DIR / "Curve3.png")
    curve3Rect = curve3.get_rect()

    curve4 = pygame.image.load(TRACK_ASSETS_DIR / "Curve4.png")
    curve4Rect = curve4.get_rect()

    straight1Top = pygame.image.load(TRACK_ASSETS_DIR / "Straight1Top.png")
    straight1RectTop = straight1Top.get_rect()

    straight2Top = pygame.image.load(TRACK_ASSETS_DIR / "Straight2Top.png")
    straight2RectTop = straight2Top.get_rect()

    curve1Top = pygame.image.load(TRACK_ASSETS_DIR / "Curve1Top.png")
    curve1RectTop = curve1Top.get_rect()

    curve2Top = pygame.image.load(TRACK_ASSETS_DIR / "Curve2Top.png")
    curve2RectTop = curve2Top.get_rect()

    curve3Top = pygame.image.load(TRACK_ASSETS_DIR / "Curve3Top.png")
    curve3RectTop = curve3Top.get_rect()

    curve4Top = pygame.image.load(TRACK_ASSETS_DIR / "Curve4Top.png")
    curve4RectTop = curve4Top.get_rect()

    initialTop = pygame.image.load(TRACK_ASSETS_DIR / "Initial.png")
    initialRectTop = initialTop.get_rect()

    bg = pygame.image.load(TRACK_ASSETS_DIR / "Background.png")

    while True:
        if len(maze.find_valid_neighbours(currentCell)) > 0:
            if currentCell.x == 0 and currentCell.y == 3:
                oldCell = currentCell
                currentCell = maze.cell_at(oldCell.x, oldCell.y-1)
                currentCell.color = GREEN
                oldCell.knock_down_wall(currentCell, "N")
                trackLenght += 1
            else:
                random_unvisited_direction = random.choice(maze.find_valid_neighbours(currentCell))[0]
                oldCell = currentCell
                if random_unvisited_direction == "N":
                    currentCell = maze.cell_at(oldCell.x, oldCell.y-1)
                elif random_unvisited_direction == "S":
                    currentCell = maze.cell_at(oldCell.x, oldCell.y+1)
                elif random_unvisited_direction == "E":
                    currentCell = maze.cell_at(oldCell.x+1, oldCell.y)
                elif random_unvisited_direction == "W":
                    currentCell = maze.cell_at(oldCell.x-1, oldCell.y)

                oldCell.knock_down_wall(currentCell, random_unvisited_direction)
                trackLenght += 1

        else:
            if currentCell.x == 0 and currentCell.y == 4 and trackLenght > 40:
                SCREEN.fill((0, 0, 0))
                currentCell.knock_down_wall(maze.cell_at(0, 3), "N")

                _save_track_metadata(
                    maze,
                    block_size=blockSize,
                    offset_x=movex,
                    offset_y=movey,
                    start=(startx, starty),
                    finish=(0, 4),
                )

                for x in range(0, WINDOW_WIDTH, blockSize):
                    for y in range(0, WINDOW_HEIGHT, blockSize):
                        currentCell = maze.cell_at(int(x/blockSize), int(y/blockSize))
                        currentCell.color = (0, 0, 1, 255)

                for x in range(0, WINDOW_WIDTH, blockSize):
                    for y in range(0, WINDOW_HEIGHT, blockSize):
                        currentCell = maze.cell_at(int(x/blockSize), int(y/blockSize))

                        if not currentCell.walls["N"] and not currentCell.walls["S"]:
                            SCREEN.blit(straight2, straight2Rect.move(x+movex, y+movey))
                        elif not currentCell.walls["E"] and not currentCell.walls["W"]:
                            SCREEN.blit(straight1, straight1Rect.move(x+movex, y+movey))
                        elif not currentCell.walls["N"] and not currentCell.walls["W"]:
                            SCREEN.blit(curve3, curve3Rect.move(x+movex, y+movey))
                        elif not currentCell.walls["W"] and not currentCell.walls["S"]:
                            SCREEN.blit(curve2, curve2Rect.move(x+movex, y+movey))
                        elif not currentCell.walls["S"] and not currentCell.walls["E"]:
                            SCREEN.blit(curve1, curve1Rect.move(x+movex, y+movey))
                        elif not currentCell.walls["E"] and not currentCell.walls["N"]:
                            SCREEN.blit(curve4, curve4Rect.move(x+movex, y+movey))

                pygame.image.save(SCREEN, TRACK_BACK_PATH)
                img = Image.open(TRACK_BACK_PATH)
                img = img.convert("RGBA")
                pixdata = img.load()
                for y in range(img.size[1]):
                    for x in range(img.size[0]):
                        if pixdata[x, y] == (0, 0, 0, 255) or pixdata[x, y] == (0, 0, 1, 255):
                            pixdata[x, y] = (0, 0, 0, 0)
                img.save(TRACK_BACK_PATH)

                SCREEN.blit(bg, (0, 0))
                for x in range(0, WINDOW_WIDTH, blockSize):
                    for y in range(0, WINDOW_HEIGHT, blockSize):
                        if x == 0 and y == 3*blockSize:
                            SCREEN.blit(initialTop, initialRectTop.move(x-20+movex, y+movey))
                        else:
                            currentCell = maze.cell_at(int(x/blockSize), int(y/blockSize))
                            if not currentCell.walls["N"] and not currentCell.walls["S"]:
                                SCREEN.blit(straight2Top, straight2RectTop.move(x-20+movex, y+movey))
                            elif not currentCell.walls["E"] and not currentCell.walls["W"]:
                                SCREEN.blit(straight1Top, straight1RectTop.move(x+movex, y-20+movey))
                            elif not currentCell.walls["N"] and not currentCell.walls["W"]:
                                SCREEN.blit(curve3Top, curve3RectTop.move(x-15+movex, y-15+movey))
                            elif not currentCell.walls["W"] and not currentCell.walls["S"]:
                                SCREEN.blit(curve2Top, curve2RectTop.move(x-15+movex, y-15+movey))
                            elif not currentCell.walls["E"] and not currentCell.walls["N"]:
                                SCREEN.blit(curve4Top, curve4RectTop.move(x-15+movex, y-15+movey))
                            elif not currentCell.walls["S"] and not currentCell.walls["E"]:
                                SCREEN.blit(curve1Top, curve1RectTop.move(x-15+movex, y-15+movey))

                pygame.image.save(SCREEN, TRACK_FRONT_PATH)
                break

            else:
                trackLenght = 0
                for x in range(0, WINDOW_WIDTH, blockSize):
                    for y in range(0, WINDOW_HEIGHT, blockSize):
                        maze.cell_at(int(x/blockSize), int(y/blockSize)).walls["N"] = True
                        maze.cell_at(int(x/blockSize), int(y/blockSize)).walls["S"] = True
                        maze.cell_at(int(x/blockSize), int(y/blockSize)).walls["E"] = True
                        maze.cell_at(int(x/blockSize), int(y/blockSize)).walls["W"] = True
                        maze.cell_at(int(x/blockSize), int(y/blockSize)).color = 0, 0, 0

                maze.cell_at(3, 3).walls["N"] = False
                maze.cell_at(4, 3).walls["N"] = False
                maze.cell_at(5, 3).walls["N"] = False
                maze.cell_at(6, 3).walls["N"] = False

                currentCell = maze.cell_at(startx, starty)


def generateRandomMap(screen):
    return generate_random_map(screen)
