# Competition API Spec

## Submission

### `POST /api/submissions`

建立一筆 submission。Submission 會歸屬到當下 active phase。

Request:

```json
{
  "group_id": "1",
  "username": "player1",
  "weights": [[0.0], [0.0]],
  "biases": [[0.0], [0.0]]
}
```

Shape:

- `weights[0]`: 36 floats
- `weights[1]`: 24 floats
- `biases[0]`: 6 floats
- `biases[1]`: 4 floats

Response:

```json
{
  "submission_id": "sub_xxxxxxxx",
  "status": "pending",
  "phase": "personal"
}
```

舊欄位如 `model_version`、`layer_sizes`、`fitness_score`、`nickname` 不再接受。

## Public Read APIs

### `GET /api/state`

回傳目前 active phase 與各 phase 使用的 map。

### `GET /api/maps`

回傳可選官方地圖 metadata。

### `GET /api/leaderboard`

回傳 active phase top30。只包含 evaluated submissions。

### `GET /api/replay/top?n=10`

回傳 active phase topN replay payload。此 endpoint 公開，包含 weights/biases。

## Admin APIs

Admin endpoints 需要 header：

```text
X-Admin-Token: admin
```

### `GET /api/submissions`

列出 submissions，包含 debug 欄位與模型 payload。

### `GET /api/submissions/{submission_id}`

查詢單筆 submission。

### `POST /api/admin/phase`

Request:

```json
{ "phase": "personal" }
```

切換 active phase，不刪除另一 phase 資料，也不重新評分。

### `POST /api/admin/map`

Request:

```json
{
  "phase": "personal",
  "map_id": "official_001"
}
```

設定該 phase 使用的官方地圖，並立即重跑該 phase 每個 identity 的目前最佳 submission。

### `POST /api/admin/reset`

清除目前 active phase 的 submissions/results。

### `POST /api/admin/process-pending`

立即處理目前所有 pending submissions，方便現場測試。

## WebSocket

### `GET /ws/events`

Server 會在批次評分完成、phase 切換、地圖切換、reset 後推送：

```json
{
  "type": "competition_updated",
  "phase": "personal",
  "map": {},
  "updated_at": "2026-06-20T00:00:00+00:00",
  "leaderboard": [],
  "replay_top": []
}
```

`leaderboard` 固定為 top30，`replay_top` 固定為 top10。
