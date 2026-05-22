#!/usr/bin/env python3
"""
Social Video Downloader
Download videos from Twitter/X and Instagram using yt-dlp
Requirements: python3.11 -m pip install yt-dlp && brew install ffmpeg
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess
import os
from datetime import datetime

# ── Palette ───────────────────────────────────────────────────────────────────
BG       = "#0f0f0f"
SURFACE  = "#1a1a1a"
SURFACE2 = "#242424"
BORDER   = "#2e2e2e"
ACCENT   = "#00e5ff"
ACCENT2  = "#ff4081"
TEXT     = "#f0f0f0"
TEXT_DIM = "#707070"
SUCCESS  = "#00e676"
ERROR    = "#ff5252"
WARNING  = "#ffab40"
MONO     = ("Menlo", 11)
UI       = ("Helvetica Neue", 12)
TITLE    = ("Helvetica Neue", 20, "bold")
SMALL    = ("Helvetica Neue", 10)


YTDLP_PATHS = [
    "yt-dlp",
    os.path.expanduser("~/yt-dlp"),
    "/opt/homebrew/bin/yt-dlp",
    "/usr/local/bin/yt-dlp",
]

def find_ytdlp():
    for path in YTDLP_PATHS:
        try:
            subprocess.run([path, "--version"], capture_output=True, check=True)
            return path
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return None

def check_ytdlp():
    return find_ytdlp() is not None


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Social Video Downloader")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(640, 600)

        self.download_folder = os.path.expanduser("~/Downloads/SocialVideos")
        self.is_downloading = False
        self._process = None
        self._ytdlp_bin = find_ytdlp()  # cached once at startup

        self._build()
        self._center()

    def _center(self):
        self.update_idletasks()
        w, h = 700, 720
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Bottom bar packed FIRST so it's never clipped ──
        bottom = tk.Frame(self, bg=SURFACE2, pady=14)
        bottom.pack(side="bottom", fill="x")

        self.stop_btn = tk.Button(
            bottom, text="⏹  Parar",
            font=(UI[0], 12, "bold"), bg=ACCENT2, fg="white",
            relief="flat", padx=18, pady=10, cursor="hand2",
            activebackground="#c2185b", activeforeground="white",
            command=self._stop, state="disabled"
        )
        self.stop_btn.pack(side="right", padx=(0, 20))

        self.dl_btn = tk.Button(
            bottom, text="⬇   Baixar Vídeos",
            font=(UI[0], 13, "bold"), bg=ACCENT, fg=BG,
            relief="flat", padx=28, pady=10, cursor="hand2",
            activebackground="#00b8d4", activeforeground=BG,
            command=self._start
        )
        self.dl_btn.pack(side="right", padx=(0, 8))

        self.clear_btn = tk.Button(
            bottom, text="Limpar",
            font=UI, bg=SURFACE, fg=TEXT_DIM,
            relief="flat", padx=16, pady=10, cursor="hand2",
            activebackground=BORDER, activeforeground=TEXT,
            command=self._clear
        )
        self.clear_btn.pack(side="left", padx=(20, 0))

        # ── Main content ──
        main = tk.Frame(self, bg=BG)
        main.pack(side="top", fill="both", expand=True, padx=24, pady=(20, 0))

        # Header
        hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill="x", pady=(0, 16))
        tk.Label(hdr, text="⬇", font=("Helvetica Neue", 26), bg=BG, fg=ACCENT).pack(side="left", padx=(0, 10))
        blk = tk.Frame(hdr, bg=BG)
        blk.pack(side="left")
        tk.Label(blk, text="Social Video Downloader", font=TITLE, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(blk, text="Twitter/X  ·  Instagram", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")

        # yt-dlp warning
        if not self._ytdlp_bin:
            wf.pack(fill="x", pady=(0, 10))
            tk.Label(wf, text="⚠  yt-dlp não encontrado — rode: brew install yt-dlp ffmpeg",
                     font=SMALL, bg="#2a1a00", fg=WARNING, padx=12).pack(anchor="w")

        # Links
        self._sep(main, "LINKS")
        lf = tk.Frame(main, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        lf.pack(fill="x", pady=(4, 0))
        self.links_box = tk.Text(
            lf, height=9, font=MONO,
            bg=SURFACE, fg=TEXT, insertbackground=ACCENT,
            relief="flat", padx=12, pady=10, wrap="word", spacing1=2,
            selectbackground=ACCENT, selectforeground=BG
        )
        self.links_box.pack(side="left", fill="both", expand=True)
        self.links_box.insert("1.0", "# Cole os links aqui, um por linha\n# Linhas com # são ignoradas\n\n")
        self.links_box.bind("<FocusIn>", self._clear_hint)
        sb = tk.Scrollbar(lf, command=self.links_box.yview, bg=SURFACE2, troughcolor=SURFACE)
        sb.pack(side="right", fill="y")
        self.links_box.configure(yscrollcommand=sb.set)
        tk.Label(main, text="Um link por linha  ·  Twitter/X e Instagram suportados",
                 font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(4, 12))

        # Options
        self._sep(main, "OPÇÕES")
        opts = tk.Frame(main, bg=BG)
        opts.pack(fill="x", pady=(4, 12))

        qf = tk.Frame(opts, bg=BG)
        qf.pack(side="left", fill="x", expand=True, padx=(0, 12))
        tk.Label(qf, text="Qualidade", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")
        self.quality = tk.StringVar(value="Melhor disponível")
        ttk.Combobox(qf, textvariable=self.quality, state="readonly", font=UI, width=24,
                     values=["Melhor disponível","1080p","720p","480p","Apenas áudio (mp3)"]).pack(fill="x", pady=(4,0))

        ff = tk.Frame(opts, bg=BG)
        ff.pack(side="left", padx=(0, 12))
        tk.Label(ff, text="Formato", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")
        self.fmt = tk.StringVar(value="mp4")
        ttk.Combobox(ff, textvariable=self.fmt, state="readonly", font=UI, width=8,
                     values=["mp4","mkv","webm","mov"]).pack(fill="x", pady=(4,0))

        cf = tk.Frame(opts, bg=BG)
        cf.pack(side="left")
        tk.Label(cf, text="Cookies (Instagram)", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")
        self.cookies = tk.StringVar(value="safari")
        ttk.Combobox(cf, textvariable=self.cookies, state="readonly", font=UI, width=10,
                     values=["chrome","safari","firefox","edge","nenhum"]).pack(fill="x", pady=(4,0))

        # Folder
        self._sep(main, "PASTA DE DESTINO")
        fr = tk.Frame(main, bg=BG)
        fr.pack(fill="x", pady=(4, 12))
        self.folder_lbl = tk.Label(
            fr, text=self.download_folder, font=("Menlo", 10),
            bg=SURFACE, fg=ACCENT, padx=12, pady=8, anchor="w",
            highlightbackground=BORDER, highlightthickness=1
        )
        self.folder_lbl.pack(side="left", fill="x", expand=True)
        tk.Button(fr, text="Escolher", font=SMALL, bg=SURFACE2, fg=TEXT,
                  relief="flat", padx=12, pady=8, cursor="hand2",
                  activebackground=BORDER, command=self._pick_folder).pack(side="left", padx=(8,0))

        # Log
        self._sep(main, "LOG")
        lf2 = tk.Frame(main, bg=SURFACE, highlightbackground=BORDER, highlightthickness=1)
        lf2.pack(fill="both", expand=True, pady=(4, 12))
        self.log = tk.Text(
            lf2, font=("Menlo", 10), bg=SURFACE, fg=TEXT_DIM,
            relief="flat", padx=12, pady=8, state="disabled", wrap="word", spacing1=2
        )
        self.log.pack(fill="both", expand=True)
        self.log.tag_configure("ok",   foreground=SUCCESS)
        self.log.tag_configure("err",  foreground=ERROR)
        self.log.tag_configure("info", foreground=ACCENT)
        self.log.tag_configure("warn", foreground=WARNING)

        # Progress
        s = ttk.Style(); s.theme_use("clam")
        s.configure("C.Horizontal.TProgressbar",
                    troughcolor=SURFACE2, background=ACCENT,
                    darkcolor=ACCENT, lightcolor=ACCENT,
                    bordercolor=SURFACE2, thickness=4)
        self.prog = ttk.Progressbar(main, style="C.Horizontal.TProgressbar", mode="indeterminate")
        self.prog.pack(fill="x", pady=(0, 4))

    def _sep(self, parent, label):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        tk.Label(row, text=label, font=("Menlo", 9, "bold"), bg=BG, fg=TEXT_DIM).pack(side="left")
        tk.Frame(row, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(8,0), pady=6)

    # ── Actions ───────────────────────────────────────────────────────────────
    def _clear_hint(self, _=None):
        if self.links_box.get("1.0", "end-1c").strip().startswith("# Cole os links"):
            self.links_box.delete("1.0", "end")

    def _pick_folder(self):
        f = filedialog.askdirectory(title="Pasta de destino")
        if f:
            self.download_folder = f
            self.folder_lbl.configure(text=f)

    def _clear(self):
        self.links_box.delete("1.0", "end")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _write_log(self, msg, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _get_links(self):
        return [l.strip() for l in self.links_box.get("1.0","end-1c").splitlines()
                if l.strip() and not l.strip().startswith("#")]

    def _ytdlp_args(self, url):
        q   = self.quality.get()
        fmt = self.fmt.get()
        out = os.path.join(self.download_folder, "%(uploader)s - %(title).60s.%(ext)s")
        browser = self.cookies.get()
        args = [self._ytdlp_bin, "--no-playlist", "-o", out]
        args += ["--recode-video", "mp4"]
        args += ["--postprocessor-args", "ffmpeg:-c:v libx264 -c:a aac -movflags +faststart"]
        if browser != "nenhum":
            args += ["--cookies-from-browser", browser]
        if q == "Apenas áudio (mp3)":
            args += ["-x", "--audio-format", "mp3"]
        elif q == "1080p":
            args += ["-f", "bestvideo[height<=1080]+bestaudio/best[height<=1080]"]
        elif q == "720p":
            args += ["-f", "bestvideo[height<=720]+bestaudio/best[height<=720]"]
        elif q == "480p":
            args += ["-f", "bestvideo[height<=480]+bestaudio/best[height<=480]"]
        else:
            args += ["-f", "bestvideo+bestaudio/best"]
        args.append(url)
        return args

    def _set_ui(self, downloading):
        self.dl_btn.configure(state="disabled" if downloading else "normal")
        self.stop_btn.configure(state="normal" if downloading else "disabled")
        self.clear_btn.configure(state="disabled" if downloading else "normal")

    def _start(self):
        links = self._get_links()
        if not links:
            messagebox.showwarning("Sem links", "Cole pelo menos um link antes de baixar.")
            return
        if not self._ytdlp_bin:
            messagebox.showerror("yt-dlp não encontrado",
                                 "Instale com:\nbrew install yt-dlp ffmpeg")
            return
        os.makedirs(self.download_folder, exist_ok=True)
        self.is_downloading = True
        self._set_ui(True)
        self.prog.start(12)
        self.log.configure(state="normal"); self.log.delete("1.0","end"); self.log.configure(state="disabled")
        self._write_log(f"Iniciando {len(links)} download(s)...", "info")
        threading.Thread(target=self._worker, args=(links,), daemon=True).start()

    def _stop(self):
        self.is_downloading = False
        if self._process:
            self._process.terminate()
        self._write_log("Interrompido pelo usuário.", "warn")

    def _worker(self, links):
        ok = fail = 0
        for i, url in enumerate(links, 1):
            if not self.is_downloading:
                break
            self.after(0, lambda u=url, idx=i, t=len(links):
                       self._write_log(f"({idx}/{t}) {u}", "info"))
            try:
                self._process = subprocess.Popen(
                    self._ytdlp_args(url),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                )
                for line in self._process.stdout:
                    line = line.strip()
                    if line and ("[download]" in line or "[Merger]" in line or "[ffmpeg]" in line):
                        self.after(0, lambda l=line: self._write_log(l))
                self._process.wait()
                if self._process.returncode == 0:
                    self.after(0, lambda: self._write_log("✓ Concluído", "ok"))
                    ok += 1
                else:
                    self.after(0, lambda c=self._process.returncode:
                               self._write_log(f"✗ Falha (código {c})", "err"))
                    fail += 1
            except Exception as e:
                self.after(0, lambda e=e: self._write_log(f"✗ Erro: {e}", "err"))
                fail += 1

        def done():
            self.is_downloading = False
            self.prog.stop()
            self._set_ui(False)
            tag = "ok" if fail == 0 else "warn"
            self._write_log(f"─── {ok} baixado(s) · {fail} falha(s) ───", tag)
            if ok > 0 and fail == 0:
                messagebox.showinfo("Concluído", f"{ok} vídeo(s) em:\n{self.download_folder}")
            elif fail > 0:
                messagebox.showwarning("Parcial", f"{ok} ok, {fail} falha(s). Veja o log.")

        self.after(0, done)


if __name__ == "__main__":
    App().mainloop()
