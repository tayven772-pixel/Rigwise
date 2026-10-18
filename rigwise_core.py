"""Rigwise - reads your PC's specs and tunes Windows to match them.

Run:   python rigwise.py     (Windows 10/11, Python 3.9+; `pip install psutil` is optional)
Build: double-click build.bat to make dist\\Rigwise.exe

Every registry change is backed up to %APPDATA%\\Rigwise\\backup.json first,
so "Undo all changes" puts your settings back exactly as they were.
"""
import ctypes, json, os, platform, queue, re, shutil, subprocess, sys, threading
import tkinter as tk
from tkinter import messagebox

try:
    import winreg
except ImportError:
    winreg = None          # not Windows: dashboard still works, tweaks are disabled
try:
    import psutil
except ImportError:
    psutil = None

IS_WIN = winreg is not None
NOWIN = 0x08000000 if IS_WIN else 0          # CREATE_NO_WINDOW: no console flashes
APPDATA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Rigwise")
BACKUP = os.path.join(APPDATA, "backup.json")
DW, SZ = (winreg.REG_DWORD, winreg.REG_SZ) if IS_WIN else (4, 1)
DISCRETE = re.compile(r"NVIDIA|GeForce|RTX|GTX|Radeon RX|Radeon Pro|Radeon VII|Arc A\d", re.I)
GUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"

BG, SIDE, PANEL, LINE = "#0d1117", "#10151d", "#161c27", "#273142"
TEXT, MUTED, ACC, WARN, BAD = "#e8ecf2", "#8a94a6", "#34d399", "#f5a524", "#ef5b5b"


def F(size, bold=False):
    return ("Segoe UI", size, "bold" if bold else "normal")


def run(cmd, timeout=30):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, creationflags=NOWIN,
                           stdin=subprocess.DEVNULL)      # a --noconsole exe has no stdin to inherit
        return r.stdout.strip()
    except Exception:
        return ""


def human(b):
    return f"{b / 2**30:.1f} GB" if b >= 2**30 else f"{b / 2**20:.0f} MB"


def aslist(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_admin():
    args = "" if getattr(sys, "frozen", False) else f'"{os.path.abspath(sys.argv[0])}"'
    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, args, None, 1)
    sys.exit()


# ---------------------------------------------------------------- live meters
class Meter:
    def __init__(self):
        self._last = None
        if psutil:
            psutil.cpu_percent(None)

    def cpu(self):
        if psutil:
            return psutil.cpu_percent(None)
        if not IS_WIN:
            return 0.0
        idle, krn, usr = (ctypes.c_ulonglong() for _ in range(3))
        ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(krn), ctypes.byref(usr))
        total, prev, self._last = krn.value + usr.value, self._last, (idle.value, krn.value + usr.value)
        if not prev or total == prev[1]:
            return 0.0
        busy = (total - prev[1]) - (idle.value - prev[0])
        return max(0.0, min(100.0, 100.0 * busy / (total - prev[1])))

    def ram(self):
        """-> (percent used, total bytes)"""
        if psutil:
            m = psutil.virtual_memory()
            return m.percent, m.total
        if IS_WIN:
            class MS(ctypes.Structure):
                _fields_ = [("len", ctypes.c_ulong), ("load", ctypes.c_ulong), ("tp", ctypes.c_ulonglong),
                            ("ap", ctypes.c_ulonglong), ("tpf", ctypes.c_ulonglong), ("apf", ctypes.c_ulonglong),
                            ("tv", ctypes.c_ulonglong), ("av", ctypes.c_ulonglong), ("aev", ctypes.c_ulonglong)]
            m = MS()
            m.len = ctypes.sizeof(m)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return float(m.load), m.tp
        return 0.0, 0


# ---------------------------------------------------------------- spec reading
PS = r"""
$ErrorActionPreference='SilentlyContinue'
$c=Get-CimInstance Win32_Processor|select -First 1 Name,NumberOfCores,NumberOfLogicalProcessors,MaxClockSpeed
$g=@(Get-CimInstance Win32_VideoController|%{[pscustomobject]@{name=$_.Name;driver=$_.DriverVersion}})
$v=@(Get-ItemProperty 'HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11cd-bfc1-08002be10318}\0*'|%{[pscustomobject]@{name=$_.DriverDesc;vram=$_.'HardwareInformation.qwMemorySize'}})
$m=@(Get-CimInstance Win32_PhysicalMemory|%{[pscustomobject]@{size=$_.Capacity;speed=$_.Speed}})
$d=@(Get-PhysicalDisk|%{[pscustomobject]@{name=$_.FriendlyName;type=[string]$_.MediaType;size=$_.Size}})
$o=Get-CimInstance Win32_OperatingSystem|select Caption,BuildNumber
$b=Get-CimInstance Win32_BaseBoard|select Manufacturer,Product
[pscustomobject]@{cpu=$c;gpu=$g;vram=$v;ram=$m;disk=$d;os=$o;board=$b;laptop=(@(Get-CimInstance Win32_Battery).Count -gt 0)}|ConvertTo-Json -Depth 4 -Compress
"""


def read_specs():
    n = os.cpu_count() or 1
    s = dict(cpu=platform.processor() or "Unknown CPU", cores=n, threads=n, ghz=0.0, gpus=[], ram_gb=0,
             ram_mhz=0, disks=[], os=platform.platform(), board="", laptop=False, build=0)
    j = None
    if IS_WIN:
        try:
            j = json.loads(run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                                "-Command", PS], 45))
        except ValueError:
            pass
    if j:
        c = j.get("cpu") or {}
        s.update(cpu=(c.get("Name") or s["cpu"]).strip(), cores=c.get("NumberOfCores") or n,
                 threads=c.get("NumberOfLogicalProcessors") or n, ghz=(c.get("MaxClockSpeed") or 0) / 1000)
        vram = {v.get("name"): v.get("vram") for v in aslist(j.get("vram"))}
        for g in aslist(j.get("gpu")):
            b = vram.get(g.get("name"))
            s["gpus"].append((g.get("name") or "Unknown GPU", b / 2**30 if isinstance(b, (int, float)) and b > 0 else 0,
                              g.get("driver") or ""))
        mods = aslist(j.get("ram"))
        s["ram_gb"] = round(sum(m.get("size") or 0 for m in mods) / 2**30)
        s["ram_mhz"] = max([m.get("speed") or 0 for m in mods] or [0])
        s["disks"] = [(d.get("name") or "Disk", (d.get("type") or "").replace("Unspecified", ""),
                       (d.get("size") or 0) / 1e9) for d in aslist(j.get("disk"))]
        o = j.get("os") or {}
        s.update(os=o.get("Caption") or s["os"], build=int(o.get("BuildNumber") or 0), laptop=bool(j.get("laptop")))
        b = j.get("board") or {}
        s["board"] = f'{b.get("Manufacturer", "")} {b.get("Product", "")}'.strip()
    if not s["ram_gb"]:
        s["ram_gb"] = round(Meter().ram()[1] / 2**30)
    s["discrete"] = any(DISCRETE.search(g[0]) for g in s["gpus"])
    s["ssd"] = any(re.search(r"SSD|NVMe", d[0] + " " + d[1], re.I) for d in s["disks"])
    return s


def tier(s):
    pts = ((2 if s["ram_gb"] >= 16 else 1 if s["ram_gb"] >= 8 else 0)
           + (2 if s["threads"] >= 12 else 1 if s["threads"] >= 6 else 0)
           + (2 if s["discrete"] else 0) + (1 if s["ssd"] else 0))
    return "High-end" if pts >= 6 else "Mainstream" if pts >= 3 else "Entry-level"


# ---------------------------------------------------------------- registry + backup
def _hive(n):
    return winreg.HKEY_CURRENT_USER if n == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def reg_get(h, p, n):
    try:
        with winreg.OpenKey(_hive(h), p) as k:
            return winreg.QueryValueEx(k, n)          # (value, type)
    except OSError:
        return None


def reg_set(h, p, n, t, v):
    with winreg.CreateKeyEx(_hive(h), p, 0, winreg.KEY_SET_VALUE) as k:
        winreg.SetValueEx(k, n, 0, t, v)


def reg_del(h, p, n):
    try:
        with winreg.OpenKey(_hive(h), p, 0, winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, n)
    except OSError:
        pass


def load_backup():
    try:
        with open(BACKUP) as f:
            return json.load(f)
    except Exception:
        return {}


def save_backup(b):
    os.makedirs(APPDATA, exist_ok=True)
    with open(BACKUP, "w") as f:
        json.dump(b, f, indent=1)


# ---------------------------------------------------------------- tweaks
def R(cond, yes, no):
    return bool(cond), (yes if cond else no)


class Tweak:
    kind = "toggle"

    def __init__(self, key, name, desc, rec, regs=(), restart=False):
        self.key, self.name, self.rec, self.regs = key, name, rec, list(regs)
        self.desc = desc + (" Sign out or restart to fully apply." if restart else "")
        self.admin = any(r[0] == "HKLM" for r in self.regs)
        self.recommended, self.reason = False, ""

    def is_on(self):
        return all((reg_get(h, p, n) or (None,))[0] == v for h, p, n, t, v in self.regs)

    def apply(self):
        b = load_backup()
        if self.key not in b:                          # remember the original values once
            b[self.key] = [reg_get(h, p, n) for h, p, n, t, v in self.regs]
            save_backup(b)
        for h, p, n, t, v in self.regs:
            reg_set(h, p, n, t, v)

    def revert(self):                                  # no backup = back to the Windows default
        b = load_backup()
        for (h, p, n, t, v), old in zip(self.regs, b.get(self.key) or [None] * len(self.regs)):
            reg_del(h, p, n) if old is None else reg_set(h, p, n, old[1], old[0])
        b.pop(self.key, None)
        save_backup(b)


HIGH, BALANCED = "8c5e7fda-e8bf-4a96-9a85-a6e84c45e8b2", "381b4222-f694-41f0-9685-ff5bb260df2e"


class PowerPlan(Tweak):
    def is_on(self):
        out = run(["powercfg", "/getactivescheme"]).lower()
        return HIGH in out or "high performance" in out or "ultimate" in out

    def apply(self):
        cur = re.search(GUID, run(["powercfg", "/getactivescheme"]), re.I)
        b = load_backup()
        b.setdefault(self.key, cur.group(0) if cur else BALANCED)
        save_backup(b)
        run(["powercfg", "/setactive", HIGH])
        if HIGH not in run(["powercfg", "/getactivescheme"]).lower():   # plan hidden on some laptops
            m = re.search(GUID, run(["powercfg", "-duplicatescheme", HIGH]), re.I)
            if m:
                run(["powercfg", "/setactive", m.group(0)])

    def revert(self):
        b = load_backup()
        run(["powercfg", "/setactive", b.pop(self.key, BALANCED)])
        save_backup(b)


class MouseAccel(Tweak):
    def _live(self):
        v = [int((reg_get("HKCU", r"Control Panel\Mouse", n) or ("0",))[0])
             for n in ("MouseThreshold1", "MouseThreshold2", "MouseSpeed")]
        ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, (ctypes.c_int * 3)(*v), 3)

    def apply(self):
        super().apply()
        self._live()

    def revert(self):
        super().revert()
        self._live()


class Action:
    kind = "action"

    def __init__(self, key, name, desc, rec, label, fn, info=None):
        self.key, self.name, self.desc, self.rec, self.label, self.fn, self.info = key, name, desc, rec, label, fn, info
        self.recommended, self.reason = False, ""


def temp_dirs():
    dirs = {os.environ.get("TEMP"), os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "Temp")}
    return [d for d in dirs if d and os.path.isdir(d) and os.path.basename(d.rstrip("\\/")).lower() in ("temp", "tmp")]


def tree_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def clean_temp():
    before = sum(tree_size(d) for d in temp_dirs())
    for d in temp_dirs():
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.isdir(p) and not os.path.islink(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
            except OSError:
                pass                                   # in use: skip it
    return f"Freed {human(max(0, before - sum(tree_size(d) for d in temp_dirs())))} of temporary files. Files in use were skipped."


def build_tweaks(s):
    cur = r"Software\Microsoft\Windows\CurrentVersion"
    ts = [
        PowerPlan("power", "High-performance power plan", "Keeps the CPU ready instead of ramping down between loads.",
                  lambda s: R(not s["laptop"], "Desktop PC, so there is no battery to protect.",
                              "Laptop: this shortens battery life. Best used while plugged in.")),
        Tweak("gamemode", "Game Mode", "Gives the game you are playing priority over background tasks.",
              lambda s: R(s["build"] >= 15063, "Your Windows version supports it.", "Needs a newer Windows 10 build."),
              [("HKCU", r"Software\Microsoft\GameBar", "AutoGameModeEnabled", DW, 1)]),
        Tweak("dvr", "Turn off background game recording",
              "Stops Xbox Game Bar from recording clips in the background, which costs CPU and GPU time.",
              lambda s: R(s["ram_gb"] <= 16, f"{s['ram_gb']} GB of RAM: the headroom is worth more than the clips.",
                          f"{s['ram_gb']} GB of RAM is plenty. Optional."),
              [("HKCU", r"System\GameConfigStore", "GameDVR_Enabled", DW, 0), ("HKCU", cur + r"\GameDVR", "AppCaptureEnabled", DW, 0)]),
        Tweak("fx", "Lighter visual effects", "Turns off window animations and transparency to free up GPU and RAM.",
              lambda s: R(s["ram_gb"] < 8 or not s["discrete"], "Little RAM or no dedicated GPU, so desktop effects cost you.",
                          "Your hardware handles the effects fine. Optional."),
              [("HKCU", r"Control Panel\Desktop\WindowMetrics", "MinAnimate", SZ, "0"),
               ("HKCU", cur + r"\Explorer\Advanced", "TaskbarAnimations", DW, 0),
               ("HKCU", cur + r"\Themes\Personalize", "EnableTransparency", DW, 0)], restart=True),
        Tweak("bgapps", "Stop apps running in the background", "Store apps stop using CPU, RAM and network while closed.",
              lambda s: R(s["ram_gb"] <= 8, f"{s['ram_gb']} GB of RAM: background apps compete with your games.",
                          "Enough RAM that this is optional."),
              [("HKCU", cur + r"\BackgroundAccessApplications", "GlobalUserDisabled", DW, 1)]),
        MouseAccel("mouse", "Turn off mouse acceleration", "Makes pointer movement match your hand movement, which helps aiming.",
                   lambda s: R(False, "", "A personal preference, so it is not applied automatically."),
                   [("HKCU", r"Control Panel\Mouse", "MouseSpeed", SZ, "0"), ("HKCU", r"Control Panel\Mouse", "MouseThreshold1", SZ, "0"),
                    ("HKCU", r"Control Panel\Mouse", "MouseThreshold2", SZ, "0")]),
        Tweak("hags", "Hardware-accelerated GPU scheduling", "Lets the GPU manage its own memory queue. Helps some setups, hurts others.",
              lambda s: R(False, "", "Depends on your GPU driver, so it is not applied automatically. Needs administrator."),
              [("HKLM", r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers", "HwSchMode", DW, 2)], restart=True),
        Action("temp", "Clear temporary files", "Deletes files in your Temp folders that Windows and apps no longer need.",
               lambda s: R(True, "Frees space and is safe to repeat.", ""), "Clean now", clean_temp,
               lambda: f"{human(sum(tree_size(d) for d in temp_dirs()))} of temporary files found"),
        Action("dns", "Flush DNS cache", "Clears stale network lookups. Useful when sites or game servers will not connect.",
               lambda s: R(False, "", "Only needed when you have connection problems."), "Flush",
               lambda: "DNS cache flushed." if run(["ipconfig", "/flushdns"]) else "Could not flush the DNS cache."),
    ]
    for t in ts:
        t.recommended, t.reason = t.rec(s)
    return ts


# ---------------------------------------------------------------- startup apps
RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
PROTECTED = ("securityhealth", "windowsdefender")


def startup_items():
    out = []
    for h in ("HKCU", "HKLM"):
        try:
            with winreg.OpenKey(_hive(h), RUN) as k:
                i = 0
                while True:
                    try:
                        name, val, _ = winreg.EnumValue(k, i)
                    except OSError:
                        break
                    i += 1
                    ap = reg_get(h, APPROVED, name)
                    off = bool(ap and isinstance(ap[0], bytes) and ap[0][:1] and ap[0][0] & 1)
                    out.append((h, name, str(val), not off))
        except OSError:
            pass
    return out


def set_startup(h, name, on):                         # same switch Task Manager uses
    reg_set(h, APPROVED, name, winreg.REG_BINARY, (b"\x02" if on else b"\x03") + b"\x00" * 11)


# ---------------------------------------------------------------- widgets
class Toggle(tk.Canvas):
    def __init__(self, master, on, command, bg):
        super().__init__(master, width=44, height=24, bg=bg, highlightthickness=0, cursor="hand2")
        self.on, self.command = on, command
        self.bind("<Button-1>", lambda e: self.command(self))
        self.draw()

    def set(self, on):
        self.on = on
        self.draw()

    def draw(self):
        self.delete("all")
        c = ACC if self.on else "#3a4558"
        self.create_oval(0, 2, 20, 22, fill=c, outline=c)
        self.create_oval(24, 2, 44, 22, fill=c, outline=c)
        self.create_rectangle(10, 2, 34, 22, fill=c, outline=c)
        x = 24 if self.on else 4
        self.create_oval(x, 4, x + 16, 20, fill="#ffffff", outline="#ffffff")


class Gauge(tk.Canvas):
    def __init__(self, master, label):
        super().__init__(master, width=150, height=150, bg=PANEL, highlightthickness=0)
        self.label = label
        self.set(0)

    def set(self, pct, sub=""):
        self.delete("all")
        col = ACC if pct < 60 else WARN if pct < 85 else BAD
        self.create_arc(14, 14, 136, 136, start=0, extent=359.9, style="arc", outline=LINE, width=10)
        if pct >= 1:
            self.create_arc(14, 14, 136, 136, start=90, extent=-min(359.9, 3.6 * pct), style="arc", outline=col, width=10)
        self.create_text(75, 66, text=f"{pct:.0f}%", fill=TEXT, font=F(22, True))
        self.create_text(75, 94, text=self.label, fill=MUTED, font=F(10))
        if sub:
            self.create_text(75, 112, text=sub, fill=MUTED, font=F(9))


class Scroll(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg=BG)
        self.cv = tk.Canvas(self, bg=BG, highlightthickness=0)
        sb = tk.Scrollbar(self, command=self.cv.yview)
        self.cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.cv.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(self.cv, bg=BG)
        win = self.cv.create_window(0, 0, window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: self.cv.configure(scrollregion=self.cv.bbox("all")))
        self.cv.bind("<Configure>", lambda e: self.cv.itemconfigure(win, width=e.width))
        self.bind_all("<MouseWheel>", lambda e: self.cv.yview_scroll(int(-e.delta / 120), "units")
                      if self.winfo_ismapped() else None, add="+")

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()


def button(master, text, cmd, primary=True, **kw):
    return tk.Button(master, text=text, command=cmd, bd=0, padx=14, pady=7, cursor="hand2", font=F(10, True),
                     bg=ACC if primary else PANEL, fg="#04130d" if primary else TEXT,
                     activebackground="#2bb883" if primary else LINE, activeforeground=TEXT if not primary else "#04130d", **kw)


# ---------------------------------------------------------------- app
class App:
    def __init__(self):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
        self.root = r = tk.Tk()
        r.title("Rigwise")
        r.geometry("1000x680")
        r.minsize(880, 580)
        r.configure(bg=BG)
        self.q, self.meter = queue.Queue(), Meter()
        self.specs, self.tier, self.tweaks, self.toggles, self.infos = None, "", [], {}, {}
        self.sysdrive = (os.environ.get("SystemDrive", "C:") + "\\") if IS_WIN else "/"
        self.msg = tk.StringVar(value="Reading your hardware…")

        side = tk.Frame(r, bg=SIDE, width=180)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="Rigwise", bg=SIDE, fg=TEXT, font=F(16, True), anchor="w", padx=18, pady=22).pack(fill="x")
        main = tk.Frame(r, bg=BG)
        main.pack(side="left", fill="both", expand=True)
        tk.Label(main, textvariable=self.msg, bg=BG, fg=MUTED, font=F(9), anchor="w", padx=24, pady=8).pack(side="bottom", fill="x")
        stack = tk.Frame(main, bg=BG)
        stack.pack(fill="both", expand=True, padx=24, pady=(20, 0))
        stack.grid_rowconfigure(0, weight=1)
        stack.grid_columnconfigure(0, weight=1)
        self.pages = {n: tk.Frame(stack, bg=BG) for n in ("Dashboard", "Optimize", "Startup")}
        self.nav = {}
        for n, p in self.pages.items():
            p.grid(row=0, column=0, sticky="nsew")
            b = tk.Button(side, text=n, anchor="w", padx=18, pady=10, bd=0, relief="flat", font=F(11), bg=SIDE, fg=MUTED,
                          activebackground=PANEL, activeforeground=TEXT, cursor="hand2", command=lambda n=n: self.show(n))
            b.pack(fill="x")
            self.nav[n] = b
        self.build_dashboard()
        self.build_optimize_shell()
        self.build_startup_shell()
        self.show("Dashboard")
        threading.Thread(target=self._load_specs, daemon=True).start()
        r.after(200, self.pump)
        r.after(1000, self.tick)

    # -- plumbing
    def run(self):
        self.root.mainloop()

    def status(self, text):
        self.msg.set(text)

    def pump(self):                                    # runs jobs queued by worker threads
        while True:
            try:
                self.q.get_nowait()()
            except queue.Empty:
                break
            except Exception as e:
                self.status(f"Something went wrong: {e}")
        self.root.after(200, self.pump)

    def tick(self):
        cpu = self.meter.cpu()
        pct, total = self.meter.ram()
        self.gauges[0].set(cpu, f"{self.specs['threads']} threads" if self.specs else "")
        self.gauges[1].set(pct, f"{total / 2**30:.0f} GB" if total else "")
        try:
            d = shutil.disk_usage(self.sysdrive)
            self.gauges[2].set(d.used / d.total * 100, f"{d.free / 2**30:.0f} GB free")
        except OSError:
            pass
        self.root.after(1000, self.tick)

    def show(self, name):
        self.pages[name].tkraise()
        for n, b in self.nav.items():
            b.config(bg=PANEL if n == name else SIDE, fg=TEXT if n == name else MUTED)
        if name == "Startup":
            self.fill_startup()

    def header(self, parent, title):
        top = tk.Frame(parent, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text=title, bg=BG, fg=TEXT, font=F(20, True)).pack(side="left")
        return top

    # -- dashboard
    def build_dashboard(self):
        p = self.pages["Dashboard"]
        top = self.header(p, "Your PC")
        self.sub = tk.Label(top, text="", bg=BG, fg=MUTED, font=F(11))
        self.sub.pack(side="left", padx=14, pady=(8, 0))
        self.go = button(top, "Optimize for my PC", self.optimize, state="disabled")
        self.go.pack(side="right")
        row = tk.Frame(p, bg=BG)
        row.pack(fill="x", pady=16)
        self.gauges = []
        for name in ("CPU", "Memory", "System drive"):
            card = tk.Frame(row, bg=PANEL, padx=12, pady=10)
            card.pack(side="left", expand=True, fill="x", padx=(0, 12))
            g = Gauge(card, name)
            g.pack()
            self.gauges.append(g)
        self.spec_box = tk.Frame(p, bg=PANEL, padx=18, pady=14)
        self.spec_box.pack(fill="x")
        tk.Label(self.spec_box, text="Reading hardware…", bg=PANEL, fg=MUTED, font=F(10)).pack(anchor="w")

    def _load_specs(self):
        s = read_specs()
        self.q.put(lambda: self.got_specs(s))

    def got_specs(self, s):
        self.specs, self.tier = s, tier(s)
        self.sub.config(text=f"{self.tier} {'laptop' if s['laptop'] else 'desktop'}")
        for w in self.spec_box.winfo_children():
            w.destroy()
        gpus = [n + (f" · {v:.0f} GB" if v else "") for n, v, _ in s["gpus"]] or ["Not detected"]
        disks = [f"{n} · {t + ' · ' if t else ''}{sz:.0f} GB" for n, t, sz in s["disks"]] or ["Not detected"]
        rows = [("Processor", f"{s['cpu']}\n{s['cores']} cores · {s['threads']} threads" + (f" · up to {s['ghz']:.1f} GHz" if s["ghz"] else "")),
                ("Graphics", "\n".join(gpus)),
                ("Memory", f"{s['ram_gb']} GB" + (f" · {s['ram_mhz']} MHz" if s["ram_mhz"] else "")),
                ("Storage", "\n".join(disks)), ("Motherboard", s["board"] or "Unknown"), ("Windows", s["os"])]
        for i, (k, v) in enumerate(rows):
            tk.Label(self.spec_box, text=k, bg=PANEL, fg=MUTED, font=F(10), anchor="nw", width=12).grid(row=i, column=0, sticky="nw", pady=4)
            tk.Label(self.spec_box, text=v, bg=PANEL, fg=TEXT, font=F(10), justify="left", anchor="w").grid(row=i, column=1, sticky="w", pady=4)
        if IS_WIN:
            self.tweaks = build_tweaks(s)
            self.fill_optimize()
            self.go.config(state="normal")
            self.status("Ready. Optimize for my PC applies only the tweaks that suit your hardware.")
        else:
            self.opt_sub.config(text="Optimizations only work on Windows. The dashboard works on any system.")
            self.status("Specs loaded. Optimizations are disabled on this system.")

    # -- optimize
    def build_optimize_shell(self):
        p = self.pages["Optimize"]
        top = self.header(p, "Optimize")
        button(top, "Undo all changes", self.undo_all, primary=False).pack(side="right")
        button(top, "Apply recommended", self.optimize).pack(side="right", padx=8)
        self.opt_sub = tk.Label(p, text="Reading hardware…", bg=BG, fg=MUTED, font=F(10), anchor="w")
        self.opt_sub.pack(fill="x", pady=(2, 8))
        if IS_WIN and not is_admin():
            bar = tk.Frame(p, bg="#2a2110", padx=14, pady=8)
            bar.pack(fill="x", pady=(0, 8))
            tk.Label(bar, text="Some tweaks need administrator rights.", bg="#2a2110", fg=WARN, font=F(10)).pack(side="left")
            button(bar, "Restart as administrator", relaunch_admin, primary=False).pack(side="right")
        self.opt_scroll = Scroll(p)
        self.opt_scroll.pack(fill="both", expand=True)

    def fill_optimize(self):
        body = self.opt_scroll.body
        for t in self.tweaks:
            f = tk.Frame(body, bg=PANEL, padx=16, pady=12)
            f.pack(fill="x", pady=4, padx=(0, 8))
            left = tk.Frame(f, bg=PANEL)
            left.pack(side="left", fill="x", expand=True)
            head = tk.Frame(left, bg=PANEL)
            head.pack(anchor="w")
            tk.Label(head, text=t.name, bg=PANEL, fg=TEXT, font=F(11, True)).pack(side="left")
            if t.recommended:
                tk.Label(head, text="   Recommended for your PC", bg=PANEL, fg=ACC, font=F(9)).pack(side="left")
            tk.Label(left, text=t.desc, bg=PANEL, fg=MUTED, font=F(9), wraplength=540, justify="left").pack(anchor="w", pady=(2, 0))
            if t.reason:
                tk.Label(left, text=t.reason, bg=PANEL, fg="#b6c0d0", font=F(9), wraplength=540, justify="left").pack(anchor="w")
            if t.kind == "toggle":
                w = Toggle(f, t.is_on(), lambda w, t=t: self.flip(t, w), PANEL)
                w.pack(side="right")
                self.toggles[t.key] = w
            else:
                button(f, t.label, lambda t=t: self.act(t)).pack(side="right")
                if t.info:
                    self.infos[t.key] = tk.Label(left, text="Checking…", bg=PANEL, fg=ACC, font=F(9))
                    self.infos[t.key].pack(anchor="w")
        self.refresh()
        threading.Thread(target=self._load_infos, daemon=True).start()

    def _load_infos(self):
        for t in self.tweaks:
            if t.kind == "action" and t.info:
                txt = t.info()
                self.q.put(lambda k=t.key, x=txt: self.infos[k].config(text=x))

    def refresh(self):
        for t in self.tweaks:
            if t.kind == "toggle":
                self.toggles[t.key].set(t.is_on())
        rec = [t for t in self.tweaks if t.kind == "toggle" and t.recommended]
        self.opt_sub.config(text=f"{self.tier} profile: {sum(t.is_on() for t in rec)} of {len(rec)} recommended tweaks are on.")

    def flip(self, t, w):
        try:
            t.apply() if not w.on else t.revert()
        except OSError:
            self.status("Could not change that setting. Restart Rigwise as administrator and try again.")
            return
        w.set(t.is_on())
        self.refresh()
        self.status(f"{t.name}: {'on' if t.is_on() else 'off'}.")

    def act(self, t):
        self.status(f"{t.label}…")

        def work():
            out = t.fn()
            txt = t.info() if t.info else ""

            def ui():
                self.status(out)
                if t.key in self.infos:
                    self.infos[t.key].config(text=txt)
            self.q.put(ui)
        threading.Thread(target=work, daemon=True).start()

    def optimize(self):
        todo = [t for t in self.tweaks if t.kind == "toggle" and t.recommended and not t.is_on()]
        if not todo:
            messagebox.showinfo("Rigwise", "Everything recommended for your PC is already on.")
            return
        names = "\n".join("•  " + t.name for t in todo)
        if not messagebox.askyesno("Optimize for my PC", f"Your PC is a {self.tier.lower()} "
                                   f"{'laptop' if self.specs['laptop'] else 'desktop'}.\n\nThese tweaks suit it:\n\n{names}\n\n"
                                   "A restore point is created first (when running as administrator), "
                                   "and every change can be undone. Continue?"):
            return
        self.status("Applying tweaks…")

        def work():
            if is_admin():
                run(["powershell", "-NoProfile", "-Command",
                     'Checkpoint-Computer -Description "Rigwise" -RestorePointType MODIFY_SETTINGS'], 90)
            fails = []
            for t in todo:
                try:
                    t.apply()
                except OSError:
                    fails.append(t.name)
            self.q.put(lambda: self.applied(len(todo) - len(fails), fails))
        threading.Thread(target=work, daemon=True).start()

    def applied(self, n, fails):
        self.refresh()
        self.status(f"Applied {n} tweak{'s' if n != 1 else ''}. Sign out or restart to finish visual changes.")
        if fails:
            messagebox.showwarning("Rigwise", "These could not be applied:\n\n" + "\n".join(fails) +
                                   "\n\nRestart Rigwise as administrator and try again.")

    def undo_all(self):
        saved, n = load_backup(), 0
        for t in self.tweaks:
            if t.kind == "toggle" and t.key in saved:
                try:
                    t.revert()
                    n += 1
                except OSError:
                    pass
        self.refresh()
        self.status(f"Restored {n} setting{'s' if n != 1 else ''} to how they were before Rigwise.")

    # -- startup apps
    def build_startup_shell(self):
        p = self.pages["Startup"]
        self.header(p, "Startup apps")
        tk.Label(p, text="Apps that launch when you sign in. Switching one off keeps it installed and you can switch it back on.",
                 bg=BG, fg=MUTED, font=F(10), anchor="w").pack(fill="x", pady=(2, 8))
        self.st_scroll = Scroll(p)
        self.st_scroll.pack(fill="both", expand=True)

    def fill_startup(self):
        self.st_scroll.clear()
        body = self.st_scroll.body
        items = startup_items() if IS_WIN else []
        if not items:
            tk.Label(body, text="No startup apps found in the registry." if IS_WIN else "Startup apps are only listed on Windows.",
                     bg=BG, fg=MUTED, font=F(10)).pack(anchor="w", pady=8)
        for h, name, cmd, on in items:
            f = tk.Frame(body, bg=PANEL, padx=16, pady=10)
            f.pack(fill="x", pady=4, padx=(0, 8))
            left = tk.Frame(f, bg=PANEL)
            left.pack(side="left", fill="x", expand=True)
            tk.Label(left, text=name, bg=PANEL, fg=TEXT, font=F(11, True)).pack(anchor="w")
            tk.Label(left, text=(cmd[:90] + "…") if len(cmd) > 90 else cmd, bg=PANEL, fg=MUTED, font=F(9)).pack(anchor="w")
            if any(x in name.lower() for x in PROTECTED):
                tk.Label(f, text="Windows security", bg=PANEL, fg=MUTED, font=F(9)).pack(side="right")
            else:
                Toggle(f, on, lambda w, h=h, n=name: self.flip_startup(h, n, w), PANEL).pack(side="right")

    def flip_startup(self, h, name, w):
        try:
            set_startup(h, name, not w.on)
        except OSError:
            self.status("Could not change that app. Restart Rigwise as administrator and try again.")
            return
        w.set(not w.on)
        self.status(f"{name}: {'will start with Windows' if w.on else 'will no longer start with Windows'}.")


if __name__ == "__main__":
    try:
        App().run()
    except Exception:
        import traceback
        err = traceback.format_exc()
        try:
            os.makedirs(APPDATA, exist_ok=True)
            log = os.path.join(APPDATA, "error.log")
            with open(log, "w") as f:
                f.write(err)
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Rigwise could not start", f"{err[-700:]}\n\nSaved to {log}")
        except Exception:
            pass
