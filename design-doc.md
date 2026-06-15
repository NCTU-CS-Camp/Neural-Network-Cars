# Neural Network Cars 設計文件

## 一、專案目標
本專案目前是一個以 Pygame 為基礎的本地神經網路賽車訓練原型。下一階段的目標，是將其擴充為可供多組協作開發的小型平台，具備以下三項核心能力：

- 支援 Genetic Algorithm（GA）訓練策略的調整、比較與驗證。
- 提供完整的本地使用者介面，讓玩家能操作訓練流程與遊戲設定。
- 提供後端服務，讓使用者能上傳訓練成果並於大螢幕模式中播放結果。

## 二、目前專案現況
目前程式主要以本地 Pygame 執行流程為核心，主要模組如下：

- `frontend/app.py`：主遊戲迴圈、鍵盤輸入、畫面繪製、訓練流程整合。
- `backend/car.py`：車輛狀態、感測器計算、碰撞判定、神經網路輸出與動作執行。
- `backend/genetic.py`：目前的 crossover 與 mutation 實作。
- `backend/track_generator.py`：隨機地圖生成與賽道圖片輸出。
- `backend/settings.py`：畫面尺寸、神經網路層數、族群大小、資源路徑與常數設定。

目前已能完成本地訓練與隨機地圖生成，但以下能力仍未模組化：

- fitness function 與 GA 訓練策略仍與主執行流程耦合。
- 使用者介面仍以鍵盤操作為主，缺少完整 UI 流程。
- 權重格式、提交流程與 replay 播放機制尚未定義為可共享的資料契約。

## 三、目標架構
下一階段將專案整理為四個層次：

- `frontend/`：場景切換、操作元件、設定儲存、重播控制。
- `backend/`：模擬邏輯、車輛行為、GA pipeline、賽道載入、模型序列化。
- `server/`：上傳 API、排行榜 API、重播任務 API、資料儲存。
- `shared contracts`：設定檔、模型權重、重播請求、執行結果等 JSON 格式定義。

此拆分的目標，是讓 GA Team、UI Team、BE Team 可以在共享資料格式明確的前提下平行開發。

## 四、團隊分工
### 4.1 GA Team
GA Team 的目標是提升訓練效果，並建立可比較、可驗證的演化策略。

主要工作範圍：
- 將 fitness function 自 `frontend/app.py` 中抽離。
- 設計可插拔的 fitness strategy。
- 研究 selection、crossover、mutation 的組合效果。
- 建立每代訓練結果的實驗紀錄格式。

建議新增模組：
- `backend/fitness.py`
- `backend/training_session.py`
- `backend/serialization.py`

第一版建議策略：
- `baseline_distance`：以碰撞前行進距離作為基礎分數。
- `progress_speed`：以行進進度與速度作為加分，碰撞作為扣分。
- `checkpoint_progress`：以 checkpoint 通過數與前進穩定性作為分數基礎，對原地打轉或停滯施加懲罰。

預期產出：
- 可替換的 fitness function 介面。
- 可重現的訓練紀錄輸出格式。
- 可供 UI 與後端共用的穩定權重匯出格式。

### 4.2 UI Team
UI Team 的目標是將目前以鍵盤操作為主的訓練器，整理成完整、可操作的本地應用程式。

主要工作範圍：
- 建立首頁、設定頁、訓練頁、重播頁等場景。
- 提供地圖切換、暱稱輸入、訓練參數調整功能。
- 顯示目前操作說明、訓練狀態與 replay 流程。
- 支援本地權重載入、匯出與上傳入口。

建議新增模組：
- `frontend/scenes.py`
- `frontend/widgets.py`
- `frontend/config_store.py`

第一版功能重點：
- 地圖模式切換：預設地圖、隨機地圖、固定 seed 地圖。
- 玩家暱稱輸入。
- `mutation_rate`、`population_size`、`fps`、debug overlay 等設定。
- 開始訓練、切換地圖、載入 weights、匯出 weights、上傳結果等操作按鈕。

預期產出：
- 以 scene 為基礎的 UI 導覽流程。
- 可持久化的 `settings.json`。
- 本地 replay 與上傳流程的使用者入口。

### 4.3 BE Team
BE Team 的目標是建立一個可接收模型提交、儲存結果並支援大螢幕播放流程的服務。

主要工作範圍：
- 接收使用者上傳的模型權重與相關 metadata。
- 儲存 submission 與 leaderboard 資料。
- 提供重播任務資料給大螢幕 renderer。
- 提供 tracks、submissions、leaderboard 等 API。

建議新增模組：
- `server/app.py`
- `server/models.py`
- `server/storage.py`
- `server/replay_queue.py`

第一版建議 API：
- `POST /submissions`
- `GET /submissions`
- `GET /submissions/{id}`
- `GET /leaderboard`
- `POST /replays`

設計原則：
- server 不直接依賴 Pygame render。
- 大螢幕播放由本地 replay client 讀取 server replay job 後進行渲染。

預期產出：
- 可接收模型上傳的 API。
- 可查詢排行榜與 submission 的 API。
- 可供大螢幕模式使用的 replay job 資料流。

## 五、共享資料契約
### 5.1 設定檔格式
```json
{
  "nickname": "player1",
  "fps": 30,
  "population_size": 50,
  "mutation_rate": 90,
  "show_player": true,
  "show_debug_overlay": true,
  "map_mode": "random",
  "track_seed": 42
}
```

### 5.2 權重資料格式
```json
{
  "model_version": "v1",
  "layer_sizes": [6, 6, 4],
  "weights": [],
  "biases": [],
  "fitness_score": 0.0,
  "generation": 1,
  "track_id": "generated-001",
  "track_seed": 42,
  "nickname": "player1"
}
```

### 5.3 Replay Request 格式
```json
{
  "submission_id": "sub_001",
  "track_seed": 42,
  "render_mode": "big-screen"
}
```

## 六、開發里程碑
1. 重構本地 runtime：抽離 fitness logic、定義 weight schema、建立可供 replay 使用的模擬核心。
2. 建立本地 UI：加入場景切換、設定持久化、地圖切換、暱稱輸入、weights 匯入匯出。
3. 建立後端 MVP：支援 submissions、leaderboard 與 replay job。
4. 完成端到端展示流程：本地訓練 -> 匯出或上傳 weights -> 大螢幕 replay。

## 七、各團隊執行項目
### 7.1 GA Team 執行項目
#### 任務 1：抽離 fitness function 模組
- 目標：將目前訓練分數計算自主迴圈中抽離，建立可替換的 fitness 介面。
- 涉及檔案：`frontend/app.py`、`backend/fitness.py`
- 驗收標準：
  - 主訓練流程不直接寫死分數公式。
  - 可透過設定切換不同 fitness strategy。

#### 任務 2：建立 training session 模組
- 目標：整理每一代訓練所需狀態，避免 GA 邏輯散落於 UI loop。
- 涉及檔案：`backend/training_session.py`、`frontend/app.py`
- 驗收標準：
  - generation、alive count、selected cars、mutation rate 等狀態集中管理。
  - UI 可讀取訓練狀態，但不負責計算演化流程。

#### 任務 3：實作多種 fitness strategy
- 目標：至少建立 3 種可比較的 fitness function。
- 建議策略：
  - `baseline_distance`
  - `progress_speed`
  - `checkpoint_progress`
- 驗收標準：
  - 每種策略皆可獨立執行。
  - 執行結果可輸出分數與排名結果。

#### 任務 4：建立實驗紀錄格式
- 目標：輸出每代訓練結果，供後續分析與比較。
- 涉及檔案：`backend/serialization.py`、`logs/` 或 `experiments/`
- 驗收標準：
  - 至少記錄 generation、fitness、track_seed、strategy_name。
  - 同一組設定可重複執行並比較結果。

#### 任務 5：定義 weights 匯出格式
- 目標：建立可供 UI Team 與 BE Team 共用的模型序列化格式。
- 驗收標準：
  - 包含 `layer_sizes`、`weights`、`biases`、`fitness_score`、`track_seed`、`nickname`。
  - 可從記憶體中的 car model 匯出 JSON。

### 7.2 UI Team 執行項目
#### 任務 1：建立 scene-based UI 架構
- 目標：將目前單一主畫面拆成場景導覽架構。
- 涉及檔案：`frontend/scenes.py`、`frontend/app.py`
- 驗收標準：
  - 至少包含 `Home`、`Settings`、`Training`、`Replay` 四個場景。
  - 場景切換不影響既有訓練流程。

#### 任務 2：建立設定儲存機制
- 目標：將使用者設定寫入本地檔案。
- 涉及檔案：`frontend/config_store.py`、`settings.json`
- 驗收標準：
  - 可儲存 nickname、FPS、population size、mutation rate、map mode。
  - 重啟程式後可恢復設定。

#### 任務 3：製作設定頁
- 目標：提供可視化設定介面，取代純鍵盤控制。
- 驗收標準：
  - 可切換地圖模式。
  - 可輸入 nickname。
  - 可調整訓練參數與 debug 顯示選項。

#### 任務 4：製作訓練控制介面
- 目標：讓使用者透過 UI 控制訓練流程。
- 驗收標準：
  - 提供開始訓練、下一張地圖、重設、載入、匯出等按鈕。
  - 顯示 generation、alive count、selected count、目前設定值。

#### 任務 5：製作 replay 與 upload 入口
- 目標：讓使用者可以選擇本地模型進行 replay 或送往 server。
- 驗收標準：
  - 可從本地載入 weight JSON。
  - 可呼叫 upload API 傳送結果。

### 7.3 BE Team 執行項目
#### 任務 1：建立 submission API
- 目標：讓使用者可上傳模型權重與 metadata。
- 涉及檔案：`server/app.py`、`server/models.py`
- 驗收標準：
  - 提供 `POST /submissions`。
  - 驗證 payload 基本欄位是否完整。

#### 任務 2：建立 leaderboard API
- 目標：提供排行榜查詢介面。
- 驗收標準：
  - 提供 `GET /leaderboard`。
  - 至少回傳 nickname、fitness_score、track_seed、submitted_at。

#### 任務 3：建立 submission 查詢 API
- 目標：提供 submission 列表與單筆查詢。
- 驗收標準：
  - 提供 `GET /submissions` 與 `GET /submissions/{id}`。
  - 可依 nickname 或排序條件擴充。

#### 任務 4：建立 replay job API
- 目標：讓大螢幕 renderer 可取得待播放資料。
- 涉及檔案：`server/replay_queue.py`
- 驗收標準：
  - 提供 `POST /replays` 建立 replay job。
  - 可回傳 submission 對應的 track 與模型資料。

#### 任務 5：建立持久化儲存層
- 目標：將 submission、leaderboard、replay job 寫入可查詢的儲存層。
- 涉及檔案：`server/storage.py`
- 驗收標準：
  - MVP 可先使用 JSON 或 SQLite。
  - 未來可替換為正式資料庫而不影響 API 層。

### 7.4 跨團隊整合項目
#### 任務 1：定義共享 JSON schema
- 目標：統一 settings、weights、replay request 格式。
- 參與團隊：GA Team、UI Team、BE Team
- 驗收標準：
  - 文件與實作一致。
  - 各團隊皆能使用相同欄位名稱與版本號。

#### 任務 2：建立本地 replay client 規格
- 目標：定義大螢幕 renderer 與 server 的資料交換方式。
- 參與團隊：UI Team、BE Team
- 驗收標準：
  - 可用同一份 submission 資料進行本地 replay 與大螢幕 replay。

#### 任務 3：建立 demo flow
- 目標：完成從本地訓練到上傳、再到大螢幕播放的整合展示。
- 參與團隊：GA Team、UI Team、BE Team
- 驗收標準：
  - 使用者可完成訓練、匯出或上傳、提交 replay、查看結果的完整流程。

## 八、待確認問題
- leaderboard 應以最高分、平均分數，還是最快通關作為排序依據？
- 正式提交是否需要固定 track seed 以確保公平性？
- replay 結果是否需要跨機器 deterministic？
- 每位使用者最多保留多少筆 submission？
