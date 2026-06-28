# 教室內網 Competition Server 部署與測試文件

## 目標

正式活動時，建議使用一台老師或助教電腦作為唯一 competition server。學生電腦只要在同一個 subnet 內能連到這台主機，就可以提交、查看 leaderboard。大螢幕 replay 可以跑在 server 主機，也可以跑在另一台同 subnet 電腦，只要能連到 server IP 並持有 replay/admin token。

目前 `uv run python -m server.app` 預設只綁定 `127.0.0.1:8000`，只能本機連線。教室部署時請使用 `uvicorn` 並綁定 `0.0.0.0`：

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

## 教室正式部署流程

### 1. 選一台 Server 主機

建議使用老師或助教電腦作為唯一 competition server：

- 這台電腦負責跑 FastAPI server、SQLite DB、batch worker。
- 學生端只需要設定 server URL，例如 `http://192.168.1.23:8000`。
- Leaderboard、admin、submission API、replay feed 都從同一台主機提供。
- 不建議每組自架 server，否則 leaderboard 與 submission 狀態會分散。

### 2. Server 主機準備

在 server 主機上：

```bash
git clone https://github.com/NCTU-CS-Camp/Neural-Network-Cars.git
cd Neural-Network-Cars
uv python install 3.12
uv sync
```

設定正式 admin token：

```bash
export COMPETITION_ADMIN_TOKEN="換成正式活動用的長 token"
```

啟動 server：

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` 是關鍵。若綁定 `127.0.0.1`，學生電腦就算在同一個 subnet 也連不進來。

### 3. 查 Server 主機內網 IP

macOS：

```bash
ipconfig getifaddr en0
```

如果是有線網路，可能是：

```bash
ipconfig getifaddr en1
```

Windows：

```powershell
ipconfig
```

找 IPv4，例如：

```text
192.168.1.23
```

Linux：

```bash
ip addr
```

假設查到 IP 是 `192.168.1.23`，正式 server URL 就是：

```text
http://192.168.1.23:8000
```

### 4. 從學生電腦測試連線

學生電腦先 ping server：

```bash
ping 192.168.1.23
```

再測 health endpoint：

```bash
curl http://192.168.1.23:8000/health
```

預期：

```json
{"status":"ok"}
```

瀏覽器測試：

```text
http://192.168.1.23:8000/leaderboard
http://192.168.1.23:8000/admin
```

Admin 頁需要輸入 `COMPETITION_ADMIN_TOKEN`。

### 5. 學生端設定

如果學生使用 partner frontend 或 `competition_main.py`，server URL 必須填：

```text
http://192.168.1.23:8000
```

本 repo 的 test client 可用：

```bash
COMPETITION_SERVER_URL=http://192.168.1.23:8000 uv run python competition_main.py
```

Phase 1 Easy/Hard queued submissions 要等目前 Admin 設定的 `Phase 1 interval` batch boundary，或由 admin 按 `Create Demo Snapshot` 立即封存。Interval 可設為 1、2、5 分鐘，預設 1 分鐘；正式活動建議不要頻繁按 demo snapshot，除非要展示或排除問題。

### 6. Replay 電腦設定

Replay 如果跑在 server 主機：

```bash
COMPETITION_SERVER_URL=http://127.0.0.1:8000 \
COMPETITION_REPLAY_TOKEN="正式 admin token" \
uv run python replay.py
```

Replay 如果跑在另一台同 subnet 電腦：

```bash
COMPETITION_SERVER_URL=http://192.168.1.23:8000 \
COMPETITION_REPLAY_TOKEN="正式 admin token" \
uv run python replay.py
```

Replay 會讀取 protected model payload，所以必須有 token。不要把 replay/admin token 給學生。

## 防火牆與網路檢查

如果學生可以 ping，但連不上 `http://server-ip:8000/health`：

- 確認 server 是用 `--host 0.0.0.0` 啟動，不是 `127.0.0.1`。
- 確認 macOS / Windows 防火牆允許 Python 或 port `8000` inbound。
- 確認學生與 server 主機在同一 subnet，例如都是 `192.168.1.x`。
- 確認沒有 VPN、校園網路隔離、Guest Wi-Fi client isolation。
- 換 port 測試，例如 `8010`。

```bash
uv run uvicorn server.app:app --host 0.0.0.0 --port 8010
```

學生端同步改成：

```text
http://192.168.1.23:8010
```

常用檢查：

```bash
curl http://192.168.1.23:8000/v2/state
curl http://192.168.1.23:8000/v2/maps
curl http://192.168.1.23:8000/v2/competitions/easy/leaderboard
```

## 本機 VM 測試方案

### 目標

在正式進教室前，用一台電腦開兩台 VM 模擬：

- VM A：server 主機
- VM B：學生 client
- 兩台 VM 必須在同一個虛擬網路內，可以互 ping

### 推薦網路模式

VM 網路請使用 Bridged Adapter 或 Host-only Network：

- Bridged：最像教室網路，VM 會拿到跟主機同網段 IP。
- Host-only：只在本機和 VM 間互通，適合離線測試。
- NAT 通常不適合測「學生連 server」，除非額外做 port forwarding。

### VM A：啟動 Server

```bash
cd Neural-Network-Cars
uv sync
export COMPETITION_ADMIN_TOKEN="test-admin"
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

查 VM A IP：

```bash
ip addr
```

假設是：

```text
192.168.56.10
```

### VM B：模擬學生端

測試 ping：

```bash
ping 192.168.56.10
```

測試 API：

```bash
curl http://192.168.56.10:8000/health
curl http://192.168.56.10:8000/v2/state
```

啟動測試 client：

```bash
COMPETITION_SERVER_URL=http://192.168.56.10:8000 uv run python competition_main.py
```

在 UI 內輸入任意 `User ID`、`Group ID`，切 Easy/Hard，按 `V` 產生 `client_result`，按 `U` 檢查 eligibility 並提交。

### VM B：測試 Leaderboard

瀏覽器開：

```text
http://192.168.56.10:8000/leaderboard
```

如果 submission 還沒出現在 Easy/Hard leaderboard，這是正常的，因為 Phase 1 需要 batch sealing。可以在 VM A 或 admin 頁呼叫 demo snapshot。

### VM A：手動建立 Snapshot

用 admin endpoint：

```bash
curl -X POST http://127.0.0.1:8000/v2/admin/batches/run-now \
  -H "X-Admin-Token: test-admin"
```

或瀏覽器開：

```text
http://192.168.56.10:8000/admin
```

輸入 `test-admin`，按 `Create Demo Snapshot`。

### Replay 測試

Replay 可跑在 VM A、VM B 或 host machine，只要能連到 VM A server。

```bash
COMPETITION_SERVER_URL=http://192.168.56.10:8000 \
COMPETITION_REPLAY_TOKEN=test-admin \
uv run python replay.py
```

## 正式活動建議 SOP

活動前一天：

- 在教室網路實測 server 主機 IP。
- 測至少兩台學生電腦能 ping server。
- 測 `/health`、`/leaderboard`、`/admin`。
- 用 `competition_main.py` 做一筆 Easy 和 Hard submission。
- 確認 snapshot 後 leaderboard 更新。
- 確認 replay 能讀到 Top 15 payload。
- 設定正式 `COMPETITION_ADMIN_TOKEN`，不要使用預設 `admin`。
- 備份或清空 `server/competition.db`，依比賽需求決定是否 reset。

活動當天：

1. Server 主機接上穩定網路與電源。
2. 啟動：

```bash
export COMPETITION_ADMIN_TOKEN="正式 token"
uv run uvicorn server.app:app --host 0.0.0.0 --port 8000
```

3. 將 server URL 公告給學生：

```text
http://<server-ip>:8000
```

4. Admin 開 `http://<server-ip>:8000/admin`。
5. Leaderboard 開 `http://<server-ip>:8000/leaderboard`。
6. Replay 開：

```bash
COMPETITION_SERVER_URL=http://<server-ip>:8000 \
COMPETITION_REPLAY_TOKEN="正式 token" \
uv run python replay.py
```

7. Phase 1 使用 `phase_one` stage。
8. Final 前由 admin 切到 `final` stage。
9. 比賽結束後備份 `server/competition.db`。

## 重要限制與後續改善

- 目前 `uv run python -m server.app` 預設綁 `127.0.0.1`，教室部署要用 `uvicorn ... --host 0.0.0.0`。
- SQLite 適合教室單機活動；如果未來有大量併發或長期服務，應改成 PostgreSQL。
- Admin/replay token 目前是單一 shared token；正式活動至少要用強 token，並限制只給助教。
- Server ranking 信任 client 上傳的 `client_result`；正式學生 client 必須和 server/replay 使用同一份 competition map 與 `*_back.png` collision 規則。
- 如果學校網路有 client isolation，即使同 subnet 也可能不能互連，需要請網管關閉隔離或改用有線/指定教室網路。
- 建議後續新增 `COMPETITION_HOST` / `COMPETITION_PORT` 環境變數支援，讓啟動指令更不容易出錯。
