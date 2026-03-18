import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WD = Path(__file__).resolve().parents[1] / "scripts" / "run_with_watchdog.py"
HB = HERE / "fixtures" / "heartbeat_script.py"


def run_watchdog(cmd, timeout=0, idle=0):
    args = [sys.executable, str(WD), "--cmd", cmd]
    if timeout:
        args += ["--timeout", str(timeout)]
    if idle:
        args += ["--idle", str(idle)]
    p = subprocess.run(args)
    return p.returncode


def test_watchdog_allows_active():
    cmd = f"{sys.executable} {HB} --period 0.1 --n 5"
    rc = run_watchdog(cmd, timeout=10, idle=1)
    assert rc == 0


def test_watchdog_kills_on_idle():
    # use a python -c that prints then sleeps -> idle timeout should kill
    cmd = f"{sys.executable} -c \"import time; print('hi'); time.sleep(5)\""
    rc = run_watchdog(cmd, timeout=10, idle=1)
    assert rc == 125
