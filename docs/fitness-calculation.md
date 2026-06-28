# BeginnerMix 十個 Fitness 參數計算說明

本文件說明目前 `pipeline/fitness.py` 與 `pipeline/simulator.py` **實際執行**
的計分邏輯。內容以程式碼為準，不以舊版設計文件中的公式為準。

## 1. 計分流程總覽

`BeginnerMix` 有十個可調參數：

- Reward：`speed`、`progress`、`centered`、`alignment`、`safety`
- Penalty：`stall`、`spin`、`wrong_way`、`time`、`crash`

模擬器每一幀依序執行：

1. 將五條距離感測器與目前速度送進 neural network。
2. 根據 network output 決定加速、煞車、左轉或右轉。
3. 更新速度、方向與座標。
4. 把車輛中心投影到賽道中心線，取得賽道進度與中心偏移。
5. 計算前進距離、方向對齊程度、牆壁距離、停滯、旋轉和碰撞狀態。
6. 計算該幀的 fitness。
7. 將該幀 fitness 累加到整場的 `training_fitness`。

一場 episode 的總分是：

```text
training_fitness = Σ 每一幀的 step_fitness
```

若同一台車需要跑多張 training map，最後用各張地圖的
`training_fitness` 平均值作為 GA 排序分數。

## 2. 座標與角度定義

Pygame 畫面的座標原點在左上角：

```text
                 y 減少
                    ↑
                    │
        x 減少  ←───┼───→  x 增加
                    │
                    ↓
                 y 增加
```

本專案的車輛角度定義為：

| `angle` | 車頭方向 |
| ---: | --- |
| `0°` | 向下，y 增加 |
| `90°` | 向左，x 減少 |
| `180°` | 向上，y 減少 |
| `270°` | 向右，x 增加 |

車輛以速度 `v` 移動時：

```text
radian = radians((-angle) mod 360)
new_x = old_x + v × sin(radian)
new_y = old_y + v × cos(radian)
```

這和一般數學上「0° 向右、逆時針增加」的定義不同。閱讀方向夾角公式時，
必須使用本專案的角度系統。

## 3. 賽道中心線如何建立

地圖會先轉成依行駛順序排列的中心點：

```text
polyline = [P0, P1, P2, ..., Pn]
```

每個點通常是道路 tile 的中心：

```text
center_x = offset_x + cell_x × cell_size + cell_size / 2
center_y = offset_y + cell_y × cell_size + cell_size / 2
```

相鄰中心點形成一個賽道線段：

```text
segment_0 = P0 → P1
segment_1 = P1 → P2
...
```

封閉賽道還會增加最後一段：

```text
segment_n = Pn → P0
```

賽道總長 `L` 是所有中心線線段的歐氏距離總和：

```text
segment_length = sqrt((end_x - start_x)² + (end_y - start_y)²)
L = Σ segment_length
```

這裡計算的是中心線長度，不是車輛實際軌跡長度。

## 4. 車輛如何投影到賽道中心線

`progress`、`center_offset` 與賽道方向都依賴車輛中心在中心線上的投影。

對每一條中心線線段，定義：

```text
S = 線段起點
E = 線段終點
P = 車輛中心
V = E - S
U = P - S
```

先用 dot product 計算投影比例：

```text
t_raw = dot(U, V) / dot(V, V)
t = clamp(t_raw, 0, 1)
```

`t` 的意思是：

- `t = 0`：投影在線段起點
- `t = 0.5`：投影在線段正中央
- `t = 1`：投影在線段終點
- 超出線段的投影會被限制在 0～1

投影點為：

```text
Q = S + t × V
```

車輛到這條線段的距離為：

```text
distance(P, Q) = sqrt((P.x - Q.x)² + (P.y - Q.y)²)
```

程式會測試所有中心線線段，選擇距離車輛最近的線段。該線段的 `Q` 就是
車輛在賽道上的投影點。

得到兩個值：

```text
car.progress =
    投影線段之前所有線段的長度
    + 目前投影線段長度 × t

car.center_offset = distance(P, Q)
```

注意：

- `center_offset` 是沒有正負號的絕對距離，無法分辨車在中心線左側或右側。
- 如果賽道不同路段靠得很近，程式永遠選幾何距離最近的線段，不會檢查上一幀
  所在的線段。這可能讓 `progress` 突然跳到另一段。

## 5. `progress`：每幀前進距離如何計算

### 5.1 原始進度差

更新位置前，程式保存：

```text
last_progress = 上一幀投影到中心線的累積距離
```

更新位置並重新投影後得到：

```text
current_progress = 目前投影到中心線的累積距離
raw_progress_delta = current_progress - last_progress
```

例子：

```text
last_progress = 120 px
current_progress = 126 px
raw_progress_delta = 6 px
```

### 5.2 封閉賽道跨越起終點的修正

封閉賽道的 `progress` 範圍約為 `0～L`。車輛正向越過終點時，數值會從接近
`L` 跳回接近 `0`，直接相減會得到很大的負數。

若：

```text
raw_progress_delta < -L / 2
```

程式假設車輛正向跨過起終點，改算：

```text
raw_progress_delta = (L - last_progress) + current_progress
```

例如：

```text
L = 1000
last_progress = 995
current_progress = 3
修正後 delta = (1000 - 995) + 3 = 8 px
```

反過來，如果：

```text
raw_progress_delta > L / 2
```

程式假設車輛反向越過起終點，改算：

```text
raw_progress_delta = raw_progress_delta - L
```

例如：

```text
L = 1000
last_progress = 3
current_progress = 995
修正後 delta = 992 - 1000 = -8 px
```

### 5.3 負進度會被截成 0

真正提供給 fitness 的值是：

```text
progress_delta = max(0, raw_progress_delta)
```

因此：

- 正向前進 6 px：`progress_delta = 6`
- 沒移動：`progress_delta = 0`
- 反向後退 6 px：`progress_delta = 0`，不會得到 `-6`

接著累加：

```text
cumulative_progress += progress_delta
```

完成比例為：

```text
progress_ratio = clamp(cumulative_progress / L, 0, 1)
```

當：

```text
cumulative_progress >= L
```

程式就判定完成一圈。

### 5.4 目前 progress 邏輯的限制

目前只累加正向 delta，反向 delta 不會扣回。因此車輛可以：

1. 正向跑過某段，取得 progress。
2. 轉頭倒回去，累積 progress 不減少。
3. 再次正向跑相同路段，再取得一次 progress。

所以 `cumulative_progress` 不一定等於「從起點到目前位置的真實圈內進度」，
而是「整場所有正向投影位移的總和」。理論上來回跑同一路段也可能累積到 `L`
並被判定完賽。

## 6. `speed`：速度如何計算

速度更新規則：

```text
有加速或煞車指令：
    velocity += acceleration

沒有加速或煞車指令：
    velocity *= 0.92
```

其中：

```text
加速 acceleration = +0.2
煞車 acceleration = -0.2
速度限制 = 0～10
```

`speed` reward 使用更新後的原始 `velocity`，沒有除以最高速度，也沒有考慮
車輛是否沿正確方向前進：

```text
speed_factor = max(0, velocity)
```

因此快速逆向行駛仍然可以取得 `speed` reward；是否抵消要看 `alignment` 與
`wrong_way` 的權重。

## 7. `centered`：離中心線多近

由第 4 節的中心線投影取得：

```text
center_offset = 車輛中心到最近中心線線段的距離
normalized_center_offset = center_offset / track.half_width
```

接著：

```text
centered_factor = clamp(1 - normalized_center_offset, 0, 1)
```

例子，假設 `half_width = 42`：

| `center_offset` | `normalized_center_offset` | `centered_factor` |
| ---: | ---: | ---: |
| 0 px | 0 | 1 |
| 10 px | 0.238 | 0.762 |
| 21 px | 0.5 | 0.5 |
| 42 px | 1 | 0 |
| 50 px | 1.19 | 0 |

此處只使用車輛中心的位置。車輛中心仍在道路內時，車身角落可能已經超出道路並
觸發碰撞。

## 8. `alignment`：賽道方向夾角如何計算

### 8.1 取得賽道目標方向

程式先使用 `car.progress` 找到車輛目前投影所屬的中心線線段。

若該線段是：

```text
S = (start_x, start_y)
E = (end_x, end_y)
dx = end_x - start_x
dy = end_y - start_y
```

目標角度為：

```text
target_heading = (-degrees(atan2(dx, dy))) mod 360
```

注意此處故意使用 `atan2(dx, dy)`，不是常見的 `atan2(dy, dx)`，以符合本專案
0° 向下的角度系統。

### 8.2 將角度差限制在 -180°～180°

車頭角度為 `car.angle`，先算：

```text
heading_delta =
    ((car.angle - target_heading + 180) mod 360) - 180
```

如此可以正確處理 0°/360° 邊界。

例如：

```text
car.angle = 350°
target_heading = 10°
heading_delta = -20°
```

而不是錯誤的 `340°`。

### 8.3 用 cosine 轉成對齊程度

```text
heading_alignment = cos(radians(heading_delta))
```

| 方向夾角絕對值 | `heading_alignment` | 意義 |
| ---: | ---: | --- |
| 0° | 1 | 完全同方向 |
| 30° | 約 0.866 | 大致同方向 |
| 60° | 0.5 | 偏離明顯 |
| 90° | 0 | 與賽道垂直 |
| 120° | -0.5 | 已朝反方向 |
| 180° | -1 | 完全逆向 |

`alignment` reward 使用：

```text
alignment_factor = clamp(heading_alignment, 0, 1)
```

所以超過 90° 後只是不再取得 alignment reward，不會直接產生負 reward。
逆向扣分由 `wrong_way` 負責。

## 9. `safety`：牆壁距離如何計算

車輛有五條感測線：

```text
0°    正前方
+45°  斜前方一側
-45°  斜前方另一側
+90°  車身一側
-90°  車身另一側
```

每條感測線：

1. 從距離車輛中心 10 px 的位置開始。
2. 若仍在賽道內，沿感測方向每次前進 4 px。
3. 第一次到達賽道外時，往回移動 1 px 後停止。
4. 計算車輛中心到停止點的歐氏距離。

程式判定「賽道內」的方式不是讀取 PNG pixel，而是：

```text
感測點到最近中心線的距離 <= track.half_width
```

`safety` 使用五條感測線中最短的一條：

```text
min_clearance = min(sensor_0, sensor_1, sensor_2, sensor_3, sensor_4)
safety_factor = clamp(min_clearance / 90, 0, 1)
```

例子：

| `min_clearance` | `safety_factor` |
| ---: | ---: |
| 0 px | 0 |
| 30 px | 0.333 |
| 45 px | 0.5 |
| 90 px | 1 |
| 120 px | 1 |

因此距離達到 90 px 後不會再增加 safety reward。

## 10. 四個每幀 Penalty 狀態

### 10.1 `stall`

```text
is_stalled = velocity < 0.5
stall_factor = 1 if is_stalled else 0
```

只看速度，不看車輛是否真的長時間停住。起步期間速度低於 0.5 的每一幀也會被
視為 stalled。

### 10.2 `spin`

```text
is_spinning =
    abs(car.angle - previous_angle) >= 5
    and progress_delta < 0.1
```

也就是該幀至少轉 5°，但正向進度不到 0.1 px。

目前 neural network 每次左轉或右轉剛好是 5°，因此只要有轉向且幾乎沒有前進，
通常就會觸發。

### 10.3 `wrong_way`

```text
wrong_way_factor = 1 if heading_alignment < 0 else 0
```

因為 `heading_alignment = cos(heading_delta)`，所以實際條件是車頭與賽道方向
相差超過 90°。

這是二元判斷：

- 偏差 91° 和 180° 都使用相同的 penalty factor 1。
- 偏差 89° 完全不會觸發 wrong-way penalty。

### 10.4 `time`

第 `frame` 幀的經過時間為：

```text
time_elapsed = frame / fps
```

例如在 30 FPS：

```text
第 30 幀：1 秒
第 150 幀：5 秒
第 300 幀：10 秒
```

`time` 每幀都會扣分，而且越晚的幀扣越多。

## 11. `crash`：碰撞如何判定

車輛尺寸為：

```text
width = 17 px
height = 35 px
```

程式先依車頭角度旋轉車身四個角。只要任何一個角不在賽道範圍內：

```text
任一角到最近中心線的距離 > track.half_width
```

就判定：

```text
collided = True
```

碰撞當幀會先計算一次包含 crash penalty 的 fitness，然後 episode 立即停止。因此
正常情況下 crash 是一次性 penalty。

## 12. 十個參數的實際計分公式

設十個滑桿為：

```text
w_speed, w_progress, w_centered, w_alignment, w_safety
w_stall, w_spin, w_wrong_way, w_time, w_crash
```

### 12.1 Reward

```text
R_speed =
    (w_speed / 100)
    × 1
    × max(0, velocity)

R_progress =
    (w_progress / 100)
    × 10
    × max(0, progress_delta)

R_centered =
    (w_centered / 100)
    × 2
    × clamp(1 - center_offset / half_width, 0, 1)

R_alignment =
    (w_alignment / 100)
    × 3
    × clamp(cos(heading_delta), 0, 1)

R_safety =
    (w_safety / 100)
    × 3
    × clamp(min_clearance / 90, 0, 1)
```

另外每幀都有不受滑桿控制的固定進度比例獎勵：

```text
R_builtin_progress = clamp(progress_ratio, 0, 1) × 0.5
```

總 reward：

```text
reward =
    R_speed
    + R_progress
    + R_centered
    + R_alignment
    + R_safety
    + R_builtin_progress
```

### 12.2 Penalty

```text
P_stall =
    (w_stall / 100)
    × 10
    × stall_factor

P_spin =
    (w_spin / 100)
    × 10
    × spin_factor

P_wrong_way =
    (w_wrong_way / 100)
    × 10
    × wrong_way_factor

P_time =
    (w_time / 100)
    × 0.1
    × time_elapsed
```

總 per-frame penalty：

```text
penalty = P_stall + P_spin + P_wrong_way + P_time
```

### 12.3 Crash 與 Finish

撞牆當幀另外扣：

```text
P_crash = (w_crash / 100) × 1000
```

第一次完成一圈時另外加：

```text
R_finish = 10000
```

### 12.4 最終每幀公式

```text
step_fitness = reward - penalty

if collided:
    step_fitness -= P_crash

if finished_now:
    step_fitness += 10000
```

## 13. 完整數值範例

假設配方：

```json
{
  "rewards": {
    "progress": 60,
    "speed": 40,
    "alignment": 0,
    "safety": 50,
    "centered": 20
  },
  "penalties": {
    "stall": 50,
    "spin": 40,
    "wrong_way": 0,
    "time": 30,
    "crash": 70
  }
}
```

某一幀狀態：

```text
velocity = 8
progress_delta = 3 px
progress_ratio = 0.25
center_offset = 10 px
half_width = 42 px
heading_delta = 30°
min_clearance = 45 px
time_elapsed = 5 秒
沒有 stall、spin、wrong_way、crash、finish
```

逐項計算：

```text
R_speed
= 0.40 × 1 × 8
= 3.2

R_progress
= 0.60 × 10 × 3
= 18

centered_factor
= 1 - 10/42
= 0.7619

R_centered
= 0.20 × 2 × 0.7619
= 0.3048

R_alignment
= 0 × 3 × cos(30°)
= 0

safety_factor
= 45/90
= 0.5

R_safety
= 0.50 × 3 × 0.5
= 0.75

R_builtin_progress
= 0.25 × 0.5
= 0.125

P_time
= 0.30 × 0.1 × 5
= 0.15
```

因此：

```text
step_fitness
= 3.2 + 18 + 0.3048 + 0 + 0.75 + 0.125 - 0.15
= 22.2298
```

如果同一幀撞牆：

```text
P_crash = 0.70 × 1000 = 700
step_fitness = 22.2298 - 700 = -677.7702
```

如果同一幀首次完成一圈且沒有撞牆：

```text
step_fitness = 22.2298 + 10000 = 10022.2298
```

## 14. 參數範圍與未指定參數

Reward 在載入時會限制為 0～100：

```text
reward_weight = clamp(config_value, 0, 100)
```

Penalty 目前只限制不能小於 0，沒有 100 的上限：

```text
penalty_weight = max(0, config_value)
```

所以直接在 JSON 寫入 `crash: 150` 時，實際 crash penalty 會是 1500。UI 即使把
滑桿限制為 100，也不代表底層 config loader 有相同上限。

配方未指定的參數不會自動補預設值，而是等同沒有該 reward 或 penalty。

## 15. Fitness 如何影響 GA 與最後模型

Training 階段：

1. 每個 network 在每張 training map 上累加 `training_fitness`。
2. 對所有 training maps 取平均。
3. 依平均 training fitness 由高到低排序。
4. 取前兩名作為父母。
5. 使用 crossover 與 mutation 產生下一代。

Validation 階段保存最佳模型時，主要順序不是 raw fitness，而是：

1. `finish_count` 越多越好。
2. 完賽數相同時，平均完賽時間越短越好。
3. 前兩項相同時，平均最大進度越高越好。

因此十個參數主要負責提供 GA 的學習方向，不等於最後 competition leaderboard
使用的排名公式。

## 16. 現行實作的重要特性與風險

### 16.1 Reward 不會正規化

五個 reward 是直接相加，不會除以 reward 權重總和。多開一個 reward 或把所有
reward 拉高，都會直接增加分數尺度。

### 16.2 Fitness 沒有乘上 `dt`

`speed`、`progress`、`stall`、`spin`、`wrong_way` 等項目每幀計算一次，但沒有乘
`1 / fps`。因此改變 FPS 可能改變同一行為的總 fitness。

例如 `stall = 100` 時每幀扣 10 分：

```text
30 FPS：約每秒扣 300 分
60 FPS：約每秒扣 600 分
```

### 16.3 各 reward 的原始尺度差很多

例如：

```text
speed = 100，velocity = 10：每幀最多約 +10
progress = 100，progress_delta = 10：該幀可 +100
centered = 100：每幀最多 +2
alignment = 100：每幀最多 +3
safety = 100：每幀最多 +3
```

所以相同滑桿數值不代表相同影響力。

### 16.4 `time` 的累積效果接近二次成長

因為每一幀扣的是「目前已經過時間」，第 1 秒每幀扣得少，第 30 秒每幀扣得多。
整場累加後不是單純與時間成正比，而是接近時間平方成長。

### 16.5 Training 完賽後可能繼續計分

Training population 評估目前使用 `stop_on_finish=False`。首次完賽只加一次
`FINISH_BONUS`，但車仍可能繼續跑到時間上限或撞牆。Validation 預設會在首次完賽
時停止。

### 16.6 不同 strategy 的 raw fitness 不適合直接比較

不同策略與不同參數會產生不同分數尺度。`avg_training_fitness` 適合用來比較同一
配方內不同 network，不適合直接判斷兩種 fitness 配方誰比較好。跨配方應優先比較
validation 的完賽數、完賽時間和最大進度。

## 17. 對應程式位置

- 十個參數與最終公式：`pipeline/fitness.py`
- 車輛移動、感測器、碰撞與每幀狀態：`pipeline/simulator.py`
- 中心線投影、進度與方向：`pipeline/track.py`
- 多地圖平均與 GA 選擇：`pipeline/training.py`
- 現有公式測試：`tests/test_beginner_mix.py`

