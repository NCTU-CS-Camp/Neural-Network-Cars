# Fitness 參數調整功能設計文件

## 1. 文件目的

本文件定義 Neural Network Cars 的 Fitness 參數調整功能，計分語意以
[`fitness-calculation.md`](fitness-calculation.md) 為基準。

目標不只是把更多滑桿畫到畫面上，而是確保：

- UI 調整的值真的會進入逐幀 fitness 計算。
- Training、選父母、儲存紀錄與 Validation 使用同一份設定。
- 使用者只能調整十個行為權重。
- 底層公式常數、判定門檻與模擬參數全部由版本化 profile 固定。
- 舊版訓練紀錄仍可讀取與 Validation。
- 每份模型都保存完整參數快照，可以重現當時的分數。
- gangexp 可通過賽道的模型能在前端以相同模擬規則重現。

本文件是實作前設計，不包含程式修改。

## 2. 已驗證的目前狀態

目前 `feat/engine` 分支和計算文件之間存在實作落差。

### 2.1 現有 UI

`game_engine/frontend/screens.py` 的 Training 設定畫面會讀取
`GA.fitness.FITNESS_STRATEGIES`，目前實際只有三個滑桿：

- `baseline_distance`
- `progress_speed`
- `checkpoint_progress`

這三個滑桿不是 `fitness-calculation.md` 定義的十個 BeginnerMix 參數。

現有 `Slider`：

- 只支援整數。
- 固定範圍 0～100。
- 沒有 step、精度、鍵盤輸入、說明文字、重設或捲動功能。
- 固定用 `index * 60` 排版，控制項增加後會和地圖難度區重疊。

### 2.2 現有 Fitness

`GA/fitness.py` 現在是以車輛最終狀態計分：

```text
baseline_distance = car.score
progress_speed = car.score + velocity × 5 - collision × 25
checkpoint_progress = car.score + sensor_balance - stall × 50
```

`score_with_config()` 再將三種 strategy 的結果乘上滑桿值後相加。

目前沒有：

- `StepContext`
- 逐幀 fitness 累加
- 賽道中心線投影
- `progress_delta`
- `progress_ratio`
- `center_offset`
- `heading_alignment`
- `is_spinning`
- `wrong_way`
- finish bonus

### 2.3 現有 Training 串接問題

Training loop 在車輛碰撞時，使用 `RuntimeSettings.fitness_strategy` 計算一次
`fitness_score`。Training 設定畫面的 `FitnessConfig` 則主要用在離開 Training
後挑選要儲存的車，以及之後的 Validation。

因此目前畫面上的滑桿不會完整控制 Training 過程中的實際計分。

### 2.4 現有地圖資料

`maps/*_maps/*.json` 已包含：

- grid 尺寸與 offset
- start/finish cell
- tile 種類
- closed-circuit metadata

但 `game_engine/backend/settings.py` 的 difficulty map pool 目前只提供 front/back PNG，
沒有將 JSON metadata 傳入 Training loop。因此 runtime 尚無法依地圖中心線計算
進度與方向。

### 2.5 結論

此功能不是單純的 UI 擴充。完整實作需要同時修改：

```text
地圖幾何
   ↓
逐幀 StepContext
   ↓
BeginnerMix 計分器
   ↓
Training / Validation 共用 evaluator
   ↓
設定資料契約與紀錄
   ↓
參數調整 UI
```

## 3. 功能範圍

### 3.1 本次應實作

1. 十個 BeginnerMix 基本權重。
2. 單一十參數設定頁，不提供 Advanced 分頁。
3. 每個欄位的數值顯示、說明與重設。
4. 參數設定驗證。
5. 設定隨 TrainingRecord 儲存。
6. Training 與 Validation 使用相同計分設定。
7. 舊版 `FitnessConfig` 與 TrainingRecord 相容。
8. 逐幀 fitness 分解資料，供 debug UI 顯示。
9. gangexp model bundle 匯入與相容 replay。
10. gangexp／前端 golden-trace 一致性測試。

### 3.2 本次不應開放調整

以下項目會改變物理、神經網路輸入或比賽公平性，不屬於 fitness editor：

- `fps`
- `population_size`
- `mutation_rate`
- neural network layer sizes
- 車輛寬高
- 最大速度
- 加速度與摩擦係數
- 感測器角度數量
- 地圖道路寬度
- Training 時間上限

這些項目應留在 Runtime／Experiment Settings，而不是混入 FitnessConfig。

以下 `fitness-calculation.md` 中的公式參數也禁止使用者調整：

- 五個 `REWARD_MAX_EFFECT`
- `PROGRESS_RATIO_BONUS`
- `B`
- `TIME_PENALTY_MAX_SCALE`
- `B_CRASH`
- `FINISH_BONUS`
- safety normalization distance
- stall speed threshold
- spin angle／progress threshold
- wrong-way angle threshold

它們必須寫死在版本化的 `FitnessProfile`，UI 不顯示輸入控制項，匯入配方也不能
覆寫。

### 3.3 不在本次偷偷修正的演算法

`fitness-calculation.md` 已指出 positive-only progress 可以被來回行駛重複累積。
為避免同一次功能同時改 UI、資料契約和 fitness 語意，本次第一階段應保持文件描述
的行為。

若要改成 checkpoint sequence 或 net progress，應另立 `algorithm_version`
並做獨立實驗，不應在沒有版本標記的情況下改變舊模型分數。

## 4. 使用者體驗設計

### 4.1 畫面結構

Training 設定畫面分成：

```text
┌──────────────────────────────────────────────────────────────┐
│ Training 設定                                                │
├────────────────────────────┬─────────────────────────────────┤
│ 十個 Fitness 權重          │ 目前設定摘要                    │
│                            │                                 │
│ 可捲動參數列表             │ Preset: Default BeginnerMix     │
│                            │ Reward 參考值                    │
│ Slider + Numeric Input     │ Penalty 參考值                   │
│ 說明 / 單位 / 預設值       │ 警告與驗證錯誤                  │
│                            │                                 │
├────────────────────────────┴─────────────────────────────────┤
│ [全部重設] [套用 Preset]             難度 [*][**][***] [Go] │
└──────────────────────────────────────────────────────────────┘
```

參數列表必須可捲動，不能再使用固定 `index * 60` 直接堆疊到畫面下方。

### 4.2 十個可調參數

畫面只顯示以下十個使用者可調整的行為權重。

Reward：

| Key | 顯示名稱 | 範圍 | Step | 預設 |
| --- | --- | ---: | ---: | ---: |
| `speed` | 速度獎勵 | 0～100 | 1 | 50 |
| `progress` | 前進獎勵 | 0～100 | 1 | 50 |
| `centered` | 中心線獎勵 | 0～100 | 1 | 50 |
| `alignment` | 方向對齊獎勵 | 0～100 | 1 | 50 |
| `safety` | 安全距離獎勵 | 0～100 | 1 | 50 |

Penalty：

| Key | 顯示名稱 | 範圍 | Step | 預設 |
| --- | --- | ---: | ---: | ---: |
| `stall` | 停滯懲罰 | 0～100 | 1 | 50 |
| `spin` | 原地旋轉懲罰 | 0～100 | 1 | 50 |
| `wrong_way` | 逆向懲罰 | 0～100 | 1 | 50 |
| `time` | 時間懲罰 | 0～100 | 1 | 50 |
| `crash` | 碰撞懲罰 | 0～100 | 1 | 50 |

預設值是否全部使用 50，最終應由產品配方決定。資料契約不能把 UI 預設散落在
多個檔案中，必須由單一 registry 提供。

### 4.3 固定公式參數

以下參數是 `beginner-mix-v1` 的固定規格，不提供滑桿、數字輸入、preset override
或 config override。

#### Reward Effect

| Key | 對應公式 | 固定值 |
| --- | --- | ---: |
| `speed_effect` | speed reward 最大倍率 | 1.0 |
| `progress_effect` | progress reward 最大倍率 | 10.0 |
| `centered_effect` | centered reward 最大倍率 | 2.0 |
| `alignment_effect` | alignment reward 最大倍率 | 3.0 |
| `safety_effect` | safety reward 最大倍率 | 3.0 |
| `progress_ratio_bonus` | 固定圈進度 bonus | 0.5 |

#### Penalty／Terminal Effect

| Key | 對應公式 | 固定值 |
| --- | --- | ---: |
| `behavior_penalty_scale` | stall/spin/wrong-way 的 `B` | 10.0 |
| `time_penalty_scale` | time penalty 最大倍率 | 0.1 |
| `crash_penalty_scale` | crash 的 `B_CRASH` | 1000 |
| `finish_bonus` | 首次完賽 bonus | 10000 |

#### Detection Threshold

| Key | 對應判斷 | 固定值 |
| --- | --- | ---: |
| `safety_clearance_reference` | `min_clearance / reference` | 90 px |
| `stall_speed_threshold` | `velocity < threshold` | 0.5 |
| `spin_angle_threshold` | 每幀最小旋轉角度 | 5° |
| `spin_progress_threshold` | spin 判斷的最大前進量 | 0.1 px |
| `wrong_way_angle_threshold` | 逆向判斷角度 | 90° |

唯一可調整的數值仍然只有十個 reward／penalty 權重。若未來需要修改上述固定值，
必須建立新的 `algorithm_version`，例如 `beginner-mix-v2`，不能沿用 v1 名稱。

### 4.4 Slider 與數字輸入

每個參數列包含：

```text
名稱 | Slider | 數字輸入 | 單位 | Reset | 說明
```

互動規則：

- 拖曳 slider 時即時更新數值。
- Reset 只重設該參數。
- 超出範圍、NaN、Infinity、空字串不得進入 FitnessConfig。

現有 `Slider` 已能表達 0～100 整數。只需要補上 label、說明、reset 與可捲動容器，
不需要建立可調任意浮點常數的 Advanced 元件。

### 4.5 即時計分預覽

右側摘要區使用固定的 reference context，顯示各項「單幀影響力」：

```text
velocity = 10
progress_delta = 1
progress_ratio = 0.5
center_offset = 0
heading_delta = 0°
min_clearance = 90
time_elapsed = 10s
```

顯示：

```text
Speed      +...
Progress   +...
Centered   +...
Alignment  +...
Safety     +...
Built-in   +...
Stall      -...
Spin       -...
Wrong way  -...
Time       -...
Crash      -...
Finish     +...
```

此預覽必須呼叫正式 `BeginnerMix` 計分器的 breakdown API，不可以在 UI 另外複製
一套公式，否則之後公式修改會造成顯示與實際結果不一致。

### 4.6 Preset

第一版至少提供：

- `Default BeginnerMix`
- `Progress First`
- `Safe Centerline`
- `Anti Spin`
- `Time Attack`

Preset 只保存十個權重與 `algorithm_version`。固定公式常數不進入 preset。

套用 preset 後只更新目前編輯中的 draft；使用者按 `Go` 後才建立不可變的
FitnessConfig 給 Training session。

## 5. 資料契約

### 5.1 新版 JSON

建議將 FitnessConfig 升級為 schema version 2：

```json
{
  "schema_version": 2,
  "mode": "beginner_mix",
  "algorithm_version": "beginner-mix-v1",
  "rewards": {
    "speed": 50,
    "progress": 50,
    "centered": 50,
    "alignment": 50,
    "safety": 50
  },
  "penalties": {
    "stall": 50,
    "spin": 50,
    "wrong_way": 50,
    "time": 50,
    "crash": 50
  }
}
```

JSON 只允許十個權重。公式常數不放入使用者 config；`algorithm_version` 唯一決定
整套固定常數與計算語意。讀到未知 version 必須拒絕，不可退回近似公式。

### 5.2 Python Contract

使用者可控制的 contract 只有：

```python
@dataclass(frozen=True, slots=True)
class FitnessConfig:
    schema_version: int
    mode: str
    algorithm_version: str
    rewards: dict[str, float]
    penalties: dict[str, float]
```

使用 `frozen=True` 是為了讓一場 Training 開始後，設定不會被 UI draft 意外改動。

固定值定義於程式內部：

```python
@dataclass(frozen=True, slots=True)
class FitnessProfile:
    profile_id: str = "beginner-mix-v1"
    speed_effect: float = 1.0
    progress_effect: float = 10.0
    centered_effect: float = 2.0
    alignment_effect: float = 3.0
    safety_effect: float = 3.0
    progress_ratio_bonus: float = 0.5
    behavior_penalty_scale: float = 10.0
    time_penalty_scale: float = 0.1
    crash_penalty_scale: float = 1000.0
    finish_bonus: float = 10000.0
    safety_clearance_reference: float = 90.0
    stall_speed: float = 0.5
    spin_angle: float = 5.0
    spin_progress: float = 0.1
    wrong_way_angle: float = 90.0
```

`FitnessProfile` 不得由 UI、preset、TrainingRecord 或外部 JSON 建構。若要變更任何
固定值，新增 profile ID 並保留舊 profile，確保舊 artifact 仍可重播。

### 5.3 Parameter Registry

所有 key、名稱、群組、範圍、step、預設值與說明集中在單一 registry：

```python
@dataclass(frozen=True, slots=True)
class ParameterSpec:
    key: str
    group: str
    label: str
    minimum: int
    maximum: int
    default: int
    unit: str
    description: str
```

Registry 必須剛好包含十個 key；測試應斷言沒有第十一個可調參數。

Registry 同時供：

- UI 建立控制項
- Config validation
- Reset default
- Preset validation
- Summary 顯示
- 測試 parameter coverage

不得在 `screens.py`、`fitness.py` 和 `contracts.py` 各自維護一份 key 清單。

## 6. 舊資料相容

目前舊版資料格式為：

```json
{
  "weights": {
    "baseline_distance": 50,
    "progress_speed": 50,
    "checkpoint_progress": 50
  }
}
```

這三個 strategy 的加權結果無法無損轉換成十個 BeginnerMix 權重。因此不能假裝
轉換成功。

讀取邏輯：

1. 有 `schema_version: 2`：讀取新版 BeginnerMix。
2. 沒有 schema version 且有 `weights`：標記為 `legacy_strategy_mix`。
3. Legacy record 在 Validation 時繼續使用舊 `score_with_config()`。
4. Legacy record 在列表顯示 `Legacy fitness`。
5. 使用者若要重新 Training，必須明確選擇新版 preset；不自動猜測十個參數。

TrainingRecord 保存十個 weights 與 `algorithm_version`。公式常數由 version
解析，不能隨 record 覆寫。

## 7. Runtime 架構

### 7.1 TrackGeometry

新增地圖幾何物件，負責：

- 從 map JSON 依 tile connection 建立有順序的 `route_cells`。
- 將 cell 轉成中心點 polyline。
- 計算 closed-loop total length。
- 將車輛中心投影到最近線段。
- 回傳 `progress`、`center_offset`、`target_heading`。

建議位置：

```text
game_engine/backend/track_geometry.py
```

Difficulty map pool 應從 `(front_path, back_path)` 改成明確資料類別：

```python
@dataclass(frozen=True, slots=True)
class TrackAsset:
    metadata_path: Path
    front_path: Path
    back_path: Path
```

如此 Training 和 Validation 才能使用同一張圖的 JSON 幾何。

### 7.2 StepContext

每幀計分只接收不可變 context：

```python
@dataclass(frozen=True, slots=True)
class StepContext:
    velocity: float
    progress_delta: float
    progress_ratio: float
    center_offset: float
    normalized_center_offset: float
    heading_delta: float
    heading_alignment: float
    min_clearance: float
    collided: bool
    finished: bool
    is_stalled: bool
    is_spinning: bool
    is_wrong_way: bool
    frame: int
    time_elapsed: float
```

`StepContext` 不應讀 Pygame Surface，也不應直接依賴 UI，才能做 deterministic
unit test。

### 7.3 FitnessTracker

每台車配置獨立 tracker：

```python
@dataclass(slots=True)
class FitnessTracker:
    previous_progress: float
    cumulative_progress: float
    total_fitness: float
    finished: bool
    crashed: bool
    frame: int
```

職責：

- 保存上一幀 progress。
- 修正 closed-loop wrap-around。
- 計算 positive-only `progress_delta`。
- 累加 `cumulative_progress`。
- 確保 crash penalty 與 finish bonus只觸發一次。
- 保存最新 breakdown 給 debug overlay。
- reset／breed／換地圖時清空狀態。

不要將這些暫態欄位動態 `setattr()` 到 Car 上。Car 應保持物理與 NN 狀態，
FitnessTracker 管理評分狀態。

### 7.4 BeginnerMix

`GA/fitness.py` 提供：

```python
class BeginnerMix:
    def score_step(
        self,
        context: StepContext,
        config: FitnessConfig,
    ) -> FitnessBreakdown:
        ...
```

Breakdown：

```python
@dataclass(frozen=True, slots=True)
class FitnessBreakdown:
    rewards: dict[str, float]
    penalties: dict[str, float]
    progress_ratio_bonus: float
    crash_penalty: float
    finish_bonus: float
    total: float
```

總分使用 `breakdown.total`，UI 預覽與 debug 顯示則讀取各子項。
`BeginnerMix` 依 `config.algorithm_version` 取得內建的 immutable
`FitnessProfile`；`FitnessConfig` 本身不能傳入或覆寫任何公式常數。

### 7.5 Training loop 串接

每幀流程：

```text
依目前 sensors 進行 feedforward
        ↓
依 outputs 套用 action
        ↓
保存 previous angle/progress
        ↓
Car.update()（固定 simulation tick）
        ↓
TrackGeometry.project(car.center)
        ↓
判定 collision / finished / stall / spin / wrong-way
        ↓
建立 StepContext
        ↓
BeginnerMix.score_step()
        ↓
FitnessTracker.total_fitness += breakdown.total
```

車輛的有效排序分數統一取：

```text
tracker.total_fitness
```

不再發生：

- 碰撞時用 `RuntimeSettings.fitness_strategy`
- 儲存時又用另一份 `FitnessConfig`
- Validation 再用第三種計算時間點

### 7.6 TrainingSession

TrainingSession 應持有：

```text
active_fitness_config
track_geometry
car_id → FitnessTracker
```

以下事件必須重設 tracker：

- 建立新 population
- breed
- reset generation
- 切換地圖
- 載入新 model

只更換車輛圖片或 debug 顯示不應重設 tracker。

### 7.7 Validation

Validation 讀取 TrainingRecord 中保存的完整 FitnessConfig，建立相同
TrackGeometry、FitnessTracker、BeginnerMix 與 SimulationProfile。

Validation 結束時顯示：

- total fitness
- progress ratio
- finish time
- collision
- reward subtotal
- penalty subtotal

Legacy TrainingRecord 則走明確的 legacy evaluator。

## 8. gangexp 實驗結果重現

### 8.1 名詞與重現目標

本文件中的 `gangexp` 指 workspace 內的 `NNCars-Fitness-Experiments`。

「可以在前端重現」定義為：

1. 載入相同 network weights／biases。
2. 使用相同地圖幾何與 spawn。
3. 每一 tick 產生相同的六個 NN inputs。
4. 每一 tick 產生相同的四個 NN outputs 與動作。
5. 車輛位置、角度、速度、progress 與碰撞狀態在容許誤差內相同。
6. `finished`／`collided` 結果相同。
7. 完賽模型的 finish tick 必須完全相同。

畫面像素可以因 renderer 不同而有差異，但模擬狀態不可由 Pygame frame timing 或
縮放改變。

### 8.2 Fitness 權重和 Replay 的關係

模型訓練完成後，十個 fitness 權重不會進入 neural network 的 feedforward，也不會
改變車輛操作。它們只影響 Training 時哪些車被選為父母。

因此：

- 重播既有 gangexp model 只需要 weights、biases、地圖與 simulation profile。
- 不需要把 gangexp 的舊 strategy 強行轉換成十個 BeginnerMix 滑桿。
- 若要從該 model 繼續 Training，才需要明確指定新的十參數 FitnessConfig。
- gangexp 的 `race_metric_proxy` 等舊 strategy 可以保留 provenance，但不能偽裝成
  等價的 BeginnerMix 配方。

### 8.3 已驗證的 gangexp Artifact

目前可作為第一個 conformance fixture 候選的 artifact：

```text
NNCars-Fitness-Experiments/artifacts/runs/
20260621T082739Z_race_metric_control_30/
strategies/race_metric_proxy/best_model.npz
```

其 metadata 包含：

```text
architecture = [6, 6, 4]
fps = 30
max_speed = 10.0
time_limit_seconds = 30.0
track_half_width = 34.0
model_architecture_version = v1
map = maps/manual/hard_test.json
```

同一 run 的 validation 紀錄包含成功完賽 episode。不過，現有 metadata 同時記錄
`hard_test.json` 和 validation seed 清單，而 validation episode 又以 seed 標示；
因此不能直接假設其中任一 finish tick 就對應 `hard_test.json`。

正式建立 fixture 前，必須用指定的 model 與明確指定的 map 再執行一次 gangexp
headless replay，將這次單一、無歧義的結果寫入 bundle 與 golden trace。舊
`validation.json` 只作為 artifact discovery 證據，不直接當 conformance oracle。

`hard_test.json` 與前端 `maps/kaggle_maps/kaggle_hard.json` 的原始檔案 SHA-256
不同，但忽略 `name`、metrics 與 JSON 排版後，canvas、grid、start、finish 和排序
後 tiles 的 canonical geometry fingerprint 相同：

```text
c932dd97c8c67bc6e4beb4c9135e9f6c4359a5f52531c6099e21100ca9d32c06
```

前端應依 canonical geometry fingerprint 配對地圖，不能只比檔名或原始檔案 hash。

### 8.4 目前 gangexp 與前端的關鍵差異

| 行為 | gangexp | 目前前端 | 重現要求 |
| --- | --- | --- | --- |
| 感測器起點 | 車中心外 10 px | 車中心外 10 px | 相同 |
| 感測器向外步長 | 4 px | 10 px | 前端 compatibility mode 改用 4 px |
| 感測器越界修正 | 往回 1 px | 往回 1 px | 相同 |
| 碰撞 | 車角到中心線距離與 `half_width` | PNG alpha pixel | compatibility mode 使用中心線 |
| 控制順序 | feedforward → action → update | update → feedforward → action | compatibility mode 使用 gangexp 順序 |
| sigmoid | input clamp 到 `[-60, 60]` | 未 clamp | compatibility mode 使用 clamp |
| spawn | JSON 中心線第一點與方向 | hard-coded 座標 | compatibility mode 使用 JSON |
| timestep | 固定 30 FPS tick | display loop FPS | 模擬 tick 與 renderer 解耦 |
| 結束條件 | collision／finish／900 frames | 主要由 UI loop 控制 | compatibility mode 完全對齊 |

只匯入 weights 而繼續使用目前前端 Car loop，不能保證原本可完賽的模型仍然完賽。

### 8.5 固定 Simulation Profile

新增不可由使用者調整的：

```text
simulation_profile_id = gangexp-v1
```

此 profile 固定：

```text
fps = 30
time_limit_seconds = 30
max_frames = 900
architecture = [6, 6, 4]
activation = sigmoid with pre-exp clamp [-60, 60]
input_order = [front, +45, -45, +90, -90, velocity]
output_order = [accelerate, brake, turn_left, turn_right]
action_threshold = 0.5
acceleration_step = 0.2
coast_multiplier = 0.92
max_speed = 10
turn_step_degrees = 5
car_width = 17
car_height = 35
sensor_angles = [0, 45, -45, 90, -90]
sensor_start_distance = 10
sensor_march_step = 4
sensor_boundary_backtrack = 1
track_half_width = 34
tick_order = feedforward → action → update → collision → finish
```

這些不是第十一個以上的 UI 參數。Profile ID 決定全部數值，使用者不能覆寫。

### 8.6 模型交換格式

前端不應直接對任意使用者提供的 `.npz` 執行 `allow_pickle=True`。gangexp 需提供
一次性的 exporter，將 artifact 轉為安全、可驗證的 JSON model bundle。

建議格式：

```json
{
  "bundle_version": 1,
  "model_version": "gangexp-model-v1",
  "simulation_profile_id": "gangexp-v1",
  "architecture": [6, 6, 4],
  "weights": [[], []],
  "biases": [[], []],
  "track": {
    "map_id": "kaggle_hard",
    "geometry_fingerprint": "c932dd97..."
  },
  "provenance": {
    "run_id": "20260621T082739Z_race_metric_control_30",
    "strategy_name": "race_metric_proxy",
    "generation": 26,
    "evolution_seed": 3057
  },
  "expected_result": {
    "completed": true,
    "finish_tick": 868
  }
}
```

`expected_result` 必須由 exporter 對指定的 model＋map 再跑一次 headless replay 後寫入，
不能只抄整個 validation summary 中任意 episode。上面的 `868` 只是格式範例，不是
目前 artifact 已驗證的 hard-test oracle。若同一模型在多張圖測試，使用一個
map/result entry 陣列。

Bundle 驗證：

- architecture 必須等於 `[6, 6, 4]`。
- weight shapes 必須是 `(6, 6)`、`(4, 6)`。
- bias shapes 必須是 `(6, 1)`、`(4, 1)`。
- 所有數值必須 finite。
- simulation profile 必須是前端支援的 ID。
- geometry fingerprint 必須和實際載入地圖一致。
- 不允許 bundle 覆寫固定 simulation constants。

### 8.7 前端 Compatibility Replay

新增獨立的 headless-compatible simulation path，renderer 只消費 state：

```text
ModelBundle + Track JSON
          ↓
GangexpV1Simulator.tick()
          ↓
SimulationState
          ├──→ Pygame renderer
          ├──→ metrics
          └──→ golden trace
```

不得讓 Pygame renderer 自己再呼叫另一套 `Car.update()`。視窗卡頓時可以一幀 render
多個 simulation ticks，但不能用 wall-clock delta 改變物理。

一般手動遊戲若仍需要 PNG collision，可保留 legacy Car；匯入 gangexp model 的
Replay／Validation 必須明確使用 `gangexp-v1` compatibility simulator。

### 8.8 Golden Trace

gangexp exporter 除了 bundle，還應產生 canonical trace：

```json
{
  "trace_version": 1,
  "simulation_profile_id": "gangexp-v1",
  "geometry_fingerprint": "c932dd97...",
  "frames": [
    {
      "tick": 1,
      "inputs": [],
      "outputs": [],
      "x": 0.0,
      "y": 0.0,
      "angle": 0.0,
      "velocity": 0.0,
      "progress": 0.0,
      "collided": false,
      "finished": false
    }
  ]
}
```

Conformance test 必須逐 tick 比較：

- inputs／outputs
- x／y
- angle／velocity
- progress／center offset
- collision／finish

驗收容許：

```text
finish tick：完全相同
boolean state：完全相同
float state：absolute tolerance <= 1e-9
```

如果跨 NumPy／平台後無法達到 `1e-9`，可以根據實測放寬，但不得只驗證「最後看起來
有完賽」。第一個 divergence tick 必須被測試訊息指出。

### 8.9 Reproduction Gate

前端載入 gangexp bundle 時：

1. 驗證 bundle schema。
2. 驗證 model shapes。
3. 驗證 simulation profile。
4. 驗證 map geometry fingerprint。
5. 執行 headless compatibility replay。
6. 比對 expected result。
7. 通過後才允許標記為 `REPRODUCED` 並進入視覺 replay。

任何一項不符都顯示具體原因，例如：

```text
INCOMPATIBLE_MAP
UNSUPPORTED_SIMULATION_PROFILE
MODEL_SHAPE_MISMATCH
NON_FINITE_MODEL_VALUE
FINISH_TICK_MISMATCH
TRACE_DIVERGENCE_AT_TICK_137
```

不得靜默改用 legacy physics，因為那會讓「模型重現失敗」看起來像模型本身失效。

## 9. UI 狀態管理

設定畫面應區分：

- `draft_config`：目前 UI 正在編輯的 mutable state。
- `active_config`：按下 Go 後建立的 immutable snapshot。
- `saved_config`：隨 TrainingRecord 持久化的 snapshot。

資料流：

```text
Parameter Registry
        ↓
Default / Preset
        ↓
draft_config ←→ UI controls
        ↓ Go + validation
active_config
        ↓ Training
saved_config in TrainingRecord
        ↓ Validation
same evaluator
```

Training 進行中不允許回到設定畫面直接修改 active config。若未來需要 live tuning，
必須明確記錄變更發生的 generation 和 frame，否則訓練無法重現。

## 10. 驗證規則

### 10.1 通用規則

- 所有值必須是 finite number。
- 不接受 bool 當數字。
- 不接受未知 key。
- 不接受缺少 required key。
- UI 值依 ParameterSpec 做 clamp 與 step rounding。
- 從檔案讀取的值若超界應回報錯誤，不應靜默 clamp，避免損壞配方未被發現。

### 10.2 Cross-field 規則

- 十個 key 必須完整且只能各出現一次。
- 每個值必須是 0～100 的整數。
- `algorithm_version` 必須是支援的固定 profile。
- 至少一個 reward 大於 0，否則顯示「缺少正向學習訊號」警告。
- 所有 reward 都是 0 且 penalty 很高時允許儲存，但 Go 前要求使用者確認

### 10.3 Scale 警告

UI 應顯示非阻擋警告：

- `progress_effect × progress weight` 遠大於其他 reward。
- crash penalty 小於單秒可取得的 reward。
- 全部 penalty 為 0。

警告計算同樣應集中在 domain layer，不放在 draw loop。

## 11. Preset

Preset 建議放在：

```text
configs/fitness_presets.json
```

格式：

```json
{
  "schema_version": 1,
  "presets": [
    {
      "id": "default_beginner_mix",
      "name": "Default BeginnerMix",
      "fitness_config": {}
    }
  ]
}
```

Preset 只能包含十個 weights 與 `algorithm_version`，不得包含固定公式常數或
simulation constants。

匯入流程：

1. JSON parse。
2. Schema validation。
3. Algorithm version validation。
4. 拒絕任何第十一個參數或固定常數 override。
5. 顯示即將覆蓋的十個欄位摘要。
6. 使用者確認後寫入 draft。

第一版若不做系統檔案選擇器，可先提供內建 preset 與「複製／貼上 JSON」畫面，
但 domain schema 必須先完成。

## 12. 建議檔案調整

| 檔案 | 調整 |
| --- | --- |
| `shared/contracts.py` | 只含十權重的 FitnessConfig、ModelBundle、legacy parser |
| `GA/fitness.py` | StepContext、固定 FitnessProfile、BeginnerMix、legacy evaluator |
| `game_engine/backend/track_geometry.py` | 中心線、投影、progress、heading |
| `game_engine/backend/fitness_tracker.py` | 每台車的逐幀狀態與累積分數 |
| `game_engine/backend/gangexp_compat.py` | `gangexp-v1` 固定模擬 profile |
| `game_engine/backend/model_bundle.py` | 安全 JSON bundle 載入與驗證 |
| `game_engine/backend/training_session.py` | active config 與 tracker lifecycle |
| `game_engine/backend/settings.py` | TrackAsset 與 JSON metadata path |
| `game_engine/frontend/widgets.py` | 十個整數 slider、scroll container、tooltip |
| `game_engine/frontend/screens.py` | 十參數 editor、preview、preset、重現狀態 |
| `game_engine/frontend/app.py` | 將逐幀 evaluator 接入 Training |
| `game_engine/backend/record_store.py` | v2 config round-trip，不破壞 legacy record |
| `configs/fitness_presets.json` | 內建完整配方 |
| `tests/fixtures/gangexp/` | model bundle、map fingerprint、golden trace |
| `tests/` | domain、UI、integration、migration、conformance tests |
| gangexp exporter | `.npz` 轉安全 bundle 與 golden trace |

## 13. 實作階段

### Phase 1：Domain 與資料契約

1. 建立 Parameter Registry。
2. 建立 v2 FitnessConfig。
3. 建立 legacy parser。
4. 實作 BeginnerMix 與 breakdown。
5. 寫死並版本化 `beginner-mix-v1` 公式常數。
6. 對十個可調參數與所有固定常數寫 unit tests。

完成條件：給定 StepContext 與 config，可在不啟動 Pygame 的情況下得到正確分數。

### Phase 2：TrackGeometry 與 Tracker

1. 從 map JSON 建立中心線。
2. 實作 projection、heading、closed-loop delta。
3. 實作 FitnessTracker。
4. 更新 difficulty map pool。

完成條件：可用固定座標測試 progress、center offset、angle 和跨圈。

### Phase 3：Runtime Integration

1. Training 每幀建立 StepContext。
2. 所有車輛累積 fitness。
3. breed／save 使用同一 total。
4. Validation 使用同一 evaluator。
5. lifecycle event 正確 reset tracker。

完成條件：同一 model、map、config 在 Training replay 與 Validation 得到相同分數。

### Phase 4：Parameter Editor

1. 建立十個 0～100 整數 slider。
2. Scroll container。
3. Reset、preset、validation warning。
4. 即時計分 breakdown。
5. 確認 UI 與 JSON 都無法覆寫固定常數。

完成條件：剛好十個參數可調整、可重設且不發生畫面重疊；不存在 Advanced 入口。

### Phase 5：Persistence 與 Migration

1. TrainingRecord 保存完整 v2 config。
2. 新 config round-trip。
3. 舊 record 走 legacy evaluator。
4. Validation list 顯示 mode／preset 摘要。

完成條件：重啟程式後載入 record，計分設定不遺失。

### Phase 6：gangexp Compatibility

1. 定義並寫死 `gangexp-v1` simulation profile。
2. 製作安全 model bundle exporter／loader。
3. 加入 canonical map geometry fingerprint。
4. 以前端 compatibility simulator 重播 golden artifact。
5. 逐 tick 比對 golden trace。
6. Pygame renderer 改為消費 compatibility simulation state。

完成條件：成功 artifact 在相同 map 上的 finish status 與 finish tick 和 gangexp
完全一致，並通過完整 trace conformance test。

## 14. 測試設計

### 14.1 Fitness Unit Tests

每個參數至少測試：

- weight 0
- weight 100
- factor 邊界
- 未觸發與觸發 penalty

固定測試案例：

- `progress=60`、`delta=1` 得到 6。
- `speed=40`、`velocity=10` 得到 4。
- `stall=100`、stalled 時扣 10。
- `crash=100`、crashed 時一次扣 1000。
- finish 一次加 10000。
- 測試固定常數不能被 config 覆寫。

### 14.2 Geometry Tests

- 水平、垂直線段投影。
- corner 附近選擇最近線段。
- center offset。
- 四個主要方向 heading。
- 350° 與 10° 的最短角差。
- closed-loop 正向跨圈。
- closed-loop 反向跨圈。
- negative progress 截為 0。

### 14.3 Tracker Tests

- 每幀累加。
- crash 只扣一次。
- finish 只加一次。
- reset 清空所有狀態。
- 切圖不保留 previous progress。

### 14.4 Contract Tests

- v2 JSON round-trip。
- NaN／Infinity／unknown key 被拒絕。
- 第十一個參數被拒絕。
- 固定常數 override 被拒絕。
- legacy record 正確辨識。
- v2 config 保存於 TrainingRecord 後保留十權重與 profile ID。

### 14.5 UI Tests

- scroll hit testing 使用正確座標。
- reset field／group／all。
- Go 遇到 invalid config 不離開畫面。
- 畫面不存在 Advanced 或固定常數輸入。

### 14.6 Integration Tests

- Training loop 使用 UI 傳入的 config。
- parent selection 使用累積 BeginnerMix total。
- save record 保存同一 config。
- Validation 載入後重現同一 total。
- legacy record 仍能 Validation。
- gangexp bundle 載入後使用 compatibility simulator。
- map fingerprint 不符時拒絕 replay。
- finish tick 與 golden result 完全相同。
- golden trace 第一個 divergence tick 可被精確回報。

### 14.7 Manual Verification

- 1600×900 下所有控制項可見且可捲動。
- Reward／Penalty 顏色與分組清楚。
- 剛好十個滑桿且沒有重疊。
- 使用者找不到修改公式常數或 simulation constants 的入口。
- Debug overlay 的 breakdown 和單元測試範例一致。
- gangexp 成功模型顯示 `REPRODUCED`，且視覺 replay 完成賽道。

## 15. 驗收標準

功能完成必須同時符合：

1. UI 剛好顯示十個 fitness 參數。
2. 每個 UI 值實際影響 Training 的逐幀分數。
3. Training、選父母、儲存與 Validation 使用同一 config snapshot。
4. 十個權重範圍為 0～100 的整數。
5. 使用者無法從 UI、preset 或 JSON 修改固定常數。
6. 所有值經 domain validation，不只依賴 UI clamp。
7. Config 與 TrainingRecord 可以 round-trip。
8. 舊 record 不會因 schema 升級而無法讀取。
9. crash 與 finish 保證只計一次。
10. 同一 model、map、config 可重現相同 fitness。
11. gangexp bundle 的 model shape、profile 與 map fingerprint 皆被驗證。
12. gangexp 成功模型在前端得到相同 finish status 與 finish tick。
13. gangexp／前端 golden trace 通過逐 tick 比對。
14. 新增的 domain、integration 與 conformance tests 全部通過。
15. 文件公式、預設值與程式 constants 一致。

## 16. 主要風險與對策

| 風險 | 影響 | 對策 |
| --- | --- | --- |
| 只完成 UI，runtime 仍走舊 strategy | 滑桿看似有效但訓練不受影響 | Integration test 驗證 config 到 score |
| 地圖只有 PNG，沒有中心線 | progress/alignment 無法計算 | difficulty map 改用 TrackAsset + JSON |
| 固定常數被 preset 偷偷覆寫 | 表面只有十參數，實際規則可變 | Schema 拒絕任何 override |
| 舊 config 無法等價轉換 | 舊 record 分數改變 | 明確 legacy mode，不做假轉換 |
| Formula 在 UI 與 GA 重複 | 顯示和實際分數漂移 | 共用 FitnessBreakdown API |
| Progress 來回累積 | 可能假完賽 | v1 保持相容，後續另開 algorithm version |
| FPS 影響逐幀總分 | 重現性下降 | 保存 FPS；未來用新 algorithm version 引入 dt |
| 只匯入 gangexp weights | 模型在不同 sensor／physics 下失效 | 固定 compatibility simulator |
| 地圖檔名相同但幾何不同 | 重播結果不可重現 | canonical geometry fingerprint |
| Renderer 使用另一套 Car.update | 畫面與 headless 結果分歧 | renderer 只消費 SimulationState |
| `.npz allow_pickle` 載入不可信資料 | 任意物件反序列化風險 | gangexp 先匯出安全 JSON bundle |

## 17. 實作前確認事項

本設計採用以下決策：

- 使用者只能調整十個行為權重。
- 所有底層公式常數、門檻與 simulation constants 寫死並版本化。
- 不提供 Advanced 分頁或第十一個參數。
- 第一版遵循 `fitness-calculation.md` 的 positive-only progress 與無 dt 語意。
- 舊三策略資料保留 legacy evaluator。
- Training 開始後 config 固定，不支援中途 live tuning。
- gangexp model replay 使用固定 `gangexp-v1` compatibility simulator。
- 重現成功以 finish tick 與 golden trace 為準，不以肉眼看起來相似為準。
