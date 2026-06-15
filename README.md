# Neural Network Cars

Neural Network Cars 是一個以 `Python + Pygame` 為基礎的本地訓練專案，目標是透過簡單神經網路與 Genetic Algorithm（GA）訓練自走車在賽道上行駛。  
目前這個 repository 正在整理成一個可供多組平行開發的基礎架構，主要支援以下三條工作線：

- `GA Team`：負責 fitness strategy、訓練流程、實驗輸出與模型序列化。
- `UI Team`：負責 scene-based 本地 UI、設定持久化、replay 入口與操作流程。
- `BE Team`：負責 submission API、leaderboard API，以及大螢幕 replay job 服務。

## 環境安裝

### 已安裝 `uv`

```bash
git clone https://github.com/NCTU-CS-Camp/Neural-Network-Cars.git
cd Neural-Network-Cars
uv python install 3.12
uv sync
uv run python main.py
```

### 尚未安裝 `uv`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

git clone https://github.com/NCTU-CS-Camp/Neural-Network-Cars.git
cd Neural-Network-Cars
uv python install 3.12
uv sync
uv run python main.py
```

## 目前程式架構

目前專案分成四個主要層次：

- `game_engine/frontend/`：Pygame app shell、場景切換、UI 元件與本地設定讀寫。
- `game_engine/backend/`：車輛模擬、訓練 session、序列化與地圖生成。
- `GA/`：genetic operators 與可替換的 fitness strategy。
- `shared/`：前端、後端與 server 共用的資料格式定義。
- `server/`：submission、leaderboard 與 replay job 的輕量 HTTP 服務。

### 主要模組

- `game_engine/frontend/app.py`：本地 simulator 的主要入口，負責串接設定、scene、training session 與 render loop。
- `game_engine/frontend/scenes.py`：`home`、`settings`、`training`、`replay` 四個場景的基礎殼層。
- `game_engine/frontend/config_store.py`：讀寫 `settings.json`。
- `game_engine/frontend/widgets.py`：提供基礎 UI 元件骨架。
- `game_engine/backend/car.py`：車輛狀態、感測器、碰撞判定與神經網路輸出動作。
- `GA/genetic.py`：mutation 與 crossover 的既有實作。
- `GA/fitness.py`：可替換的 fitness strategy 入口。
- `game_engine/backend/training_session.py`：管理 generation、selected cars、mutation rate、alive count 等訓練狀態。
- `game_engine/backend/serialization.py`：訓練後模型 weights 的匯出與載入。
- `game_engine/backend/track_generator.py`：隨機賽道生成與輸出。
- `shared/contracts.py`：`RuntimeSettings`、`WeightPayload`、`ReplayRequest` 等共享 schema。
- `server/app.py`：提供 `/health`、`/submissions`、`/leaderboard`、`/replays` API。

## Repository 結構

```text
game_engine/frontend/   本地遊戲 UI、scenes、settings、replay 殼層
game_engine/backend/    模擬邏輯、training session、serialization、assets
GA/          genetic operators 與 fitness strategy
shared/     共用資料契約
server/     submission 與 replay 服務
Images/     車輛 sprite 與賽道生成素材
Images/Tracks/  預設賽道與隨機產生賽道圖片
docs/       專案設計與協作文件
settings.json  本地執行設定
```

## 啟動方式

### 啟動本地 simulator

```bash
uv run python main.py
```

此指令會從 `game_engine/frontend/app.py` 啟動 Pygame simulator。

### 啟動 server stub

```bash
uv run python server/app.py
```

此指令會在 `http://127.0.0.1:8000` 啟動本地 server，提供 submission、leaderboard 與 replay job 的基本 API。

## 開發指令

```bash
uv sync
uv run pytest
uv run ruff check .
uv run mypy game_engine GA server shared
```

## 三個 Team 的起點

- `GA Team`：建議從 `GA/fitness.py`、`GA/genetic.py`、`game_engine/backend/training_session.py`、`game_engine/backend/serialization.py` 開始。
- `UI Team`：建議從 `game_engine/frontend/scenes.py`、`game_engine/frontend/widgets.py`、`game_engine/frontend/config_store.py`、`game_engine/frontend/app.py` 開始。
- `BE Team`：建議從 `server/app.py`、`server/models.py`、`server/storage.py`、`shared/contracts.py` 開始。

若要看較完整的規劃，請參考 [docs/design-doc.md](docs/design-doc.md)。
