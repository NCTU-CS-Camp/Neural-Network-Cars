from pathlib import Path

# settings.py 位於 game_engine/backend/，往上兩層才是專案根目錄
PROJECT_ROOT = Path(__file__).resolve().parents[2]

IMAGES_DIR = PROJECT_ROOT / "Images"
SPRITES_DIR = IMAGES_DIR / "Sprites"
TRACK_ASSETS_DIR = IMAGES_DIR / "TracksMapGen"
TRACKS_DIR = IMAGES_DIR / "Tracks"
OFFICIAL_TRACKS_DIR = IMAGES_DIR / "OfficialTracks"

FONT_PATH = PROJECT_ROOT / "fonts" / "GenSenRounded-R.ttc"

FONTS_DIR = PROJECT_ROOT / "fonts"
HEAD_FONT_PATH = FONTS_DIR / "ChakraPetch-Bold.ttf"
BODY_FONT_PATH = FONTS_DIR / "Rajdhani-SemiBold.ttf"
MONO_FONT_PATH = FONTS_DIR / "SpaceMono-Bold.ttf"

MAPS_DIR = PROJECT_ROOT / "maps"
TRAIN_MAPS_DIR = MAPS_DIR / "train_maps"
VALID_MAPS_DIR = MAPS_DIR / "valid_maps"

DEFAULT_TRACK_BACK_PATH = TRACKS_DIR / "bg4.png"
DEFAULT_TRACK_FRONT_PATH = TRACKS_DIR / "bg7.png"
TRACK_BACK_PATH = TRACKS_DIR / "randomGeneratedTrackBack.png"
TRACK_FRONT_PATH = TRACKS_DIR / "randomGeneratedTrackFront.png"
TRACK_METADATA_PATH = TRACKS_DIR / "randomGeneratedTrack.json"

SCREEN_SIZE = WIDTH, HEIGHT = 1600, 900
FPS = 30
MAX_SPEED = 10
TRACK_HALF_WIDTH = 66.0

# Validation run length. Kept as a config knob because the termination rule is
# expected to change later (e.g. stagnation / first-completion); for now a flat
# time limit is the only criterion implemented.
VALIDATION_TIME_LIMIT_SECONDS = 60
VALIDATION_FRAME_LIMIT = VALIDATION_TIME_LIMIT_SECONDS * FPS  # 60s @ 30fps = 1800 ticks

WHITE = (255, 255, 255)
GREEN = (0, 255, 0)
BLUE = (0, 0, 128)
BLACK = (0, 0, 0)
COLOR_LINE = (255, 0, 0)

# --- F1 Broadcast palette ---
BG       = (10, 11, 14)      # 深黑底
CARBON   = (20, 22, 28)      # 面板 / 一般按鈕
CARBON2  = (27, 30, 38)      # hover / 次層
FIELD    = (12, 14, 18)      # 輸入框底
LINE     = (42, 46, 57)      # 邊框線
INK      = (238, 241, 246)   # 主要文字
DIM      = (138, 146, 163)   # 次要文字
F1_RED   = (255, 43, 33)     # 主色 / CTA / 懲罰 / 選取高亮
CYAN     = (24, 223, 230)    # 資料 / 獎勵 / 焦點
YELLOW   = (255, 214, 10)    # 訊號
F1_GREEN = (58, 224, 110)    # 正向數值
SELECT_BG = (28, 17, 20)     # 被選中列底（帶紅調）

INPUT_LAYER = 6
HIDDEN_LAYER = 6
OUTPUT_LAYER = 4
NUM_OF_NN_CARS = 50

TRAINING_DIFFICULTY_MAPS: dict[int, tuple[Path, Path, Path]] = {
    1: (
        TRAIN_MAPS_DIR / "train_easy.png",
        TRAIN_MAPS_DIR / "train_easy_back.png",
        TRAIN_MAPS_DIR / "train_easy.json",
    ),
    2: (
        TRAIN_MAPS_DIR / "train_hard.png",
        TRAIN_MAPS_DIR / "train_hard_back.png",
        TRAIN_MAPS_DIR / "train_hard.json",
    ),
    3: (
        TRACK_FRONT_PATH,
        TRACK_BACK_PATH,
        TRACK_METADATA_PATH,
    ),  # random, generated at runtime
}

# Validation maps mirror the training hookup (front for display, back for
# collision). Scoring checkpoints come from the matching valid_{id}.json.
VALIDATION_DIFFICULTY_MAPS: dict[str, tuple[Path, Path]] = {
    "easy": (VALID_MAPS_DIR / "valid_easy.png", VALID_MAPS_DIR / "valid_easy_back.png"),
    "hard": (VALID_MAPS_DIR / "valid_hard.png", VALID_MAPS_DIR / "valid_hard_back.png"),
}

# UI text is mostly Traditional Chinese; a CJK-capable font is required or
# labels render blank. Path is OS-specific (no bundled font in the repo yet),
# so probe known install locations per platform instead of hardcoding one.
_CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",  # macOS
    "/mnt/c/Windows/Fonts/msjh.ttc",  # WSL2 -> Windows host (Traditional Chinese)
    "/mnt/c/Windows/Fonts/msyh.ttc",  # WSL2 -> Windows host (Simplified Chinese)
    "C:/Windows/Fonts/msjh.ttc",  # native Windows
    "C:/Windows/Fonts/msyh.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # common Linux CJK install
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
CJK_FONT_PATH = next((path for path in _CJK_FONT_CANDIDATES if Path(path).exists()), None)
