"""Install the locked local development wheel and print its reusable interpreter.

Run from any directory: python PATH/scripts/bootstrap.py --uv PATH/uv.exe
This script makes no provider requests and does not read environment files.
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", default=shutil.which("uv"))
    parser.add_argument("--python", default="3.12.13")
    args = parser.parse_args()
    if not args.uv:
        parser.error("uv is required; install it separately or pass --uv PATH")
    root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["UV_PYTHON_INSTALL_DIR"] = str(root / ".agent-work" / "python")
    env["UV_PYTHON_BIN_DIR"] = str(root / ".agent-work" / "python-bin")
    env["UV_NO_CONFIG"] = "1"
    subprocess.run(
        [
            args.uv,
            "sync",
            "--project",
            str(root),
            "--locked",
            "--extra",
            "dev",
            "--no-editable",
            "--python",
            args.python,
        ],
        env=env,
        check=True,
    )
    subprocess.run(
        [args.uv, "build", "--project", str(root), "--wheel", "--out-dir", str(root / "dist")],
        env=env,
        check=True,
    )
    interpreter = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    subprocess.run([str(interpreter), "-I", "-m", "mcpsh.cli", "--help"], check=True)
    print(
        json.dumps(
            {
                "interpreter": str(interpreter),
                "project": str(root),
                "install": "locked non-editable wheel",
                "live_calls": "not_run",
            }
        )
    )


if __name__ == "__main__":
    main()
