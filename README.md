# Environment Setup

## 已安裝 uv

```bash
git clone https://github.com/NCTU-CS-Camp/Neural-Network-Cars.git
cd Neural-Network-Cars
uv python install 3.12
uv sync
uv run python nnCarGame.py
```

## 尚未安裝 uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc

git clone https://github.com/NCTU-CS-Camp/Neural-Network-Cars.git
cd Neural-Network-Cars

uv python install 3.12
uv sync
uv run python nnCarGame.py
```
