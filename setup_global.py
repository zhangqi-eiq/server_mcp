"""Deploy the GUI manager (SSH-Server-Manager.exe) to a user-level directory on PATH.

This is an **optional** follow-up to ``install.py``. After running it you can
launch the GUI from any shell via ``SSH-Server-Manager`` without a full
PyInstaller rebuild.

Prerequisites::

    pip install -e ".[gui]"   # installs pyinstaller
    python build.py           # builds dist/SSH-Server-Manager.exe
    python setup_global.py    # copies it to ~/.ssh-mcp-server and adds to PATH

Run ``python setup_global.py --uninstall`` to remove.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

SERVER_DIR = Path(__file__).parent.resolve()
GLOBAL_DIR = Path.home() / ".ssh-mcp-server"
SRC_EXE = SERVER_DIR / "dist" / ("SSH-Server-Manager.exe" if platform.system() == "Windows"
                                 else "SSH-Server-Manager")


def _print(msg: str) -> None:
    print(msg)


def _add_to_path(directory: Path) -> bool:
    """Add ``directory`` to the user PATH on Windows. No-op on other OSes."""
    if platform.system() != "Windows":
        _print(f"[skip] PATH update only supported on Windows (current: {platform.system()})")
        return False

    ps_get = "[Environment]::GetEnvironmentVariable('Path','User')"
    cmd = ["powershell", "-NoProfile", "-Command", ps_get]
    current = subprocess.run(cmd, capture_output=True, text=True).stdout.strip()

    if str(directory) in current.split(";"):
        _print(f"[skip] {directory} already on user PATH")
        return False

    new_path = current.rstrip(";") + ";" + str(directory)
    cmd = ["powershell", "-NoProfile", "-Command",
           f"[Environment]::SetEnvironmentVariable('Path','{new_path}','User')"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        _print(f"[error] failed to update PATH: {result.stderr.strip()}")
        return False
    _print(f"[ok] added to user PATH: {directory}")
    return True


def deploy() -> None:
    _print("=" * 60)
    _print(" SSH-Server-Manager — global GUI deployment")
    _print("=" * 60)

    if not SRC_EXE.exists():
        _print(f"[error] build artifact missing: {SRC_EXE}")
        _print("        run `python build.py` first")
        sys.exit(1)

    GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    dst = GLOBAL_DIR / SRC_EXE.name
    shutil.copy2(SRC_EXE, dst)
    _print(f"[ok] deployed → {dst}")

    _add_to_path(GLOBAL_DIR)

    _print("")
    _print("Done. Open a new terminal so the updated PATH takes effect, then run:")
    _print(f"    {SRC_EXE.stem}")


def uninstall() -> None:
    _print("Removing GUI deployment...")
    target = GLOBAL_DIR / SRC_EXE.name
    if target.exists():
        target.unlink()
        _print(f"[ok] removed {target}")
    if GLOBAL_DIR.exists() and not any(GLOBAL_DIR.iterdir()):
        GLOBAL_DIR.rmdir()
        _print(f"[ok] removed empty {GLOBAL_DIR}")
    _print("Note: user PATH entry not auto-removed. Edit via:")
    _print("  System Properties → Environment Variables → User PATH")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--uninstall", action="store_true",
                        help="Remove the GUI deployment")
    args = parser.parse_args()

    if args.uninstall:
        uninstall()
    else:
        deploy()


if __name__ == "__main__":
    main()
