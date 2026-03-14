#!/home/linuxbrew/.linuxbrew/bin/python3
"""
3DSkit GUI
Auto-installs: numpy, ctrtool, vgmstream
Auto-clones:   3DSkit
Workflow:      .cia/.3ds → ctrtool (RomFS) → 3DSkit (BCSTM→WAV)
"""

import subprocess, sys, os, shutil, threading, zipfile, stat, urllib.request
from pathlib import Path

# ── constants ─────────────────────────────────────────────────────────────────

PYTHON  = sys.executable
BREW    = str(next((p for p in [
    Path.home() / ".linuxbrew/bin/brew",
    Path("/home/linuxbrew/.linuxbrew/bin/brew"),
] if p.exists()), Path("brew")))

LOCAL_BIN   = Path.home() / ".local" / "bin"
CTRTOOL_BIN = LOCAL_BIN / "ctrtool"
CTRTOOL_URL = (
    "https://github.com/3DSGuy/Project_CTR/releases/download/"
    "ctrtool-v1.2.0/ctrtool-v1.2.0-ubuntu_x86_64.zip"
)

# ── bootstrap ─────────────────────────────────────────────────────────────────

def _run(cmd, **kw):
    return subprocess.run(cmd, **kw)

def _pip_ok(pkg):
    try: __import__(pkg); return True
    except ImportError: return False

def _brew_ok(pkg):
    try: return _run([BREW,"list","--formula",pkg], capture_output=True).returncode == 0
    except: return False

def _find_kit():
    for p in [
        Path.home()/"3DSkit"/"3DSkit.py",
        Path.home()/"3dskit"/"3DSkit.py",
        Path.cwd()/"3DSkit"/"3DSkit.py",
        Path.cwd()/"3DSkit.py",
    ]:
        if p.exists(): return str(p)
    return ""

def bootstrap():
    steps = []
    if not _pip_ok("numpy"):
        steps.append(("pip: numpy",
            [PYTHON,"-m","pip","install","--break-system-packages","numpy"]))
    if not shutil.which("git") and shutil.which(BREW):
        steps.append(("brew: git", [BREW,"install","git"]))
    if not _brew_ok("vgmstream") and not shutil.which("vgmstream-cli") and shutil.which(BREW):
        steps.append(("brew: vgmstream", [BREW,"install","vgmstream"]))

    if steps:
        print("\n╔══════════════════════════════════════╗")
        print("║   3DSkit GUI — installing deps…      ║")
        print("╚══════════════════════════════════════╝\n")
        for label, cmd in steps:
            print(f"  → {label}")
            r = _run(cmd)
            print(f"  {'✓' if r.returncode==0 else '✗'} done\n")

    # clone 3DSkit
    if not _find_kit():
        dest = Path.home() / "3DSkit"
        if not dest.exists():
            print("  → cloning Tyulis/3DSkit…")
            r = _run(["git","clone","https://github.com/Tyulis/3DSkit.git",str(dest)])
            print(f"  {'✓ cloned' if r.returncode==0 else '✗ git clone failed'}\n")
        setup = dest / "setup.py"
        if setup.exists():
            _run([PYTHON,str(setup),"build_ext","--inplace"],
                 cwd=str(dest), capture_output=True)

    # download ctrtool binary if missing
    if not CTRTOOL_BIN.exists() and not shutil.which("ctrtool"):
        print("  → downloading ctrtool…")
        LOCAL_BIN.mkdir(parents=True, exist_ok=True)
        try:
            zip_path = Path("/tmp/ctrtool.zip")
            urllib.request.urlretrieve(CTRTOOL_URL, zip_path)
            with zipfile.ZipFile(zip_path) as z:
                for name in z.namelist():
                    if "ctrtool" in name.lower() and not name.endswith("/"):
                        CTRTOOL_BIN.write_bytes(z.read(name))
                        CTRTOOL_BIN.chmod(CTRTOOL_BIN.stat().st_mode | stat.S_IEXEC)
                        break
            print(f"  ✓ ctrtool installed to {CTRTOOL_BIN}\n")
        except Exception as e:
            print(f"  ✗ ctrtool download failed: {e}\n")

bootstrap()

# ── GUI imports ───────────────────────────────────────────────────────────────

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext

# ── theme ─────────────────────────────────────────────────────────────────────

C = {
    "bg": "#f5f4f0", "sidebar": "#ffffff", "card": "#ffffff",
    "border": "#e2e0d8", "accent": "#378ADD", "text": "#1a1a1a",
    "text2": "#6b6a66", "text3": "#9a9994", "term_bg": "#0f0f0f",
    "term_fg": "#d0d0d0", "green": "#639922", "amber": "#EF9F27",
    "red": "#E24B4A", "sel_bg": "#E6F1FB", "sel_bd": "#378ADD",
    "btn_bg": "#1a1a1a", "btn_fg": "#ffffff",
}
FM  = ("Monospace", 10)
FU  = ("Sans", 10)
FUB = ("Sans", 11, "bold")
FL  = ("Sans", 9)

EXT_COLORS = {
    ".cia":   ("#E6F1FB","#0C447C"), ".3ds":   ("#EAF3DE","#27500A"),
    ".bcstm": ("#FAEEDA","#633806"), ".bcwav": ("#FAEEDA","#633806"),
    ".bcsar": ("#FBEAF0","#72243E"), ".romfs": ("#EEEDFE","#3C3489"),
    ".bin":   ("#F1EFE8","#444441"),
}

VIEWS = {
    "Dump OST": {
        "flag": "CTRTOOL_AUTO",
        "ops": [
            ("Full pipeline",    "CTRTOOL_AUTO",
             "CIA/3DS → extract RomFS via ctrtool → convert all BCSTM/BCWAV to WAV"),
            ("Audio only",       "CTRTOOL_AUDIO",
             "Same as above, faster — skips non-audio extraction"),
        ],
    },
    "Convert Audio": {
        "flag": "-g",
        "ops": [
            ("BCSTM → WAV",   "-g BCSTM", "Convert BCSTM files to WAV"),
            ("BCWAV → WAV",   "-g BCWAV", "Convert BCWAV files to WAV"),
            ("BCSAR → files", "-g BCSAR", "Unpack a BCSAR sound archive"),
        ],
    },
    "Extract / Unpack": {
        "flag": "-x",
        "ops": [
            ("ctrtool RomFS",  "CTRTOOL_ROMFS", "Extract RomFS from CIA/3DS via ctrtool"),
            ("3DSkit unpack",  "-x",            "Unpack a container with 3DSkit"),
        ],
    },
    "Identify File": {
        "flag": "-D",
        "ops": [("Identify", "-D", "Print format info about a file")],
    },
}


def fmt_size(b):
    if b >= 1_073_741_824: return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576:     return f"{b/1_048_576:.1f} MB"
    if b >= 1024:          return f"{b/1024:.0f} KB"
    return f"{b} B"


# ── app ───────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("3DSkit GUI")
        self.geometry("1000x720")
        self.minsize(820, 600)
        self.configure(bg=C["bg"])

        self.kit_path     = tk.StringVar(value=_find_kit())
        self.ctrtool_path = tk.StringVar(value=
            str(CTRTOOL_BIN) if CTRTOOL_BIN.exists()
            else shutil.which("ctrtool") or "")
        self.out_dir      = tk.StringVar(value=str(Path.home()/"3dskit_output"))
        self.fmt_var      = tk.StringVar(value="auto-detect")
        self.verbose      = tk.BooleanVar(value=False)
        self.bigendian    = tk.BooleanVar(value=False)
        self.current_view = tk.StringVar(value="Dump OST")
        self.selected_op  = 0
        self.files: list[Path] = []

        self._build_ui()
        self._refresh_ops()
        self._update_preview()

    # ── layout ────────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sb = tk.Frame(self, bg=C["sidebar"], width=248)
        sb.grid(row=0, column=0, sticky="ns")
        sb.grid_propagate(False)
        sb.columnconfigure(0, weight=1)

        tk.Label(sb, text="3DSkit GUI", font=("Monospace",14,"bold"),
                 bg=C["sidebar"], fg=C["text"]).grid(
            row=0, column=0, sticky="w", padx=18, pady=(18,2))
        tk.Label(sb, text="ctrtool + 3DSkit wrapper",
                 font=FL, bg=C["sidebar"], fg=C["text3"]).grid(
            row=1, column=0, sticky="w", padx=18)
        ttk.Separator(sb).grid(row=2, column=0, sticky="ew", pady=10)

        tk.Label(sb, text="TOOLS", font=("Sans",8,"bold"),
                 bg=C["sidebar"], fg=C["text3"]).grid(
            row=3, column=0, sticky="w", padx=20, pady=(0,4))

        self._nav_btns = {}
        for i, name in enumerate(VIEWS):
            b = tk.Button(sb, text=name, anchor="w", font=FU,
                          bg=C["sidebar"], fg=C["text2"],
                          activebackground=C["bg"], relief="flat",
                          bd=0, padx=14, pady=6, cursor="hand2",
                          command=lambda n=name: self._switch_view(n))
            b.grid(row=4+i, column=0, sticky="ew", padx=6)
            self._nav_btns[name] = b

        ttk.Separator(sb).grid(row=10, column=0, sticky="ew", pady=10)

        # path entries
        for row_off, (label, var, pick) in enumerate([
            ("3DSkit path",   self.kit_path,     self._pick_kit),
            ("ctrtool path",  self.ctrtool_path, self._pick_ctrtool),
        ]):
            tk.Label(sb, text=label, font=FL, bg=C["sidebar"],
                     fg=C["text3"]).grid(
                row=11+row_off*2, column=0, sticky="w", padx=18, pady=(6,0))
            pf = tk.Frame(sb, bg=C["sidebar"])
            pf.grid(row=12+row_off*2, column=0, sticky="ew", padx=10, pady=(0,2))
            pf.columnconfigure(0, weight=1)
            tk.Entry(pf, textvariable=var, font=FM, relief="flat",
                     bg=C["bg"], fg=C["text2"]).grid(
                row=0, column=0, sticky="ew", ipady=3)
            tk.Button(pf, text="…", font=FU, relief="flat", bg=C["bg"],
                      fg=C["text2"], cursor="hand2",
                      command=pick).grid(row=0, column=1, padx=(4,0))

        self._update_nav()

    def _build_main(self):
        main = tk.Frame(self, bg=C["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        tb = tk.Frame(main, bg=C["card"], height=48)
        tb.grid(row=0, column=0, columnspan=2, sticky="ew")
        tb.grid_propagate(False)
        tb.columnconfigure(1, weight=1)
        self._title_lbl = tk.Label(tb, text="Dump OST", font=FUB,
                                   bg=C["card"], fg=C["text"])
        self._title_lbl.grid(row=0, column=0, padx=20, sticky="w")
        self._flag_lbl = tk.Label(tb, text="ctrtool + 3DSkit",
                                  font=FM, bg=C["bg"], fg=C["text2"],
                                  padx=8, pady=2)
        self._flag_lbl.grid(row=0, column=1, sticky="w")
        tk.Frame(tb, bg=C["border"], height=1).grid(
            row=1, column=0, columnspan=3, sticky="ew")

        canvas = tk.Canvas(main, bg=C["bg"], highlightthickness=0)
        vsb = ttk.Scrollbar(main, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        canvas.grid(row=1, column=0, sticky="nsew")
        vsb.grid(row=1, column=1, sticky="ns")

        self._sf = tk.Frame(canvas, bg=C["bg"])
        self._cw = canvas.create_window((0,0), window=self._sf, anchor="nw")
        self._sf.bind("<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",
            lambda e: canvas.itemconfig(self._cw, width=e.width))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        f = self._sf
        f.columnconfigure(0, weight=1)
        self._build_file_card(f, 0)
        self._build_op_card(f, 1)
        self._build_options_card(f, 2)
        self._build_preview_card(f, 3)

        self._run_btn = tk.Button(
            f, text="▶  Run", font=("Sans",12,"bold"),
            bg=C["btn_bg"], fg=C["btn_fg"],
            activebackground="#333", activeforeground=C["btn_fg"],
            relief="flat", cursor="hand2", pady=10, command=self._run)
        self._run_btn.grid(row=4, column=0, sticky="ew", padx=20, pady=(0,12))

        self._build_terminal(f, 5)
        self._build_output_card(f, 6)

    # ── cards ─────────────────────────────────────────────────────────────────

    def _card(self, parent, row, title, pad=(0,12)):
        outer = tk.Frame(parent, bg=C["bg"])
        outer.grid(row=row, column=0, sticky="ew", padx=20, pady=pad)
        outer.columnconfigure(0, weight=1)
        frame = tk.Frame(outer, bg=C["card"],
                         highlightbackground=C["border"], highlightthickness=1)
        frame.grid(row=0, column=0, sticky="ew")
        frame.columnconfigure(0, weight=1)
        tk.Label(frame, text=title.upper(), font=("Sans",8,"bold"),
                 bg=C["card"], fg=C["text3"]).grid(
            row=0, column=0, sticky="w", padx=16, pady=(12,6))
        inner = tk.Frame(frame, bg=C["card"])
        inner.grid(row=1, column=0, sticky="ew", padx=14, pady=(0,14))
        inner.columnconfigure(0, weight=1)
        return inner

    def _build_file_card(self, parent, row):
        inner = self._card(parent, row, "Input Files", pad=(16,12))
        dz = tk.Frame(inner, bg=C["bg"],
                      highlightbackground=C["border"], highlightthickness=1)
        dz.grid(row=0, column=0, sticky="ew", pady=(0,8))
        dz.columnconfigure(0, weight=1)
        tk.Label(dz, text="Drop files here  or", font=FU,
                 bg=C["bg"], fg=C["text2"]).grid(row=0, column=0, pady=(14,4))
        tk.Button(dz, text="Browse files…", font=FU, bg=C["card"],
                  fg=C["accent"], relief="flat", cursor="hand2",
                  command=self._pick_files).grid(row=1, column=0, pady=(0,14))
        self._file_list = tk.Frame(inner, bg=C["card"])
        self._file_list.grid(row=1, column=0, sticky="ew")
        self._file_list.columnconfigure(0, weight=1)

    def _build_op_card(self, parent, row):
        inner = self._card(parent, row, "Operation")
        self._op_inner = inner
        self._op_btns: list[tk.Frame] = []

    def _refresh_ops(self):
        for w in self._op_inner.winfo_children(): w.destroy()
        self._op_btns.clear()
        ops = VIEWS[self.current_view.get()]["ops"]
        for i in range(min(len(ops),3)):
            self._op_inner.columnconfigure(i, weight=1)
        for i, (name, flag, desc) in enumerate(ops):
            f = tk.Frame(self._op_inner, bg=C["card"],
                         highlightbackground=C["border"],
                         highlightthickness=1, cursor="hand2")
            f.grid(row=0, column=i, sticky="nsew",
                   padx=(0, 4 if i < len(ops)-1 else 0))
            f.columnconfigure(0, weight=1)
            tk.Label(f, text=name, font=FUB, bg=C["card"],
                     fg=C["text"]).grid(row=0, column=0, sticky="w",
                                        padx=10, pady=(10,0))
            tk.Label(f, text=flag, font=FM, bg=C["card"],
                     fg=C["text3"]).grid(row=1, column=0, sticky="w", padx=10)
            tk.Label(f, text=desc, font=("Sans",9), bg=C["card"],
                     fg=C["text2"], wraplength=200,
                     justify="left").grid(row=2, column=0, sticky="w",
                                          padx=10, pady=(2,10))
            for w in (f, *f.winfo_children()):
                w.bind("<Button-1>", lambda e, idx=i: self._select_op(idx))
            self._op_btns.append(f)
        self._highlight_op()

    def _highlight_op(self):
        for i, f in enumerate(self._op_btns):
            sel = (i == self.selected_op)
            bg = C["sel_bg"] if sel else C["card"]
            bd = C["sel_bd"] if sel else C["border"]
            f.configure(bg=bg, highlightbackground=bd,
                        highlightthickness=2 if sel else 1)
            for w in f.winfo_children(): w.configure(bg=bg)

    def _build_options_card(self, parent, row):
        inner = self._card(parent, row, "Options")
        inner.columnconfigure((0,1), weight=1)

        tk.Label(inner, text="Output directory", font=FL,
                 bg=C["card"], fg=C["text2"]).grid(row=0, column=0, sticky="w")
        od = tk.Frame(inner, bg=C["card"])
        od.grid(row=1, column=0, sticky="ew", padx=(0,8), pady=(2,10))
        od.columnconfigure(0, weight=1)
        tk.Entry(od, textvariable=self.out_dir, font=FU,
                 relief="flat", bg=C["bg"]).grid(
            row=0, column=0, sticky="ew", ipady=4)
        tk.Button(od, text="…", font=FU, relief="flat", bg=C["bg"],
                  fg=C["text2"], cursor="hand2",
                  command=self._pick_outdir).grid(row=0, column=1, padx=(4,0))

        tk.Label(inner, text="Output format", font=FL,
                 bg=C["card"], fg=C["text2"]).grid(row=0, column=1, sticky="w")
        ttk.Combobox(inner, textvariable=self.fmt_var,
                     values=["auto-detect","wav","bcstm","bcwav","bfstm","brstm"],
                     state="readonly", font=FU, width=14).grid(
            row=1, column=1, sticky="w", pady=(2,10))

        tf = tk.Frame(inner, bg=C["card"])
        tf.grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(tf, text=" Verbose (-v)", variable=self.verbose,
                        command=self._update_preview).pack(side="left", padx=(0,20))
        ttk.Checkbutton(tf, text=" Big-endian (-B)", variable=self.bigendian,
                        command=self._update_preview).pack(side="left")

    def _build_preview_card(self, parent, row):
        inner = self._card(parent, row, "Command Preview")
        self._preview_lbl = tk.Label(inner, text="", font=FM,
            bg=C["bg"], fg=C["text2"], anchor="w", justify="left",
            wraplength=720, padx=10, pady=8)
        self._preview_lbl.grid(row=0, column=0, sticky="ew")

    def _build_terminal(self, parent, row):
        outer = tk.Frame(parent, bg=C["bg"])
        outer.grid(row=row, column=0, sticky="ew", padx=20, pady=(0,12))
        outer.columnconfigure(0, weight=1)
        tc = tk.Frame(outer, bg=C["term_bg"])
        tc.grid(row=0, column=0, sticky="ew")
        tc.columnconfigure(0, weight=1)
        tbar = tk.Frame(tc, bg="#1a1a1a")
        tbar.grid(row=0, column=0, sticky="ew")
        for col in ("#E24B4A","#EF9F27","#639922"):
            tk.Label(tbar, text="●", fg=col, bg="#1a1a1a",
                     font=("Sans",9)).pack(side="left", padx=(6,0), pady=4)
        tk.Label(tbar, text="terminal", font=FM,
                 bg="#1a1a1a", fg="#555").pack(side="left", padx=10)
        self._term = scrolledtext.ScrolledText(
            tc, height=14, font=FM, bg=C["term_bg"], fg=C["term_fg"],
            insertbackground=C["term_fg"], relief="flat",
            state="disabled", wrap="word")
        self._term.grid(row=1, column=0, sticky="ew", padx=2, pady=(0,2))
        for tag, fg in [
            ("info",C["accent"]),("success",C["green"]),
            ("warn",C["amber"]),("err",C["red"]),
            ("dim","#555"),("prompt","#666"),("out","#aaa"),
        ]:
            self._term.tag_configure(tag, foreground=fg)
        self._tlog("Ready. Add a .cia or .3ds file and hit Run.\n","dim")

    def _build_output_card(self, parent, row):
        self._out_card = self._card(parent, row, "Output Files")
        tk.Label(self._out_card, text="Output will appear here after running.",
                 font=FU, bg=C["card"], fg=C["text3"]).grid(
            row=0, column=0, pady=10)

    # ── actions ───────────────────────────────────────────────────────────────

    def _switch_view(self, name):
        self.current_view.set(name)
        self.selected_op = 0
        self._title_lbl.configure(text=name)
        self._flag_lbl.configure(text=VIEWS[name]["flag"])
        self._refresh_ops()
        self._update_nav()
        self._update_preview()

    def _update_nav(self):
        cur = self.current_view.get()
        for name, btn in self._nav_btns.items():
            if name == cur:
                btn.configure(bg=C["bg"], fg=C["text"], font=FUB)
            else:
                btn.configure(bg=C["sidebar"], fg=C["text2"], font=FU)

    def _select_op(self, idx):
        self.selected_op = idx
        self._highlight_op()
        self._update_preview()

    def _pick_files(self):
        paths = filedialog.askopenfilenames(
            title="Select 3DS files",
            filetypes=[
                ("3DS files","*.cia *.3ds *.bcstm *.bcwav *.bcsar *.romfs *.bin"),
                ("All files","*.*"),
            ])
        for p in paths:
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
        self._render_files()
        self._update_preview()

    def _remove_file(self, path):
        self.files.remove(path)
        self._render_files()
        self._update_preview()

    def _render_files(self):
        for w in self._file_list.winfo_children(): w.destroy()
        for path in self.files:
            row = tk.Frame(self._file_list, bg=C["bg"],
                           highlightbackground=C["border"], highlightthickness=1)
            row.grid(sticky="ew", pady=2)
            row.columnconfigure(1, weight=1)
            ext = path.suffix.lower()
            ec = EXT_COLORS.get(ext, ("#F1EFE8","#444441"))
            tk.Label(row, text=ext.upper().lstrip(".")[:5] or "?",
                     font=("Monospace",8,"bold"),
                     bg=ec[0], fg=ec[1], padx=6, pady=2).grid(
                row=0, column=0, padx=(6,8), pady=4)
            tk.Label(row, text=path.name, font=FU, bg=C["bg"],
                     fg=C["text"], anchor="w").grid(row=0, column=1, sticky="ew")
            size_str = fmt_size(path.stat().st_size) if path.exists() else "?"
            tk.Label(row, text=size_str, font=FM,
                     bg=C["bg"], fg=C["text3"]).grid(row=0, column=2, padx=8)
            tk.Button(row, text="✕", font=("Sans",9), relief="flat",
                      bg=C["bg"], fg=C["text3"], cursor="hand2",
                      command=lambda p=path: self._remove_file(p)).grid(
                row=0, column=3, padx=(0,6))

    def _pick_outdir(self):
        d = filedialog.askdirectory(title="Select output directory")
        if d:
            self.out_dir.set(d)
            self._update_preview()

    def _pick_kit(self):
        p = filedialog.askopenfilename(title="Locate 3DSkit.py",
            filetypes=[("Python script","*.py"),("All","*.*")])
        if p: self.kit_path.set(p)

    def _pick_ctrtool(self):
        p = filedialog.askopenfilename(title="Locate ctrtool binary")
        if p: self.ctrtool_path.set(p)

    def _get_ctrtool(self):
        p = self.ctrtool_path.get()
        if p and Path(p).exists(): return p
        w = shutil.which("ctrtool")
        if w: return w
        if CTRTOOL_BIN.exists(): return str(CTRTOOL_BIN)
        return None

    def _build_cmd(self) -> list[str]:
        view = VIEWS[self.current_view.get()]
        flag = view["ops"][self.selected_op][1]
        if flag.startswith("CTRTOOL"):
            return ["<ctrtool pipeline>"]
        parts = [PYTHON, self.kit_path.get()]
        parts += flag.split()
        if self.verbose.get(): parts.append("-v")
        if self.bigendian.get(): parts.append("-B")
        fmt = self.fmt_var.get()
        if fmt != "auto-detect": parts += ["-f", fmt]
        parts += ["-o", str(Path(self.out_dir.get()).resolve())]
        for p in self.files: parts.append(str(p.resolve()))
        return parts

    def _update_preview(self):
        view = VIEWS[self.current_view.get()]
        flag = view["ops"][self.selected_op][1]
        if flag.startswith("CTRTOOL"):
            files_str = ", ".join(p.name for p in self.files) or "no file"
            self._preview_lbl.configure(
                text=f"[1] ctrtool --romfsdir=<out> <file>  "
                     f"[2] 3DSkit -g BCSTM/BCWAV -o <out>/wav  |  {files_str}")
        else:
            self._preview_lbl.configure(text=" ".join(self._build_cmd()))

    # ── run ───────────────────────────────────────────────────────────────────

    def _run(self):
        if not self.files:
            messagebox.showwarning("No files", "Add at least one input file.")
            return

        view  = VIEWS[self.current_view.get()]
        flag  = view["ops"][self.selected_op][1]
        kit   = self.kit_path.get()
        ctrt  = self._get_ctrtool()

        if flag.startswith("CTRTOOL") or flag == "CTRTOOL_ROMFS":
            if not ctrt:
                messagebox.showerror("ctrtool not found",
                    "ctrtool was not found.\n"
                    "Restart the GUI to auto-download it, or set the path manually.")
                return
        if flag in ("-g","-x","-D"):
            if not kit or not Path(kit).exists():
                messagebox.showerror("3DSkit not found",
                    f"3DSkit.py not found.\nSet the path in the sidebar.")
                return

        Path(self.out_dir.get()).mkdir(parents=True, exist_ok=True)
        self._term.configure(state="normal")
        self._term.delete("1.0","end")
        self._term.configure(state="disabled")
        self._run_btn.configure(state="disabled", text="Running…")
        for w in self._out_card.winfo_children(): w.destroy()

        if flag in ("CTRTOOL_AUTO","CTRTOOL_AUDIO"):
            threading.Thread(target=self._pipeline,
                             args=(ctrt, kit), daemon=True).start()
        elif flag == "CTRTOOL_ROMFS":
            threading.Thread(target=self._ctrtool_only,
                             args=(ctrt,), daemon=True).start()
        else:
            cmd = self._build_cmd()
            self._tlog("$ " + " ".join(cmd) + "\n","prompt")
            threading.Thread(target=self._exec, args=(cmd,), daemon=True).start()

    # ── pipeline ──────────────────────────────────────────────────────────────

    def _pipeline(self, ctrtool, kit):
        out_root = Path(self.out_dir.get()).resolve()

        for rom in self.files:
            rom     = rom.resolve()
            rom_out = out_root / rom.stem
            rom_out.mkdir(parents=True, exist_ok=True)

            # step 1 — ctrtool RomFS extract
            self._tlog(f"\n━━ {rom.name} ━━\n","info")
            self._tlog(f"[1/2] Extracting RomFS with ctrtool…\n","info")
            rom_out.mkdir(parents=True, exist_ok=True)
            # -p = plain (no decrypt attempt), -n 0 = NCCH partition 0
            cmd = [ctrtool, "-p", "-n", "0", f"--romfsdir={rom_out}", str(rom)]
            self._tlog("$ " + " ".join(cmd) + "\n","prompt")
            ok = self._run_stream(cmd)
            # ctrtool sometimes exits 0 even on partial errors; check if files were written
            has_files = any(rom_out.rglob("*"))
            if not ok and not has_files:
                self._tlog("✗ ctrtool failed — see errors above.\n","err")
                continue
            elif not has_files:
                self._tlog("⚠ ctrtool ran but wrote no files — ROM may be encrypted.\n","warn")
                continue

            # step 2 — find audio and convert
            audio = []
            for pat in ("*.bcstm","*.BCSTM","*.bcwav","*.BCWAV"):
                audio += list(rom_out.rglob(pat))

            if not audio:
                self._tlog("⚠ No BCSTM/BCWAV files found in extracted RomFS.\n","warn")
                continue

            wav_out = rom_out / "wav"
            wav_out.mkdir(exist_ok=True)
            self._tlog(f"[2/2] Converting {len(audio)} audio file(s) → WAV…\n","info")

            for af in audio:
                plugin = "BCSTM" if af.suffix.lower() == ".bcstm" else "BCWAV"
                cmd = [PYTHON, kit, "-g", plugin, "-o", str(wav_out), str(af)]
                self._tlog("$ " + " ".join(cmd) + "\n","prompt")
                self._run_stream(cmd)

            self._tlog(f"\n✓ WAVs saved to {wav_out}\n","success")

        self.after(0, self._show_output)
        self.after(0, lambda: self._run_btn.configure(
            state="normal", text="▶  Run again"))

    def _ctrtool_only(self, ctrtool):
        out_root = Path(self.out_dir.get()).resolve()
        for rom in self.files:
            rom     = rom.resolve()
            rom_out = out_root / rom.stem
            rom_out.mkdir(parents=True, exist_ok=True)
            self._tlog(f"\n━━ {rom.name} ━━\n","info")
            rom_out.mkdir(parents=True, exist_ok=True)
            # -p = plain (no decrypt attempt), -n 0 = NCCH partition 0
            cmd = [ctrtool, "-p", "-n", "0", f"--romfsdir={rom_out}", str(rom)]
            self._tlog("$ " + " ".join(cmd) + "\n","prompt")
            self._run_stream(cmd)
        self._tlog("\n✓ Done.\n","success")
        self.after(0, self._show_output)
        self.after(0, lambda: self._run_btn.configure(
            state="normal", text="▶  Run again"))

    def _run_stream(self, cmd) -> bool:
        try:
            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1)
            def read(stream, dtag):
                for line in stream:
                    line = line.rstrip()
                    if not line: continue
                    ll = line.lower()
                    t = dtag
                    if any(x in ll for x in
                           ("error","traceback","exception","unrecognized","no such")):
                        t = "err"
                    elif "warning" in ll: t = "warn"
                    elif any(x in ll for x in
                             ("done","success","complete","saving","wrote")): t = "success"
                    elif any(x in ll for x in
                             ("[","reading","writing","extracting","converting",
                              "parsing","dumping")): t = "info"
                    self._tlog(line+"\n", t)
            t1 = threading.Thread(target=read, args=(proc.stdout,"out"), daemon=True)
            t2 = threading.Thread(target=read, args=(proc.stderr,"err"), daemon=True)
            t1.start(); t2.start(); t1.join(); t2.join()
            proc.wait()
            return proc.returncode == 0
        except Exception as e:
            self._tlog(f"✗ {e}\n","err")
            return False

    def _exec(self, cmd):
        ok = self._run_stream(cmd)
        if ok:
            self._tlog("\n✓ Finished successfully.\n","success")
            self.after(0, self._show_output)
        else:
            self._tlog("\n✗ Process failed.\n","err")
        self.after(0, lambda: self._run_btn.configure(
            state="normal", text="▶  Run again"))

    def _tlog(self, text, tag="out"):
        def _w():
            self._term.configure(state="normal")
            self._term.insert("end", text, tag)
            self._term.see("end")
            self._term.configure(state="disabled")
        self.after(0, _w)

    def _show_output(self):
        out = Path(self.out_dir.get())
        if not out.exists(): return
        # prefer WAV files, fall back to all files
        files = sorted(out.rglob("*.wav"))[:40]
        if not files:
            files = sorted(out.iterdir(),
                           key=lambda p: (p.is_file(), p.name))[:20]
        if not files: return
        for w in self._out_card.winfo_children(): w.destroy()
        self._out_card.columnconfigure(tuple(range(4)), weight=1)
        for i, path in enumerate(files):
            col, row = i%4, i//4
            cell = tk.Frame(self._out_card, bg=C["bg"],
                            highlightbackground=C["border"],
                            highlightthickness=1, cursor="hand2")
            cell.grid(row=row, column=col, sticky="nsew",
                      padx=3, pady=3, ipadx=8, ipady=6)
            icon = ("🎵" if path.suffix in (".wav",".bcstm",".bcwav")
                    else "📂" if path.is_dir() else "📄")
            tk.Label(cell, text=icon, font=("Sans",16),
                     bg=C["bg"]).pack()
            tk.Label(cell, text=path.name, font=("Monospace",9),
                     bg=C["bg"], fg=C["text"],
                     wraplength=130, justify="center").pack()
            size_str = fmt_size(path.stat().st_size) if path.is_file() else "dir"
            tk.Label(cell, text=size_str, font=FL,
                     bg=C["bg"], fg=C["text3"]).pack()
            cell.bind("<Button-1>",
                lambda e, p=path: os.system(f'xdg-open "{p.parent}"'))


def main():
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()