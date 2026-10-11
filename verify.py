"""Run the suite and preserve a clean, machine-checkable verification record."""
import io
import json
from pathlib import Path
import platform
import sys
import unittest

stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(".", pattern="test_quality_lab.py")
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
output = stream.getvalue()
Path("test-results.txt").write_text(output, encoding="utf-8")
Path("verification.json").write_text(json.dumps({
    "python": platform.python_version(), "tests_run": result.testsRun,
    "failures": len(result.failures), "errors": len(result.errors),
    "skipped": len(result.skipped), "passed": result.wasSuccessful(),
    "date": "2026-10-11"
}, indent=2) + "\n", encoding="utf-8")
print(output, end="")
sys.exit(0 if result.wasSuccessful() else 1)
