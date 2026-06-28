# BeginnerMix Fitness 串接提案

狀態：已依 2026-06-28 的回覆完成實作與驗證。

依據：`/Users/harryp/Downloads/fitness-calculation.md` 描述的十項 BeginnerMix
分數與目前 repository 內的 `GA/fitness.py`、`game_engine/` 執行流程。

## 已確認的產品決策

- 計分語意要 1:1 符合 `fitness-calculation.md`，包含文件列出的現行特性與限制；
  這一輪不順便修正公式。
- 不實作完整自動化 GA orchestration、多張 training map 平均、時間上限或 validation
  的 competition ranking。保留現有 Pygame 訓練操作，重點是逐幀算出十項 fitness，
  並用累積分數自動找出目前 population 中表現最好的車。
- 賽道 `half_width` 採 `66 px`。依據見「half_width 調查結果」。
- 停止支援舊版 fitness records：不做 placeholder key migration，也不保留 legacy scorer；
  舊 key 會明確拋出不相容錯誤，不可靜默套用新公式。
- 按 `B` breed 時，自動選 accumulated fitness 最高的兩台車當 parents，取代原本
  必須先用滑鼠指定兩台車的限制。

## 目標

讓 `game_engine` 在每一個 simulation frame 產生完整且定義清楚的賽車狀態，
使 `GA/fitness.py` 可以計算以下十項分數：

- Reward：`speed`、`progress`、`centered`、`alignment`、`safety`
- Penalty：`stall`、`spin`、`wrong_way`、`time`、`crash`
- 額外事件：內建進度比例獎勵與首次完賽獎勵

本提案不改變上述公式，也不擴張成另一套自動訓練系統。

## 現況結論

目前 `GA/fitness.py` 只在讀取車輛當下的 `score`、`velocity`、`collided` 和部分
感測器距離，且主要是在碰撞時才取一次 fitness。這不足以重現文件中的公式，因為
該公式需要逐幀狀態、賽道中心線、前一幀狀態、累積進度、episode 時間與一次性事件。

目前 UI 中的十個 slider 也只是另一組 placeholder 名稱；除了部分名稱語意相近外，
它們沒有對應到文件中的十個 BeginnerMix 項目。現有 `score_with_config()` 會把每個
slider key 當成 strategy 名稱；找不到時會 fallback 到 `baseline_distance`，因此目前
十個權重實際上不是十種獨立 reward／penalty。

## 每個計分項目缺少的 game_engine 資料

| 項目 | 目前可用資料 | 必須補上的 engine 資料或行為 |
| --- | --- | --- |
| `speed` | `Car.velocity` | 產生「本幀更新後」的速度 snapshot，並固定 scoring 發生順序 |
| `progress` | 無中心線進度 | ordered centerline、track length、上一幀投影、本幀 delta、跨起終點修正、累積正向進度 |
| `centered` | 無 | 車輛中心到最近中心線的距離與 map metadata 中的 `half_width = 66` |
| `alignment` | `Car.angle` | 最近中心線 segment 的行進方向、heading delta、alignment cosine |
| `safety` | `d1`～`d5` | 確認並統一感測器算法；現況用 PNG alpha 且每次前進 10 px，文件則是中心線範圍且每次 4 px |
| `stall` | `Car.velocity` | 本幀 `velocity < 0.5` 的明確旗標 |
| `spin` | 無前幀角度 | previous angle、本幀轉角差與本幀 progress delta |
| `wrong_way` | 無賽道方向 | 由 heading alignment 產生的旗標 |
| `time` | global `frames` | 每個 episode 的 frame index、fps 與 elapsed seconds |
| `crash` | `collision()`、`collided` | 碰撞必須先進入本幀 snapshot，再計分一次，最後才結束該車 episode |
| 內建進度獎勵 | 無 | `cumulative_progress / track_length` 的 ratio |
| 完賽獎勵 | 無 | 首次跨過一圈門檻的 one-shot `finished_now` 事件 |

## 建議的資料流

```text
Track metadata / centerline
             │
NN output → action → Car physics → track projection / collision / sensors
                                      │
                                      ▼
                               FrameTelemetry
                                      │
                                      ▼
                         GA/fitness.py 計算 step_fitness
                                      │
                                      ▼
                         EpisodeState.training_fitness 累加
```

`GA/fitness.py` 應接收明確的 `FrameTelemetry`，不再用 `getattr(car, ...)` 猜測欄位；
神經網路權重與車輛物理狀態則繼續由 `Car` 負責。

## 預計修改的 game_engine 範圍

### 1. 新增賽道幾何模型

新增 `game_engine/backend/track.py`，負責：

- 從 map JSON 載入 grid、start、finish 與 tile 資訊。
- 根據 tile 連通方向建立「依行駛順序排列」的中心點，而不是沿用 JSON 的 row-major
  `tiles` 順序。
- 建立 closed centerline segments、各段長度、累積長度與總長度。
- 提供最近線段投影，回傳 `progress`、`center_offset`、segment index 與 target heading。
- 提供 `contains(point)`，讓感測與碰撞能使用同一套賽道邊界定義。
- 明確驗證中心線為單一封閉迴路；資料不合法時直接報錯，不靜默猜測順序。

固定 easy／hard map 已有 JSON，但 `settings.py` 目前只把前景與碰撞 PNG 傳給 runtime，
因此 map descriptor 加入 JSON metadata path。固定地圖使用已驗證的
`TRACK_HALF_WIDTH = 66`；隨機地圖 metadata 會明確寫出 `half_width_px: 66`。

### half_width 調查結果

已檢查 `Images/TracksMapGen/` 的 collision tiles 與 `maps/*/*_back.png`：

- `Straight1.png` 與 `Straight2.png` 都是 146 × 146 px。
- 非黑色、會保留在 collision map 的道路截面寬度固定為 132 px。
- 道路位於 local pixel `[7, 139)`，以 tile center 73 px 計算，連續幾何半寬為 66 px。
- train、valid、kaggle 的所有固定地圖，在抽查每個直線 tile 的 alpha 截面時都得到
  相同的 132 px 寬度。
- 隨機地圖使用同一組 146 px collision tiles，所以應由 generator 寫出相同的 66 px，
  不需要另一套推導規則。

因此既有 assets 足以定義 `half_width`。實作將已驗證的 66 px 固化為 engine constant，
並寫入隨機地圖 schema；圖片掃描只作為 asset consistency check，不作 runtime source
of truth。

### 2. 讓隨機地圖保留可計分的 route metadata

修改 `game_engine/backend/track_generator.py`：

- 在 maze 生成時保留 ordered route cells，不只輸出兩張 PNG。
- 回傳或輸出與固定 map 相同 schema 的 track metadata，包括 `half_width_px: 66`。
- 讓 `app.py` 換隨機地圖時同步替換 collision surface 與 `TrackGeometry`。
- 對 generated route 執行 closed-loop、相鄰 cell 和長度驗證。

如果隨機地圖沒有 ordered route，`progress`、`alignment`、`finish` 三類狀態無法可靠
計算；只從 PNG 反推中心線會引入另一套不符合文件的語意，因此不列為首選方案。

### 3. 把每車每局狀態從 Car 本體分離

新增 `game_engine/backend/simulator.py`（或同等職責的模組），定義：

- `FrameTelemetry`：本幀計分所需的不可變 snapshot。
- `EpisodeState`：previous angle、last projected progress、cumulative progress、
  accumulated fitness、frame count、finished flag、collided flag。
- `Simulator.step(...)`：固定執行 NN、action、physics、projection、sensor、collision、
  telemetry、fitness accumulation 的順序。
- `reset_episode(...)`：換圖、重設、breed 或 validation 時完整清除 per-episode 狀態。

採用獨立 `EpisodeState` 的原因是 `Car` 同時也是 GA genotype 容器；若把時間、賽道投影、
一次性完賽事件全部動態塞進 `Car`，breed、reset 與 replay 較容易留下上一局資料。

### 4. 收斂 Car 的物理與感測介面

修改 `game_engine/backend/car.py`：

- 將「移動」與「更新 sensors／corners」拆成可由 simulator 按順序呼叫的步驟。
- 移除 `self.score += self.velocity` 與 legacy scorer；需要輸出分數的地方一律改讀
  `EpisodeState.training_fitness`。
- collision 與 sensor 查詢改為接收 track geometry，避免依賴 module-level global surface。
- reset 時只重設車輛物理／NN runtime，episode 計分狀態由 simulator 一起重設。
- 加入 surface 邊界保護，避免感測線或車角超出圖片時由 `get_at()` 直接丟例外。

文件的感測與碰撞邊界都是 `distance-to-centerline <= half_width`；依已確認的 1:1
語意，PNG alpha 只保留作 render asset，不再作這兩項規則的真實來源。

### 5. 修改訓練主迴圈

修改 `game_engine/frontend/app.py`：

- 載入目前 map 對應的 `TrackGeometry`。
- 每幀透過 simulator 更新每一台未結束的車並累加 step fitness。
- 碰撞當幀先套用 crash penalty，再將該車標記為結束。
- 正確處理首次完賽事件，防止每幀重複加 finish bonus。
- reset、breed、next track 和 random map 全部同步重建 episode state。
- 自動最佳車選擇、存檔與畫面顯示統一讀取 accumulated training fitness，不再混用 legacy
  `score`、碰撞時計算的 `fitness_score` 和存檔時重新計算的另一份分數。
- 使用 `settings.fps` 產生 elapsed time；不以 wall-clock rendering delay 代替 frame time。

這會同時修正目前「實際訓練畫面用 `fitness_strategy`，存最佳車卻用另一套
`fitness_config`」的雙重計分路徑。

### 6. 更新十個 slider 名稱

修改 `game_engine/frontend/screens.py` 的 training config：

- Slider 名稱改成文件中的十個 BeginnerMix 名稱，reward 與 penalty 分組顯示。
- 依使用者指定，本次不擴張或重構 validation ranking 流程。

### 7. Settings 與 map descriptor

修改 `game_engine/backend/settings.py`：

- 將 map 設定由 `(front_png, back_png)` 擴充成帶有 `metadata_json` 的 descriptor。
- 固定地圖使用 `TRACK_HALF_WIDTH = 66`；generated metadata 同步輸出此值。
- scoring multiplier、bonus 等公式常數仍放在 `GA/fitness.py`，不塞進 engine settings。

## 必要但不在 game_engine 內的配套修改

### `GA/fitness.py`

- 實作單一 BeginnerMix step scorer，逐項回傳 reward／penalty breakdown 與總分。
- Reward 權重 clamp 到 0～100；penalty 權重只限制不得小於 0、不設 100 上限，
  再套用文件中的 multiplier。
- crash 與 finish 由 telemetry 的 one-shot event 控制。
- 保留 breakdown 供 debug UI 與單元測試驗證。
- 移除 unknown strategy 靜默 fallback；未知 key 應直接報錯。

### `FitnessConfig` 與既有 records

- 保留 `FitnessConfig.weights` 的 flat 結構，但 canonical keys 只接受十個新名稱。
- 不做既有 `records.json` migration；遇到舊 placeholder keys 時拋出 `ValueError`，
  而不是 fallback 到 `baseline_distance`。

### Tests

新增 `tests/`，至少涵蓋：

- 中心線 route ordering、projection、center offset 與 target heading。
- 正向／反向跨起終點時的 progress delta。
- sensor normalization、stall、spin、wrong-way、time、crash 和 finish one-shot。
- 文件第 13 節的完整數值範例，預期 `22.2298`、`-677.7702`、`10022.2298`。
- reset／換圖／breed 後不殘留 episode state。

## 已完成的實作順序

1. 確認 `B` breed 自動選 accumulated fitness 最高的兩台車。
2. 建立 `TrackGeometry`、固定地圖 metadata path、隨機地圖 metadata 與幾何測試。
3. 建立 `FrameTelemetry`、`EpisodeState` 與 deterministic simulator step。
4. 調整 `Car`，使物理、感測、碰撞可被 simulator 明確排序。
5. 在 `GA/fitness.py` 1:1 實作 BeginnerMix 與 breakdown 測試。
6. 串接目前的 training、random map 和 slider config；不新增自動 GA 流程。
7. 執行 `pytest`、`ruff`、`mypy`，再用 simulator 手動驗證畫面與一圈完賽事件。

## 驗收標準

- 每個 BeginnerMix 項目都能從 `FrameTelemetry` 找到唯一、可測試的資料來源。
- 同一 frame 不會重複計 crash 或 finish；整局分數是所有 step fitness 的總和。
- 固定 map 與隨機 map 都有合法 ordered centerline。
- 文件的完整數值範例通過自動測試。
- 不再以 unknown key fallback、碰撞時才算一次或存檔時臨時重算的方式產生 fitness。
- 舊 placeholder fitness key 會被明確拒絕，不會產生看似有效但公式錯誤的分數。
- 不加入自動 generation、跨 training map 平均或 competition ranking。

## 驗證結果

- `pytest`: 12 passed
- `ruff check .`: passed
- `mypy game_engine GA server shared`: passed
- 實際 `Car + TrackGeometry + Simulator` 逐幀整合執行：passed
- seed 8 隨機地圖 metadata 生成與重新載入：42 segments、6132 px、half-width 66 px
