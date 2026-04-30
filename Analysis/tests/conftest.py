"""Pytest conftest — adds engine dir to sys.path."""
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'engine'))
sys.path.insert(0, os.path.dirname(__file__))
