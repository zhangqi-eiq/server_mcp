"""打包 server_manager.py 为独立可执行文件"""

import os
import subprocess
import sys
from pathlib import Path

# 以脚本所在目录作为工作目录,避免路径写死导致在不同机器上失败
BASE_DIR = Path(__file__).parent.resolve()

# Detect Tcl/Tk runtime DLLs. Standard CPython ships them next to python.exe;
# conda puts them in <env>/DLLs/. Either way, they live next to the interpreter.
_PYTHON_DIR = Path(sys.executable).parent
_CANDIDATE_DIRS = [_PYTHON_DIR, _PYTHON_DIR / "DLLs", _PYTHON_DIR / "Library" / "bin"]

def _find_runtime_dll(name: str) -> Path | None:
    """Locate a Tcl/Tk runtime DLL alongside the active interpreter."""
    for d in _CANDIDATE_DIRS:
        candidate = d / name
        if candidate.is_file():
            return candidate
    return None


_TCL_DLL = _find_runtime_dll("tcl86t.dll")
_TK_DLL = _find_runtime_dll("tk86t.dll")
# Some Python builds name the Tk DLL tk86t.dll, others use tk86t.dll or tk86.dll.
if _TK_DLL is None:
    _TK_DLL = _find_runtime_dll("tk86.dll")

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",           # 单文件
    "--windowed",          # 无控制台窗口
    "--name", "SSH-Server-Manager",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", ".",
    # Tcl/Tk DLLs (tcl86t.dll, tk86t.dll, etc.) live in <env>/DLLs/ in
    # conda distributions. PyInstaller's default tkinter hook does not
    # always pick them up, causing "DLL load failed while importing
    # _tkinter" at runtime. Force-bundle the entire tkinter package and
    # explicitly add the runtime DLLs from the active interpreter.
    "--collect-all", "tkinter",
    "--collect-all", "_tkinter",
]

if _TCL_DLL is None or _TK_DLL is None:
    print("[warn] Could not locate Tcl/Tk DLLs next to the Python interpreter.")
    print(f"       Searched: {[str(d) for d in _CANDIDATE_DIRS]}")
    print("       The resulting exe may fail with 'DLL load failed' on launch.")
else:
    print(f"[info] Bundling Tcl runtime: {_TCL_DLL}")
    print(f"[info] Bundling Tk  runtime: {_TK_DLL}")
    cmd += ["--add-binary", f"{_TCL_DLL};."]
    cmd += ["--add-binary", f"{_TK_DLL};."]

cmd.append("server_manager.py")

print("正在打包...")
print(" ".join(cmd))
result = subprocess.run(cmd, cwd=BASE_DIR)

if result.returncode == 0:
    print("\n打包成功!")
    print(f"可执行文件: {os.path.join(BASE_DIR, 'dist', 'SSH-Server-Manager.exe')}")
    print("\n部署提示:")
    print("  - profiles.json 默认从 ~/.ssh-mcp-server/ 读取（便携模式除外）")
    print("  - 把 exe 放到任意目录双击运行即可")
else:
    print("\n打包失败，请检查错误信息")
    sys.exit(1)
