import pygame

from backend.settings import SCREEN_SIZE
from backend.track_generator import generate_random_map


def main():
    pygame.init()
    screen = pygame.display.set_mode(SCREEN_SIZE)
    generate_random_map(screen)
    pygame.quit()


if __name__ == "__main__":
    main()
