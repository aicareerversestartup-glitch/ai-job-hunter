import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Isolate every test run from the real data folder and database.
_tmp = tempfile.mkdtemp(prefix="aijh-test-")
os.environ.setdefault("DATA_DIR", _tmp)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(_tmp, 'test.db').as_posix()}")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-for-hs256")
os.environ.setdefault("RUN_SCHEDULER", "false")
os.environ.setdefault("AI_PROVIDER", "none")

SAMPLE_CV = (ROOT / "data/samples/sample_master_cv.txt").read_text(encoding="utf-8")
SAMPLE_JOB = (ROOT / "data/samples/sample_job.txt").read_text(encoding="utf-8")
