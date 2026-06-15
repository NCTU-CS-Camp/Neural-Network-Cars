import sys
from pathlib import Path

# Make the project root importable (GA, game_engine, shared) when pytest is
# invoked from anywhere.
sys.path.insert(0, str(Path(__file__).parent))
