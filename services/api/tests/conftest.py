import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="dhwani-test-"))
os.environ.update({
    "APP_ENV": "test",
    "DATABASE_URL": f"sqlite:///{(_tmp / 'test.db').as_posix()}",
    "BLOB_DIR": str(_tmp / "blobs"),
    "LLM_MODE": "offline",
    "SPEECH_BACKEND": "simulated",
    "ALLOW_SIMULATED_AUDIO": "true",
})
