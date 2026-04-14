"""Pytest conftest — adds paths for imports."""
import sys, os

# Add parent dir (Fractal Sweep/) for model_stats import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
# Add tests dir for helpers import
sys.path.insert(0, os.path.dirname(__file__))
