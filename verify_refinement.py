"""Verify original and refined suites; retain the original verification record."""
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest

started = time.perf_counter()
stream = io.StringIO()
suite = unittest.defaultTestLoader.discover(".", pattern="test*.py")
result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
elapsed = time.perf_counter() - started
Path("test-results-v2.txt").write_text(stream.getvalue(), encoding="utf-8")
source_names = ["quality_lab.py", "refinement.py", "test_quality_lab.py",
                "test_refinement.py", "verify.py", "verify_refinement.py",
                "CUSTOMER-SPEC.md", "PROCESS-MAP.md", "REFINEMENT-PLAN.md", "REQUIREMENTS.md"]
Path("verification-v2.json").write_text(json.dumps({
    "python": platform.python_version(), "tests_run": result.testsRun,
    "failures": len(result.failures), "errors": len(result.errors),
    "skipped": len(result.skipped), "passed": result.wasSuccessful(),
    "elapsed_seconds": round(elapsed, 3), "date": "2026-10-11",
    "sha256": {name: hashlib.sha256(Path(name).read_bytes()).hexdigest() for name in source_names}
}, indent=2) + "\n", encoding="utf-8")
print(stream.getvalue(), end="")
sys.exit(0 if result.wasSuccessful() else 1)
