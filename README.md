# Neural Network Cars

Neural Network Cars 是一個以 `Python + Pygame` 為基礎的本地訓練專案，目標是透過簡單神經網路與 Genetic Algorithm（GA）訓練自走車在賽道上行駛。  
目前這個 repository 正在整理成一個可供多組平行開發的基礎架構，主要支援以下三條工作線：

- `GA Team`：負責 fitness strategy、訓練流程、實驗輸出與模型序列化。
- `UI Team`：負責 scene-based 本地 UI、設定持久化、replay 入口與操作流程。
- `BE Team`：負責 trusted-client submission API、batch leaderboard 與大螢幕 replay 服務。

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
- `server/`：FastAPI trusted-client submission、leaderboard、batch 與 replay 服務。

### 主要模組

- `game_engine/frontend/app.py`：本地 simulator 的主要入口，負責串接設定、scene、training session 與 render loop。
- `game_engine/frontend/scenes.py`：`home`、`settings`、`training`、`replay` 四個場景的基礎殼層。
- `game_engine/frontend/config_store.py`：讀寫本機的 `settings.json`。
- `game_engine/frontend/widgets.py`：提供基礎 UI 元件骨架。
- `game_engine/backend/car.py`：車輛狀態、感測器、碰撞判定與神經網路輸出動作。
- `GA/genetic.py`：mutation 與 crossover 的既有實作。
- `GA/fitness.py`：可替換的 fitness strategy 入口。
- `game_engine/backend/training_session.py`：管理 generation、selected cars、mutation rate、alive count 等訓練狀態。
- `game_engine/backend/serialization.py`：新版 submission weights/biases 的匯出與載入。
- `game_engine/backend/track_generator.py`：隨機賽道生成與輸出。
- `game_engine/backend/official_track_generator.py`：產生官方競賽地圖與 checkpoint metadata。
- `shared/contracts.py`：`RuntimeSettings`、`WeightPayload`、`SubmissionPayload`、`ReplayRequest` 等共享 schema。
- `server/app.py`：提供新版 submission、leaderboard、replay、admin 與 WebSocket API。

## Repository 結構

```text
game_engine/frontend/   本地遊戲 UI、scenes、settings、replay 殼層
game_engine/backend/    模擬邏輯、training session、serialization、assets
GA/          genetic operators 與 fitness strategy
shared/     共用資料契約
server/     submission 與 replay 服務
Images/     車輛 sprite 與賽道生成素材
Images/Tracks/  預設賽道，以及執行期產生且不納入版控的隨機賽道
Images/OfficialTracks/  官方競賽地圖與 checkpoint metadata
docs/       專案設計與協作文件
settings.json  本地執行設定（不納入版控）
```

## 啟動方式

### 啟動本地 simulator

```bash
uv run python main.py
```

此指令會從 `game_engine/frontend/app.py` 啟動 Pygame simulator。
訓練時按 `U` 可將目前最佳車的 weights 提交到 server。

Client 使用的 API 位址由專案根目錄的 `.env` 設定：

```dotenv
COMPETITION_SERVER_URL=http://127.0.0.1:8000
```

請先複製 `.env.example` 為 `.env`，再依本機環境修改 IP、protocol 與 port。`.env`、`settings.json`、`profile.json`、`records.json` 與隨機賽道輸出皆為本機執行期資料，不納入版本控制。登入畫面不允許使用者修改此位址；若作業系統環境變數中也有 `COMPETITION_SERVER_URL`，環境變數優先。

`main.py` 保留為訓練用 simulator。競賽提交請使用符合 v2 `client_result` 契約的
competition client；repository 內提供 `competition_main.py` 作為人工訓練與測試提交入口。

### 啟動 competition server

```bash
uv run python server/app.py
```

此指令會在 `http://127.0.0.1:8000` 啟動本地 server。排行榜頁面位於 `http://127.0.0.1:8000/leaderboard`，助教管理頁面位於 `http://127.0.0.1:8000/admin`。預設 admin token 是 `admin`，正式活動可用 `COMPETITION_ADMIN_TOKEN` 環境變數覆蓋。

若要讓同 subnet 的學生電腦連進來，請改用：

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

### 產生 mock submissions

```bash
uv run python -m server.mock_data --count 10 --state completed --reset
```

此指令會直接寫入 competition SQLite 資料，建立 deterministic trusted-client submissions。
`--state queued` 可測試 UTC batch，`--state completed` 可立即建立 demo snapshot。

### 啟動大螢幕 replay

```bash
uv run python replay.py
```

此指令會開啟 Pygame replay client。Phase 1 會同步播放 Easy/Hard 的各自 Top 15，Final
會切換為單一 group competition 畫面。它需要 `COMPETITION_REPLAY_TOKEN`，預設值是本地
admin token `admin`。

### 啟動 competition test main

```bash
uv run python competition_main.py
```

此測試 client 可在 Easy、Hard、Final competition maps 上訓練新 weights，手動輸入
User ID、Group ID 與 admin 建立的 temporary password，產生或覆寫 test-only
`client_result`，並用 v2 authenticated APIs 提交。

## Competition 操作流程

以下四個入口使用同一個 competition server，統一使用
`http://127.0.0.1:8000`。啟動 Pygame client 前可明確設定：

```bash
export COMPETITION_SERVER_URL=http://127.0.0.1:8000
```

### 1. Admin：設定賽程與建立 snapshot

開啟 `http://127.0.0.1:8000/admin`，輸入 admin token。開發環境預設為 `admin`。後台內容會在 token 驗證成功後才顯示。

1. 將 stage 設為 `phase_one`，開放個人 Easy 與 Hard submission。
2. 將 stage 設為 `final`，關閉 Easy/Hard，開放 Final submissions；Final cooldown 以 `(group_id, username)` 個人為單位，但排行榜以小組最佳代表上榜。
3. `Snapshot interval` 可設定 snapshot 與 cooldown 間隔，目前支援 1、2、5 分鐘，預設 1 分鐘。
4. `User Management` 可建立/更新使用者 temporary password、批次匯入帳號、enable/disable 帳號；測試帳號可從 `docs/test-users.csv` 匯入。
5. `Run Snapshot Now` 會立即封存目前 queued submissions，方便測試；正式比賽則由目前 interval 的 UTC 邊界自動封存。
6. `Restart Replay` 會通知大螢幕 Pygame client 立即從 spawn 重新播放目前 Top 15，不改變排行榜或 snapshot。
7. `Submissions` 區可 soft-delete 單筆 submission；刪除後會從 leaderboard/replay/cooldown 中排除並重新排名。
8. `Reset Competition Data` 會刪除所有 submissions、cooldown 與 snapshots，但保留目前 stage、competition interval 與 admin 建立的使用者帳號。

Admin 頁也會固定顯示 Easy、Hard、Final 三張 competition map 預覽。這三張 map 不能在 admin 頁任意替換。

### 2. Competition Test Main：訓練並模擬不同玩家提交

```bash
COMPETITION_SERVER_URL=http://127.0.0.1:8000 uv run python competition_main.py
```

Competition test main 的操作：

- 直接在右側表單輸入 `User ID`、`Group ID`、Password、Skin ID、Max Speed、server URL 與選用 admin token。
- `I`：用目前 User ID / Group ID / Password 登入 server；`U` 提交前也會在尚未登入時自動嘗試登入。
- `E`、`H`、`F`：切換 Easy、Hard、Final competition map；切圖會保留目前 weights。
- 左鍵選兩台車、`B` 手動 breed；或按 `G` 自動挑目前分數最高的兩台車 breed。
- `V`：用目前 best car 在選定 competition map 上跑一次，產生 test-only `client_result`。
- `O`：切換 manual result override，可手動輸入 completed、lap ticks、max progress 與 ticks。
- `U`：先呼叫 eligibility API；可提交時才送出目前 best car weights、`client_result`、`skin_id` 與 `max_speed`。
- `P`：用 admin token 呼叫 `Run Snapshot Now`，讓 queued submissions 立即進 leaderboard/replay。

Easy/Hard 對同一 `(group_id, username)` 各自有一段 cooldown，長度由 Admin 的 `Snapshot interval` 決定。Final 必須先由 admin 切到 `final` stage，cooldown 同樣以 `(group_id, username)` 為單位，但 leaderboard 只保留每個 group 的歷史最佳 non-deleted submission。

### 3. Leaderboard：公開查看排名

開啟 `http://127.0.0.1:8000/leaderboard`，使用 Easy、Hard、Final tabs 切換排行榜。

- Easy/Hard：每個 `(group_id, username)` 只保留歷史最佳 completed submission。
- Final：每個 `group_id` 只顯示小組最佳 model；username 顯示實際代表提交者。
- 完成模型依圈速排序；未完成模型依最大 progress、到達該 progress 的 tick 排序。
- queued submission 會在下一個 snapshot 後才進入排行榜。
- Public leaderboard 不需登入；登入後頁面底部 sticky bar 會顯示目前 tab 的個人成績、next submission time 與 submission history；Final tab 會顯示小組代表成績、代表提交者與自己的最新提交。
- Group 顯示統一使用 `Group 8` 這種格式。

公開頁面不會暴露任何人的 weights 或 biases。

### 4. Replay：大螢幕模式

```bash
COMPETITION_SERVER_URL=http://127.0.0.1:8000 \
COMPETITION_REPLAY_TOKEN=admin \
uv run python replay.py
```

Replay 需要 admin/replay token，因為它會讀取模型參數來播放車輛。Phase 1 同時呈現 Easy 與 Hard 各自的排行榜 Top 15；Final 會自動改為單一賽道與 group leaderboard。每一輪動畫結束才重新抓取資料，因此 snapshot 更新不會中斷正在播放的車輛。車輛完成第一圈、撞牆，或連續 180 ticks 未離開最後有效位置 24px 時會停止並變暗；所有車輛完成、撞毀或停滯後，replay 會暫停 3 秒再抓取目前 replay payload，若沒有新 snapshot 則重播同一批資料。Replay header 會顯示目前狀態、本輪 elapsed time、下一輪 replay 倒數與下一次 snapshot 倒數。

Replay 目前採 safe-reveal 流程：新 snapshot 或 stage change 抵達時不會中斷目前畫面，而是在本輪 replay 結束後才採用。第一次播放新 leaderboard 時會先隱藏排行榜，等該 Easy/Hard/Final session 結束後再揭示；同一批 snapshot 的後續 replay 會直接顯示排行榜。

Replay 會使用 submission metadata 呈現車子：`skin_id=0` 是白車、`skin_id=1` 是綠車，`max_speed` 會套用到 replay 車速上限。車名使用非灰色排行色；車輛 finished/crashed/stalled 後車體與名字會變暗。下一個 snapshot 剩 5 秒內，active map panel 會覆蓋半透明 F1 start-light 風格倒數燈號；若倒數到 0 時 replay 還在跑，會先用目前排名從 spawn 重新播放，並顯示「等待新快照，先重播目前排名」，新快照仍會等安全邊界才揭榜。

若教室電腦的 Pygame 無法正確顯示中文狀態文字，可以指定 CJK 字型：

```bash
COMPETITION_REPLAY_FONT_PATH=/path/to/NotoSansCJK-Regular.ttc uv run python replay.py
```

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
若要在學校電腦教室部署 competition server，請參考
[docs/classroom-deployment.md](docs/classroom-deployment.md)。
