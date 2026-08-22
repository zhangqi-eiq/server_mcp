"""打包 server_manager.py 为独立可执行文件"""

import os
import subprocess
import sys

# 以脚本所在目录作为工作目录,避免路径写死导致在不同机器上失败
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

cmd = [
    sys.executable, "-m", "PyInstaller",
    "--noconfirm",
    "--onefile",           # 单文件
    "--windowed",          # 无控制台窗口
    "--name", "SSH-Server-Manager",
    "--distpath", "dist",
    "--workpath", "build",
    "--specpath", ".",
    "server_manager.py",
]

print("正在打包...")
print(" ".join(cmd))
result = subprocess.run(cmd, cwd=BASE_DIR)

if result.returncode == 0:
    print("\n打包成功!")
    print(f"可执行文件: {os.path.join(BASE_DIR, 'dist', 'SSH-Server-Manager.exe')}")
    print("\n注意: profiles.json 和 config.json 需要与 exe 放在同一目录")
else:
    print("\n打包失败，请检查错误信息")
    sys.exit(1)
