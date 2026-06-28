from pathlib import Path

# settings.py 位於 game_engine/backend/，往上兩層才是專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[2]

IMAGES_DIR = PROJECT_ROOT / "Images"
SPRITES_DIR = IMAGES_DIR / "Sprites"
TRACK_ASSETS_DIR = IMAGES_DIR / "TracksMapGen"
TRACKS_DIR = IMAGES_DIR / "Tracks"

MAPS_DIR = PROJECT_ROOT / "maps"
TRAIN_MAPS_DIR = MAPS_DIR / "train_maps"
VALID_MAPS_DIR = MAPS_DIR / "valid_maps"

DEFAULT_TRACK_BACK_PATH = TRACKS_DIR / "bg4.png"
DEFAULT_TRACK_FRONT_PATH = TRACKS_DIR / "bg7.png"
TRACK_BACK_PATH = TRACKS_DIR / "randomGeneratedTrackBack.png"
TRACK_FRONT_PATH = TRACKS_DIR / "randomGeneratedTrackFront.png"

SCREEN_SIZE = WIDTH, HEIGHT = 1600, 900
FPS = 30
MAX_SPEED = 10

WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
BLUE = (0, 0, 128)
BLACK = (0, 0, 0)
COLOR_LINE = (255, 0, 0)

INPUT_LAYER = 6
HIDDEN_LAYER = 6
OUTPUT_LAYER = 4
NUM_OF_NN_CARS = 50

TRAINING_DIFFICULTY_MAPS: dict[int, tuple[Path, Path]] = {
    1: (TRAIN_MAPS_DIR / "train_easy.png", TRAIN_MAPS_DIR / "train_easy_back.png"),
    2: (TRAIN_MAPS_DIR / "train_hard.png",  TRAIN_MAPS_DIR / "train_hard_back.png"),
    3: (TRACK_FRONT_PATH, TRACK_BACK_PATH),  # random, generated at runtime
}

VALIDATION_DIFFICULTY_MAPS: dict[int, tuple[Path, Path]] = {
    1: (DEFAULT_TRACK_FRONT_PATH, DEFAULT_TRACK_BACK_PATH),
    2: (DEFAULT_TRACK_FRONT_PATH, DEFAULT_TRACK_BACK_PATH),
    3: (DEFAULT_TRACK_FRONT_PATH, DEFAULT_TRACK_BACK_PATH),
}
