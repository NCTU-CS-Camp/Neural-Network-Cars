# Ubuntu client 打包與發佈

此流程只封裝 Pygame client，不包含 FastAPI server 或 SQLite database。玩家的
client 會連線到既有的中央 competition server。

client 的 server URL 固定為：

```text
http://192.168.15.1:8000
```

## 從 GitHub Actions 手動打包

1. 將打包相關修改 commit 並 push／merge 到 GitHub 的預設 branch。
2. 開啟 <https://github.com/NCTU-CS-Camp/Neural-Network-Cars/actions>。
3. 左側選擇 `Build Ubuntu client`。
4. 點 `Run workflow`。
5. 選擇 branch，再按綠色 `Run workflow`。
6. 完成後點進該次執行，在頁面下方 `Artifacts` 下載
   `NeuralNetworkCars-Ubuntu-x86_64`。

Artifact 裡的交付檔是：

```text
NeuralNetworkCars-Ubuntu-x86_64.tar.gz
```

GitHub runner 使用 Ubuntu 22.04 建置，以便產物也能在較新的 Ubuntu desktop
版本執行。

## 玩家啟動方式

```bash
tar -xzf NeuralNetworkCars-Ubuntu-x86_64.tar.gz
cd NeuralNetworkCars-Ubuntu-x86_64
./NeuralNetworkCars
```

若執行權限在傳輸過程中遺失：

```bash
chmod +x NeuralNetworkCars
./NeuralNetworkCars
```

玩家的設定與訓練資料位於：

```text
~/.local/share/NeuralNetworkCars
```

打包後的 client 會固定使用 `http://192.168.15.1:8000`。即使玩家保留舊版的
`~/.local/share/NeuralNetworkCars/settings.json`，其中的 `server_url` 也不會覆蓋
這個固定網址；其他玩家設定仍會照常保留。

## 正式 Release

建立 tag 即可觸發正式 Release：

```bash
git tag v0.1.0
git push origin v0.1.0
```

workflow 會建立或更新 GitHub Release，並附上 Ubuntu client 的 `.tar.gz`。

## Ubuntu 本機打包

```bash
./scripts/build_ubuntu.sh
```

產物位於 `dist/`。若已另外跑過測試：

```bash
SKIP_TESTS=1 ./scripts/build_ubuntu.sh
```

PyInstaller 產物與建置作業系統及 CPU 架構綁定；此流程產生 Ubuntu x86_64
執行檔，不是 Windows `.exe`。
