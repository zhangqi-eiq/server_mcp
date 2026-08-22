"""SSH Server Manager - 可视化管理多个远程服务器配置"""

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

# ── 路径常量 ──────────────────────────────────────────────────────────

# PyInstaller 打包后，配置文件应与 exe 同目录
if getattr(sys, 'frozen', False):
    _LOCAL_DIR = Path(sys.executable).parent
else:
    _LOCAL_DIR = Path(__file__).parent

_GLOBAL_DIR = Path.home() / ".ssh-mcp-server"


def _find_file(filename: str) -> Path:
    """按优先级查找配置文件：本地目录 > 全局目录"""
    local = _LOCAL_DIR / filename
    if local.exists():
        return local
    global_path = _GLOBAL_DIR / filename
    if global_path.exists():
        return global_path
    # 都不存在时，默认保存到全局目录
    _GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    return global_path


PROFILES_PATH = _find_file("profiles.json")
CONFIG_PATH = _find_file("config.json")

# ── 默认模板 ──────────────────────────────────────────────────────────

DEFAULT_PROFILE = {
    "ssh": {
        "host": "",
        "port": 22,
        "username": "",
        "auth": {
            "type": "key",
            "key_path": "~/.ssh/id_rsa",
            "password": "",
            "key_password": "",
        },
        "connect_timeout": 10,
        "keepalive_interval": 30,
    },
    "allowed_paths": [],
    "security": {
        "blocked_commands": [
            "rm -rf /", "rm -rf /*", "mkfs", "dd if=", "format",
            "shutdown", "reboot", "halt", "poweroff", "init 0", "init 6",
            ":(){:|:&};:", "chmod -R 777 /", "chown -R",
            "> /dev/sd", "echo > /dev/sd",
        ],
        "max_file_size_mb": 50,
        "max_output_chars": 100000,
        "command_timeout": 30,
    },
}

DEFAULT_PROFILES = {
    "active_profile": "",
    "profiles": {},
}


def _deep_copy(d):
    return json.loads(json.dumps(d))


# ── 数据管理 ──────────────────────────────────────────────────────────


def load_profiles() -> dict:
    if PROFILES_PATH.exists():
        with open(PROFILES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return _deep_copy(DEFAULT_PROFILES)


def save_profiles(data: dict):
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def write_config(profile_data: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2, ensure_ascii=False)


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── GUI ───────────────────────────────────────────────────────────────


class ServerManagerApp:
    # 字体定义（统一管理，方便调整）
    FONT_LABEL = ("Microsoft YaHei UI", 18)
    FONT_ENTRY = ("Microsoft YaHei UI", 18)
    FONT_HEADER = ("Microsoft YaHei UI", 20, "bold")
    FONT_LISTBOX = ("Microsoft YaHei UI", 18)
    FONT_PATHS = ("Consolas", 16)
    FONT_BUTTON = ("Microsoft YaHei UI", 14)
    FONT_STATUS = ("Microsoft YaHei UI", 14)

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SSH Server Manager - 服务器管理器")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 750)

        self.data = load_profiles()
        self.current_name = None  # 当前编辑的 profile 名称
        self._modified = False

        self._build_ui()
        self._refresh_list()

        # 如果有 active profile，选中它
        active = self.data.get("active_profile", "")
        if active and active in self.data.get("profiles", {}):
            self._select_profile(active)

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI 构建 ───────────────────────────────────────────────────────

    def _build_ui(self):
        # 主分割
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # ── 左侧：服务器列表 ──
        left = ttk.LabelFrame(main_frame, text="服务器列表", padding=8)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))

        self.listbox = tk.Listbox(left, width=24, font=self.FONT_LISTBOX)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_frame, text="添加", width=8, command=self._add_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", width=8, command=self._delete_profile).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="复制", width=8, command=self._copy_profile).pack(side=tk.LEFT, padx=2)

        # ── 右侧：编辑区域（可滚动） ──
        right = ttk.LabelFrame(main_frame, text="配置详情", padding=8)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(right, highlightthickness=0)
        scrollbar = ttk.Scrollbar(right, orient=tk.VERTICAL, command=canvas.yview)
        self.edit_frame = ttk.Frame(canvas)

        self.edit_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._canvas_win = canvas.create_window((0, 0), window=self.edit_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 让内框宽度跟随 canvas 宽度
        def _on_canvas_resize(event):
            canvas.itemconfig(self._canvas_win, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 绑定鼠标滚轮
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        self._build_form()

        # ── 底部按钮 ──
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(fill=tk.X)

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(bottom, textvariable=self.status_var, font=self.FONT_STATUS).pack(side=tk.LEFT)

        ttk.Button(bottom, text="测试连接", command=self._test_connection).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="切换到选中服务器", command=self._switch_active).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bottom, text="保存配置", command=self._save_current).pack(side=tk.RIGHT, padx=4)

    def _build_form(self):
        """构建编辑表单"""
        f = self.edit_frame
        for widget in f.winfo_children():
            widget.destroy()

        row = 0
        LBL = self.FONT_LABEL
        ENT = self.FONT_ENTRY
        HDR = self.FONT_HEADER
        PAD_Y = 6  # 行间距

        # ── 基本信息 ──
        ttk.Label(f, text="── 基本信息 ──", font=HDR).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, PAD_Y)
        )
        row += 1

        ttk.Label(f, text="名称:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_name = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_name, font=ENT).grid(row=row, column=1, columnspan=2, sticky="we", pady=PAD_Y)
        row += 1

        ttk.Label(f, text="主机:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_host = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_host, font=ENT).grid(row=row, column=1, columnspan=2, sticky="we", pady=PAD_Y)
        row += 1

        ttk.Label(f, text="端口:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_port = tk.StringVar(value="22")
        ttk.Entry(f, textvariable=self.var_port, font=ENT, width=10).grid(row=row, column=1, sticky="w", pady=PAD_Y)
        row += 1

        ttk.Label(f, text="用户名:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_user = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_user, font=ENT).grid(row=row, column=1, columnspan=2, sticky="we", pady=PAD_Y)
        row += 1

        # ── 认证 ──
        ttk.Label(f, text="── 认证方式 ──", font=HDR).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(12, PAD_Y)
        )
        row += 1

        self.var_auth_type = tk.StringVar(value="key")
        auth_frame = ttk.Frame(f)
        auth_frame.grid(row=row, column=0, columnspan=3, sticky="w", padx=4, pady=PAD_Y)
        tk.Radiobutton(auth_frame, text="密钥认证", variable=self.var_auth_type, value="key", font=LBL).pack(side=tk.LEFT)
        tk.Radiobutton(auth_frame, text="密码认证", variable=self.var_auth_type, value="password", font=LBL).pack(side=tk.LEFT, padx=(16, 0))
        row += 1

        ttk.Label(f, text="密钥路径:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_key_path = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_key_path, font=ENT).grid(row=row, column=1, sticky="we", pady=PAD_Y)
        ttk.Button(f, text="浏览", width=6, command=self._browse_key).grid(row=row, column=2, padx=4, pady=PAD_Y)
        row += 1

        ttk.Label(f, text="密码:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_password = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_password, font=ENT, show="*").grid(row=row, column=1, columnspan=2, sticky="we", pady=PAD_Y)
        row += 1

        ttk.Label(f, text="密钥密码:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_key_password = tk.StringVar()
        ttk.Entry(f, textvariable=self.var_key_password, font=ENT, show="*").grid(row=row, column=1, columnspan=2, sticky="we", pady=PAD_Y)
        row += 1

        # ── 允许路径 ──
        ttk.Label(f, text="── 允许访问的远程路径 ──", font=HDR).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(12, PAD_Y)
        )
        row += 1

        self.paths_listbox = tk.Listbox(f, height=4, font=self.FONT_PATHS)
        self.paths_listbox.grid(row=row, column=0, columnspan=2, sticky="we", padx=4, pady=PAD_Y)
        path_btn_frame = ttk.Frame(f)
        path_btn_frame.grid(row=row, column=2, sticky="n", padx=4, pady=PAD_Y)
        ttk.Button(path_btn_frame, text="删除", width=6, command=self._remove_path).pack(pady=1)
        row += 1

        add_path_frame = ttk.Frame(f)
        add_path_frame.grid(row=row, column=0, columnspan=3, sticky="we", padx=4, pady=PAD_Y)
        add_path_frame.columnconfigure(0, weight=1)
        self.var_new_path = tk.StringVar()
        ttk.Entry(add_path_frame, textvariable=self.var_new_path, font=ENT).grid(row=0, column=0, sticky="we")
        ttk.Button(add_path_frame, text="添加路径", width=8, command=self._add_path).grid(row=0, column=1, padx=4)
        row += 1

        # ── 安全设置 ──
        ttk.Label(f, text="── 安全设置 ──", font=HDR).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(12, PAD_Y)
        )
        row += 1

        ttk.Label(f, text="文件大小限制:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_max_size = tk.StringVar(value="50")
        sf = ttk.Frame(f)
        sf.grid(row=row, column=1, columnspan=2, sticky="w", pady=PAD_Y)
        ttk.Entry(sf, textvariable=self.var_max_size, font=ENT, width=8).pack(side=tk.LEFT)
        ttk.Label(sf, text=" MB", font=LBL).pack(side=tk.LEFT)
        row += 1

        ttk.Label(f, text="输出字符限制:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_max_output = tk.StringVar(value="100000")
        ttk.Entry(f, textvariable=self.var_max_output, font=ENT, width=12).grid(row=row, column=1, sticky="w", pady=PAD_Y)
        row += 1

        ttk.Label(f, text="命令超时:", font=LBL).grid(row=row, column=0, sticky="e", padx=4, pady=PAD_Y)
        self.var_timeout = tk.StringVar(value="30")
        tf = ttk.Frame(f)
        tf.grid(row=row, column=1, columnspan=2, sticky="w", pady=PAD_Y)
        ttk.Entry(tf, textvariable=self.var_timeout, font=ENT, width=8).pack(side=tk.LEFT)
        ttk.Label(tf, text=" 秒", font=LBL).pack(side=tk.LEFT)
        row += 1

        # 配置列权重
        f.columnconfigure(1, weight=1)

    # ── 列表操作 ──────────────────────────────────────────────────────

    def _refresh_list(self):
        self.listbox.delete(0, tk.END)
        active = self.data.get("active_profile", "")
        for name in sorted(self.data.get("profiles", {}).keys()):
            prefix = "★ " if name == active else "  "
            self.listbox.insert(tk.END, f"{prefix}{name}")

    def _select_profile(self, name: str):
        profiles = self.data.get("profiles", {})
        if name not in profiles:
            return
        self.current_name = name

        # 高亮列表项
        names = sorted(profiles.keys())
        if name in names:
            idx = names.index(name)
            self.listbox.selection_clear(0, tk.END)
            self.listbox.selection_set(idx)
            self.listbox.see(idx)

        self._load_form(name)

    def _get_selected_name(self) -> str | None:
        sel = self.listbox.curselection()
        if not sel:
            return None
        display = self.listbox.get(sel[0])
        return display.replace("★ ", "").strip()

    def _on_select(self, event):
        name = self._get_selected_name()
        if name and name != self.current_name:
            self._select_profile(name)

    # ── 表单加载/读取 ─────────────────────────────────────────────────

    def _load_form(self, name: str):
        p = self.data["profiles"][name]
        ssh = p.get("ssh", {})
        auth = ssh.get("auth", {})
        sec = p.get("security", {})

        self.var_name.set(name)
        self.var_host.set(ssh.get("host", ""))
        self.var_port.set(str(ssh.get("port", 22)))
        self.var_user.set(ssh.get("username", ""))
        self.var_auth_type.set(auth.get("type", "key"))
        self.var_key_path.set(auth.get("key_path", ""))
        self.var_password.set(auth.get("password", ""))
        self.var_key_password.set(auth.get("key_password", ""))
        self.var_max_size.set(str(sec.get("max_file_size_mb", 50)))
        self.var_max_output.set(str(sec.get("max_output_chars", 100000)))
        self.var_timeout.set(str(sec.get("command_timeout", 30)))

        self.paths_listbox.delete(0, tk.END)
        for pth in p.get("allowed_paths", []):
            self.paths_listbox.insert(tk.END, pth)

        self._modified = False
        self.status_var.set(f"正在编辑: {name}")

    def _read_form(self) -> tuple[str, dict]:
        """从表单读取数据，返回 (name, profile_dict)"""
        name = self.var_name.get().strip()
        if not name:
            raise ValueError("名称不能为空")

        paths = list(self.paths_listbox.get(0, tk.END))

        profile = {
            "ssh": {
                "host": self.var_host.get().strip(),
                "port": int(self.var_port.get() or 22),
                "username": self.var_user.get().strip(),
                "auth": {
                    "type": self.var_auth_type.get(),
                    "key_path": self.var_key_path.get().strip(),
                    "password": self.var_password.get(),
                    "key_password": self.var_key_password.get(),
                },
                "connect_timeout": 10,
                "keepalive_interval": 30,
            },
            "allowed_paths": paths,
            "security": {
                "blocked_commands": DEFAULT_PROFILE["security"]["blocked_commands"],
                "max_file_size_mb": int(self.var_max_size.get() or 50),
                "max_output_chars": int(self.var_max_output.get() or 100000),
                "command_timeout": int(self.var_timeout.get() or 30),
            },
        }
        return name, profile

    # ── 按钮操作 ──────────────────────────────────────────────────────

    def _add_profile(self):
        # 生成唯一名称
        base = "new-server"
        name = base
        profiles = self.data.setdefault("profiles", {})
        i = 1
        while name in profiles:
            name = f"{base}-{i}"
            i += 1

        profiles[name] = _deep_copy(DEFAULT_PROFILE)
        self._refresh_list()
        self._select_profile(name)
        self.status_var.set(f"已添加: {name}")

    def _delete_profile(self):
        name = self._get_selected_name()
        if not name:
            messagebox.showinfo("提示", "请先选择一个服务器")
            return
        if not messagebox.askyesno("确认删除", f"确定要删除服务器配置 '{name}' 吗？"):
            return

        del self.data["profiles"][name]
        if self.data.get("active_profile") == name:
            self.data["active_profile"] = ""
        save_profiles(self.data)
        self.current_name = None
        self._refresh_list()
        self.status_var.set(f"已删除: {name}")

    def _copy_profile(self):
        name = self._get_selected_name()
        if not name:
            messagebox.showinfo("提示", "请先选择一个服务器")
            return

        new_name = f"{name}-copy"
        profiles = self.data.setdefault("profiles", {})
        i = 1
        while new_name in profiles:
            new_name = f"{name}-copy-{i}"
            i += 1

        profiles[new_name] = _deep_copy(profiles[name])
        save_profiles(self.data)
        self._refresh_list()
        self._select_profile(new_name)
        self.status_var.set(f"已复制: {name} -> {new_name}")

    def _add_path(self):
        path = self.var_new_path.get().strip()
        if not path:
            return
        # 检查重复
        existing = list(self.paths_listbox.get(0, tk.END))
        if path in existing:
            messagebox.showinfo("提示", "路径已存在")
            return
        self.paths_listbox.insert(tk.END, path)
        self.var_new_path.set("")
        self._modified = True

    def _remove_path(self):
        sel = self.paths_listbox.curselection()
        if not sel:
            messagebox.showinfo("提示", "请先选择要删除的路径")
            return
        self.paths_listbox.delete(sel[0])
        self._modified = True

    def _browse_key(self):
        path = filedialog.askopenfilename(
            title="选择 SSH 私钥文件",
            filetypes=[("所有文件", "*.*"), ("PEM 文件", "*.pem"), ("密钥文件", "*.key")],
        )
        if path:
            self.var_key_path.set(path)

    def _save_current(self):
        """保存当前编辑的配置到 profiles"""
        if not self.current_name:
            messagebox.showinfo("提示", "没有正在编辑的配置")
            return
        try:
            name, profile = self._read_form()
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return

        profiles = self.data.setdefault("profiles", {})

        # 如果名称改变了，需要重命名
        old_name = self.current_name
        if name != old_name:
            if name in profiles:
                messagebox.showerror("错误", f"名称 '{name}' 已存在")
                return
            del profiles[old_name]
            if self.data.get("active_profile") == old_name:
                self.data["active_profile"] = name

        profiles[name] = profile
        self.current_name = name
        save_profiles(self.data)
        self._refresh_list()
        self._select_profile(name)
        self.status_var.set(f"已保存: {name}")

    def _switch_active(self):
        """切换激活的服务器：写入 config.json"""
        name = self._get_selected_name()
        if not name:
            messagebox.showinfo("提示", "请先选择一个服务器")
            return

        profiles = self.data.get("profiles", {})
        if name not in profiles:
            messagebox.showerror("错误", f"服务器 '{name}' 不存在")
            return

        # 先保存当前编辑
        if self.current_name:
            try:
                self._save_current()
            except Exception:
                pass

        profile = profiles[name]
        write_config(profile)
        self.data["active_profile"] = name
        save_profiles(self.data)
        self._refresh_list()
        self._select_profile(name)
        self.status_var.set(f"已切换到: {name}  (config.json 已更新)")
        messagebox.showinfo("切换成功", f"已切换到服务器 '{name}'\n\nconfig.json 已更新，Claude Code 将使用新配置。")

    def _test_connection(self):
        """测试 SSH 连接"""
        try:
            name, profile = self._read_form()
        except ValueError as e:
            messagebox.showerror("错误", str(e))
            return

        host = profile["ssh"]["host"]
        port = profile["ssh"]["port"]
        username = profile["ssh"]["username"]

        if not host:
            messagebox.showerror("错误", "主机地址不能为空")
            return

        self.status_var.set(f"正在测试连接 {host}:{port} ...")
        self.root.update_idletasks()

        def _do_test():
            try:
                import paramiko
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

                kwargs = {
                    "hostname": host,
                    "port": port,
                    "username": username,
                    "timeout": 8,
                }
                auth = profile["ssh"]["auth"]
                if auth["type"] == "key":
                    kwargs["key_filename"] = os.path.expanduser(auth["key_path"])
                    if auth.get("key_password"):
                        kwargs["passphrase"] = auth["key_password"]
                else:
                    kwargs["password"] = auth["password"]

                client.connect(**kwargs)
                stdin, stdout, stderr = client.exec_command("echo ok", timeout=5)
                result = stdout.read().decode().strip()
                client.close()

                if result == "ok":
                    self.root.after(0, lambda: self._test_result(True, "连接成功!"))
                else:
                    self.root.after(0, lambda: self._test_result(False, "连接异常: 未能执行测试命令"))
            except ImportError:
                self.root.after(0, lambda: self._test_result(False, "paramiko 未安装，请运行: pip install paramiko"))
            except Exception as e:
                self.root.after(0, lambda: self._test_result(False, f"连接失败: {e}"))

        threading.Thread(target=_do_test, daemon=True).start()

    def _test_result(self, success: bool, msg: str):
        if success:
            self.status_var.set(f"测试结果: {msg}")
            messagebox.showinfo("连接测试", msg)
        else:
            self.status_var.set(f"测试结果: {msg}")
            messagebox.showerror("连接测试", msg)

    def _on_close(self):
        if self._modified:
            if messagebox.askyesno("未保存", "有未保存的修改，是否保存？"):
                try:
                    self._save_current()
                except Exception:
                    pass
        self.root.destroy()


# ── 入口 ──────────────────────────────────────────────────────────────


def main():
    root = tk.Tk()

    # 尝试设置高 DPI 支持（Windows）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # 设置主题
    style = ttk.Style()
    available = style.theme_names()
    for preferred in ("clam", "vista", "winnative", "default"):
        if preferred in available:
            style.theme_use(preferred)
            break

    app = ServerManagerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
