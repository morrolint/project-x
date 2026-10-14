#!/usr/bin/env python3
"""测试入口：python3 assistant/tests/run.py [-v]"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agent"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    verbose = "-v" in sys.argv
    suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parent), pattern="test_*.py")
    result = unittest.TextTestRunner(verbosity=2 if verbose else 1).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
