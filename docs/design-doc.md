# 新 Competition API、評分、Replay、Leaderboard 改版計畫

## Summary

- 將 competition server 改成新的 submission API，只接收隊伍、使用者與模型參數。
- 支援兩階段競賽：`personal` 個人賽與 `group` 小組賽。
- Server 每 60 秒批次評分所有尚未評分的 submissions。
- 每筆 submission 最多模擬 30 秒，使用 checkpoint 計算 `score_laps`。
- Leaderboard 顯示 active phase 前 30 名，`replay.py` 顯示 active phase 前 10 名動畫。
- Admin 頁負責切換 active phase、選擇每階段地圖、reset 目前階段資料。
- WebSocket `/ws/events` 推播完整 leaderboard top30 與 replay top10。
- 新增 mock data CLI，方便後端直接產生多筆訓練資料測試。

## Key Changes

### Submission API

`POST /api/submissions` 只接受新格式：

```json
{
  "group_id": "1",
  "username": "player1",
  "weights": [[36], [24]],
  "biases": [[6], [4]]
}
```

實際欄位規則：

- `group_id`：字串，代表小組競賽身份。
- `username`：字串，代表個人競賽身份。
- `weights`：分層扁平陣列，固定為 `[[36 floats], [24 floats]]`。
- `biases`：分層扁平陣列，固定為 `[[6 floats], [4 floats]]`。
- 神經網路結構固定為 `[6, 6, 4]`，不再由 request 傳入。

成功回應：

```json
{
  "submission_id": "sub_xxxxxxxx",
  "status": "pending",
  "phase": "personal"
}
```

舊格式欄位不再接受，包含：

- `model_version`
- `layer_sizes`
- `fitness_score`
- `generation`
- `track_id`
- `track_seed`
- `nickname`

### Competition Phase

系統有兩個 phase：

- `personal`：個人賽，以 `username` 作為 leaderboard identity。
- `group`：小組賽，以 `group_id` 作為 leaderboard identity。

submission 上傳時會歸屬到當下 active phase。

同一個 identity 可以多次提交，但 leaderboard 只保留最高 `score_laps`：

- personal phase：同一 `username` 只顯示最佳 submission。
- group phase：同一 `group_id` 只顯示最佳 submission，並顯示該最佳成績來自哪個 `username`。

同分時採先提交者優先。

### Leaderboard API

`GET /api/leaderboard` 回傳 active phase 前 30 名。

response 使用 `score_laps` 作為正式排名分數。

個人賽顯示：

- rank
- username
- group_id
- score_laps
- submission_id
- submitted_at
- evaluated_at

小組賽顯示：

- rank
- group_id
- best_username
- score_laps
- submission_id
- submitted_at
- evaluated_at

leaderboard 只顯示已評分完成的 submissions，不顯示 `pending` 或 `evaluating`。

### Replay API

`GET /api/replay/top?n=10` 回傳 active phase 前 10 名，供 `replay.py` 播放。

此 endpoint 公開，不需要 token。

每筆 replay item 需要包含：

- submission_id
- group_id
- username
- score_laps
- weights
- biases

`replay.py` 每輪動畫最多播放 30 秒；若前 10 名車輛全部撞車，則提前結束。

當 replay 播放中收到新的 top10 資料時，不立刻打斷目前動畫，而是暫存到下一輪套用。

### Admin API 與 Admin Page

Admin 頁需要支援：

- 切換 active phase：`personal` / `group`
- 選擇 personal phase 使用的官方地圖
- 選擇 group phase 使用的官方地圖
- reset 目前 active phase 的資料

切換 active phase 時：

- 不刪除另一個 phase 的資料。
- 不重新評分。
- active leaderboard 改為顯示新 phase 的結果。
- 若新 phase 尚無 evaluated submissions，leaderboard 顯示空榜。

同一 phase 內切換地圖時：

- 立即重跑該 phase 中每個 identity 的目前最佳 submission。
- 使用新地圖重新計算 `score_laps`。
- 重跑完成後更新 leaderboard 與 replay top10。

reset 時：

- 只清除目前 active phase 的 submissions 與 results。
- 不影響另一個 phase。

### 地圖與 Checkpoint

正式競賽使用 5 張全新的官方地圖。

這 5 張地圖都由新的 map generator 產生，不沿用目前 `Images/Tracks` 裡既有的兩張圖。

map generator 需要同時輸出：

- track front image
- track collision image
- checkpoint metadata
- spawn position
- spawn angle

每個 phase 每次只使用一張 active official map 評分。

評分方式：

- 每筆 submission 最多模擬 30 秒。
- 透過 checkpoint 計算完成圈數與當前進度。
- 分數欄位為 `score_laps`。
- 30 秒後仍在 running 的車，以當下 checkpoint 進度計算小數圈數。
- 若車輛提前撞車，使用撞車當下進度計算小數圈數。

### Evaluation Worker

Server 每 60 秒批次處理目前尚未評分的 submissions。

批次規則：

- 每筆 pending submission 都要評分。
- 不因同一個 `username` 或 `group_id` 有多筆 pending 就跳過。
- 批次完成後一次性更新 leaderboard/replay 資料。
- 批次完成後推送一次 WebSocket event。

### WebSocket

新增單一 WebSocket endpoint：

```text
GET /ws/events
```

每批評分完成後，server 推送完整資料：

```json
{
  "type": "competition_updated",
  "phase": "personal",
  "map_id": "official_001",
  "updated_at": "2026-06-20T00:00:00Z",
  "leaderboard": [],
  "replay_top": []
}
```

WebSocket payload 包含：

- active phase
- active map
- leaderboard top30
- replay top10
- updated_at

leaderboard 頁收到 event 後立即重畫。

`replay.py` 收到 event 後暫存新的 replay top10，等待下一輪動畫套用。

### Submission Debug APIs

保留 submission 查詢 endpoints 供 debug/admin 使用：

- `GET /api/submissions`
- `GET /api/submissions/{submission_id}`

這兩個 endpoints 需要 admin token。

公開 API 不應直接列出所有 submission 的 weights/biases。

### Local Simulator Upload

本地 simulator 中按 `U` 的提交流程需要同步更新成新格式。

`settings.json` / runtime settings 新增：

- `group_id`
- `username`

保留讀取舊 `nickname` 的相容邏輯，但新的 submission 一律使用 `username`。

### Mock Data Tool

新增 mock data CLI，讓後端可以直接產生測試資料。

預設行為：

- 預設產生 10 筆 submissions。
- 可指定產生數量。
- 可指定 phase。
- 可指定資料狀態：`pending` 或 `evaluated`。
- 直接寫入 competition DB，不需要 server 已啟動。

用途：

- 測試 60 秒批次評分。
- 測試 leaderboard top30。
- 測試 replay top10。
- 測試 personal/group identity 取最高分。
- 測試 WebSocket 更新流程。

## Replay 與 WebSocket 行為

完整資料流：

```text
Frontend submits weights/biases
        ↓
POST /api/submissions
        ↓
DB stores pending submission with active phase
        ↓
Evaluation worker runs every 60 seconds
        ↓
Each pending submission is simulated for up to 30 seconds
        ↓
Checkpoint progress becomes score_laps
        ↓
Leaderboard top30 and replay top10 are updated
        ↓
Server pushes /ws/events competition_updated
        ↓
Leaderboard redraws immediately
        ↓
replay.py stores new top10 and applies it next round
```

Replay 行為：

- 每輪最多 30 秒。
- 若全部車輛提前撞車，該輪提前結束。
- 播放中收到新的 top10 不立即切換。
- 下一輪開始時使用最新 top10。

Leaderboard 行為：

- 顯示 active phase top30。
- 只顯示 evaluated submissions。
- 收到 WebSocket event 後立即更新。
- 若 WebSocket 斷線，可用 HTTP API 重新抓取目前 leaderboard。

## Test Plan

### API Tests

- 新 submission 格式成功建立 pending submission。
- 成功 response 包含 `submission_id`、`status`、`phase`。
- 舊 submission 格式被拒絕。
- invalid `weights` shape 回 400。
- invalid `biases` shape 回 400。
- `GET /api/submissions` 未帶 admin token 被拒絕。
- `GET /api/submissions/{submission_id}` 未帶 admin token 被拒絕。
- `/api/replay/top` 可公開取得 top10 replay payload。

### Evaluation Tests

- worker 每 60 秒批次處理 pending submissions。
- 同一批中的每筆 pending submission 都會評分。
- checkpoint scorer 可以產生小數 `score_laps`。
- 車輛撞車時，以撞車當下 checkpoint 進度計分。
- 車輛 30 秒後仍 running 時，以 30 秒當下位置計分。
- 同一 `username` 在 personal phase 只保留最高分。
- 同一 `group_id` 在 group phase 只保留最高分。
- 同分時先提交者排序較前。

### Phase/Admin Tests

- personal 與 group 結果分開保存。
- 切 active phase 不刪除另一 phase 資料。
- 切 active phase 不重新評分。
- reset 只清除目前 active phase。
- 同一 phase 內換地圖會重跑該 phase 每個 identity 的最佳 submission。
- 換地圖後 leaderboard/replay 會更新為新地圖分數。

### Replay/WebSocket Tests

- 批次評分完成後推送一次 `competition_updated` event。
- WebSocket event 包含完整 leaderboard top30。
- WebSocket event 包含完整 replay top10。
- leaderboard 頁收到 event 後重畫。
- `replay.py` 播放中收到 event 不打斷目前動畫。
- `replay.py` 下一輪套用最新 top10。
- replay 單輪最多 30 秒。
- replay 全部車輛撞車時提前結束。

### Mock Data Tests

- mock CLI 預設產生 10 筆 submissions。
- mock CLI 可指定產生數量。
- mock CLI 可產生 `pending` submissions。
- mock CLI 可產生 `evaluated` submissions。
- mock CLI 產生的資料可出現在 leaderboard/replay。
- mock CLI 可產生 personal/group phase 測試資料。

## Assumptions

- 神經網路結構固定為 `[6, 6, 4]`。
- `weights` 固定為 `[[36 floats], [24 floats]]`。
- `biases` 固定為 `[[6 floats], [4 floats]]`。
- `score_laps` 是唯一正式排名分數。
- personal phase 使用 `username` 排名。
- group phase 使用 `group_id` 排名。
- group phase 顯示最佳 submission 對應的 `username`。
- 五張官方地圖全部重新產生。
- 五張官方地圖都必須有 checkpoint metadata。
- 舊 `competition.db` 可清空重建，不需要 migration。
- `/api/replay/top` 公開回傳 top10 的 weights/biases。
- submission debug endpoints 需要 admin token。
- Admin reset 只清目前 active phase。
- WebSocket 推送完整 leaderboard top30 與 replay top10。
