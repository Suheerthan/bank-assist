import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    path = os.getenv("PW_CHROMIUM_PATH")  # only needed if Playwright's own browser is not installed
    return {**browser_type_launch_args, **({"executable_path": path} if path else {})}


@pytest.fixture(scope="session")
def server_url(tmp_path_factory):
    port = 8765
    env = {**os.environ, "LLM_PROVIDER": "none", "MONGO_URI": "mongodb://localhost:1",
           "LOCAL_STORE_PATH": str(tmp_path_factory.mktemp("store") / "store.json")}
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            socket.create_connection(("127.0.0.1", port), timeout=0.2).close()
            break
        except OSError:
            time.sleep(0.25)
    yield f"http://127.0.0.1:{port}"
    proc.terminate()
