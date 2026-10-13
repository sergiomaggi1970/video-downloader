#!/usr/bin/env python3
"""
Social Video Downloader
Ferramenta dedicada ao YouTube (também aceita Instagram, X e TikTok) usando yt-dlp.

yt-dlp (nightly) e deno são baixados automaticamente quando não encontrados.
ffmpeg/ffprobe: embutidos no executável do Windows; no Mac use `brew install ffmpeg`.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import zipfile
from datetime import datetime, date
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

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

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"

YTDLP_NIGHTLY_URL = {
    "win": "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp.exe",
    "mac": "https://github.com/yt-dlp/yt-dlp-nightly-builds/releases/latest/download/yt-dlp_macos",
}
DENO_BASE_URL = "https://github.com/denoland/deno/releases/latest/download/"

Q_BEST = "Melhor (até 1080p, rápido)"
Q_MAX = "Máxima (4K, mais lento)"
Q_AUDIO = "Apenas áudio (mp3)"

YT_RETRY_ARGS = [
    [],
    ["--extractor-args", "youtube:player_client=android"],
    ["--extractor-args", "youtube:player_client=visionos,web_embedded,mweb"],
]


# ── Plataforma / pastas ───────────────────────────────────────────────────────
def app_dir():
    """Pasta do executável (ou do script, quando rodando do código-fonte)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    if IS_WIN:
        base = os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), "AppData", "Local")
        return os.path.join(base, "SocialVideoDownloader")
    return os.path.join(os.path.expanduser("~"), ".social-video-downloader")


def tools_dir():
    return os.path.join(data_dir(), "bin")


def config_path():
    return os.path.join(data_dir(), "config.json")


def load_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass


def setup_environment():
    """PATH ampliado: apps GUI no Mac não herdam o PATH do shell; no Windows usa o ffmpeg embutido."""
    extra = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        extra.append(sys._MEIPASS)
    if IS_MAC:
        extra += ["/opt/homebrew/bin", "/usr/local/bin"]
    cur = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(extra + ([cur] if cur else []))


def _proc_kwargs():
    kw = {}
    if IS_WIN:
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _env():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_quiet(cmd, timeout=60):
    return subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, env=_env(), **_proc_kwargs()
    )


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    if IS_WIN:
        os.startfile(path)  # noqa: S606
    elif IS_MAC:
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


# ── Localização de ferramentas ────────────────────────────────────────────────
class ToolError(Exception):
    """Falha ao preparar uma ferramenta; `folder` é a pasta onde ela deve ficar."""
    def __init__(self, message, folder=None):
        super().__init__(message)
        self.folder = folder


def _works(path, arg="--version"):
    try:
        return run_quiet([path, arg], timeout=30).returncode == 0
    except Exception:
        return False


def _first_working(candidates):
    for path in candidates:
        if path and os.path.isfile(path) and _works(path):
            return path
    return None


def find_ytdlp():
    name = "yt-dlp.exe" if IS_WIN else "yt-dlp"
    if IS_WIN:
        cands = [os.path.join(tools_dir(), name), os.path.join(app_dir(), name)]
    else:
        cands = [os.path.join(app_dir(), name), os.path.expanduser("~/yt-dlp")]
    found = _first_working(cands)
    if found:
        return found
    on_path = shutil.which("yt-dlp")
    if on_path and _works(on_path):
        return on_path
    return None


def find_deno():
    name = "deno.exe" if IS_WIN else "deno"
    if IS_WIN:
        cands = [os.path.join(tools_dir(), name), os.path.join(app_dir(), name)]
    else:
        cands = [
            os.path.join(app_dir(), name),
            os.path.expanduser("~/.deno/bin/deno"),
            "/opt/homebrew/bin/deno",
        ]
    found = _first_working(cands)
    if found:
        return found
    on_path = shutil.which("deno")
    if on_path and _works(on_path):
        return on_path
    return _first_working([os.path.join(tools_dir(), name)])   # baixado pelo próprio app


def find_media_tool(name):
    """ffmpeg / ffprobe: embutido no Windows (sys._MEIPASS), PATH no Mac."""
    exe = name + (".exe" if IS_WIN else "")
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        p = os.path.join(sys._MEIPASS, exe)
        if os.path.isfile(p):
            return p
    return shutil.which(name)


# ── Download de ferramentas ───────────────────────────────────────────────────
def download_file(url, dest, log):
    """Baixa url → dest, com progresso no log. Cai para curl se o SSL do Python falhar."""
    name = os.path.basename(dest)
    folder = os.path.dirname(dest)
    tmp = dest + ".download"
    os.makedirs(folder, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SocialVideoDownloader"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done, next_pct = 0, 20
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total and done * 100 // total >= next_pct:
                    log(f"Baixando {name}… {done * 100 // total}%")
                    next_pct += 20
    except Exception as e:
        curl = shutil.which("curl")
        if not curl:
            raise ToolError(f"Não foi possível baixar {name}: {e}. Baixe manualmente em {url} e coloque em {folder}.", folder)
        log(f"Download direto falhou ({e}); tentando via curl…")
        r = subprocess.run([curl, "-L", "--fail", "-sS", "-o", tmp, url],
                           capture_output=True, text=True, **_proc_kwargs())
        if r.returncode != 0:
            raise ToolError(f"Não foi possível baixar {name}: {r.stderr.strip()}. "
                            f"Baixe manualmente em {url} e coloque em {folder}.", folder)
    os.replace(tmp, dest)


def verify_tool(path, url):
    """Arquivo existe, > 1 MB e executa --version; senão explica (Defender)."""
    name = os.path.basename(path)
    folder = os.path.dirname(path)
    if os.path.isfile(path) and os.path.getsize(path) > 1024 * 1024 and _works(path):
        return
    if IS_WIN:
        msg = (f"O Windows Defender pode ter bloqueado {name}. Libere em Segurança do Windows → "
               f"Proteção contra vírus e ameaças → Histórico de proteção, ou baixe manualmente em "
               f"{url} e coloque em {folder}.")
    else:
        msg = (f"Não foi possível executar {name}. Um antivírus pode tê-lo bloqueado. "
               f"Baixe manualmente em {url} e coloque em {folder}.")
    raise ToolError(msg, folder)


def ensure_ytdlp(log):
    found = find_ytdlp()
    if found:
        return found
    if IS_WIN:
        url, dest = YTDLP_NIGHTLY_URL["win"], os.path.join(tools_dir(), "yt-dlp.exe")
    elif IS_MAC:
        url, dest = YTDLP_NIGHTLY_URL["mac"], os.path.expanduser("~/yt-dlp")
    else:
        raise ToolError("yt-dlp não encontrado. Instale-o e deixe-o no PATH.")
    log("yt-dlp não encontrado — baixando a versão nightly…")
    download_file(url, dest, log)
    if not IS_WIN:
        os.chmod(dest, 0o755)
    verify_tool(dest, url)
    log("yt-dlp instalado.")
    return dest


def deno_asset():
    if IS_WIN:
        return "deno-x86_64-pc-windows-msvc.zip"
    if IS_MAC:
        arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
        return f"deno-{arch}-apple-darwin.zip"
    return "deno-x86_64-unknown-linux-gnu.zip"


def ensure_deno(log):
    found = find_deno()
    if found:
        return found
    asset = deno_asset()
    url = DENO_BASE_URL + asset
    folder = tools_dir()
    exe = "deno.exe" if IS_WIN else "deno"
    dest = os.path.join(folder, exe)
    log("deno não encontrado — baixando o runtime JavaScript…")
    zpath = os.path.join(folder, asset)
    download_file(url, zpath, log)
    try:
        with zipfile.ZipFile(zpath) as z:
            member = next((n for n in z.namelist() if os.path.basename(n) == exe), None)
            if not member:
                raise ToolError(f"{asset} não contém {exe}.", folder)
            with z.open(member) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out)
    except zipfile.BadZipFile:
        raise ToolError(f"Arquivo {asset} corrompido. Baixe manualmente em {url} e coloque em {folder}.", folder)
    finally:
        try:
            os.remove(zpath)
        except OSError:
            pass
    if not IS_WIN:
        os.chmod(dest, 0o755)
    verify_tool(dest, url)
    log("deno instalado.")
    return dest


def ytdlp_version(ytdlp):
    try:
        r = run_quiet([ytdlp, "--version"], timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def update_due(cfg, today=None):
    return cfg.get("last_ytdlp_update") != (today or date.today().isoformat())


def update_ytdlp(ytdlp, log):
    """yt-dlp --update-to nightly; registra o resultado no log. True se concluiu sem erro."""
    before = ytdlp_version(ytdlp)
    log("Verificando atualização do yt-dlp (nightly)…")
    try:
        r = run_quiet([ytdlp, "--update-to", "nightly"], timeout=300)
    except Exception as e:
        log(f"Não foi possível atualizar o yt-dlp: {e}", "warn")
        return False
    if r.returncode != 0:
        lines = [l for l in (r.stdout + "\n" + r.stderr).splitlines() if l.strip()]
        log(f"Não foi possível atualizar o yt-dlp: {lines[-1] if lines else 'erro desconhecido'}", "warn")
        return False
    after = ytdlp_version(ytdlp)
    if after and after != before:
        log(f"yt-dlp atualizado para {after}", "ok")
    else:
        log("yt-dlp já está na versão mais recente", "ok")
    return True


# ── Links ─────────────────────────────────────────────────────────────────────
YT_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
TRACKING_PARAMS = {"si", "feature", "pp"}


def is_youtube(url):
    host = (urlsplit(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in YT_HOSTS)


def clean_url(url):
    """Remove rastreamento (si, feature, pp). Se há vídeo e list=, mantém só o vídeo.
    Retorna (url, aviso_ou_None)."""
    if not is_youtube(url):
        return url, None
    parts = urlsplit(url)
    q = parse_qsl(parts.query, keep_blank_values=True)
    keys = {k for k, _ in q}
    host = (parts.hostname or "").lower()
    has_video = ("v" in keys or "/shorts/" in parts.path
                 or (host.endswith("youtu.be") and parts.path.strip("/") != ""))
    warn = None
    drop = set(TRACKING_PARAMS)
    if "list" in keys and has_video:
        drop |= {"list", "index", "start_radio"}
        warn = "Link com playlist (list=) e vídeo: baixando só o vídeo."
    q = [(k, v) for k, v in q if k not in drop]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment)), warn


# ── Formato / erros ───────────────────────────────────────────────────────────
def build_format(quality):
    """-f priorizando H.264 + AAC (evita recodificação). None para só áudio."""
    if quality == Q_AUDIO:
        return None
    if quality == Q_MAX:
        return "bv*+ba/b"   # sem restrição de codec; ffprobe converte depois se preciso
    m = re.match(r"(\d+)p", quality)
    h = f"[height<={m.group(1)}]" if m else ""
    return (f"bv*[vcodec^=avc1]{h}+ba[acodec^=mp4a]"
            f"/b[vcodec^=avc1]{h}"
            f"/bv*{h}+ba"
            f"/b{h}")


COOKIE_ERROR_PATTERNS = [
    r"could not copy \w+ cookie database",
    r"failed to decrypt",
    r"app[- ]bound",
    r"unable to (read|decrypt|extract).{0,40}cookie",
    r"could not (find|read).{0,40}cookie",
]


def is_cookie_error(text):
    t = text.lower()
    return any(re.search(p, t) for p in COOKIE_ERROR_PATTERNS)


def is_retryable(text):
    t = text.lower()
    return "http error 403" in t or "sign in to confirm" in t


def translate_error(lines, rc):
    err = next((l for l in reversed(lines) if l.startswith("ERROR:")), None)
    if not err:
        return f"Falha (código {rc})"
    low = err.lower()
    if "sign in to confirm" in low and "not a bot" in low:
        return "YouTube bloqueou temporariamente: aguarde alguns minutos ou use cookies"
    if "sign in to confirm your age" in low:
        return "Vídeo com restrição de idade: escolha um navegador em Cookies"
    if "private video" in low:
        return "Vídeo privado"
    if "video unavailable" in low or "video is unavailable" in low or "video is not available" in low:
        return "Vídeo indisponível ou removido"
    if "http error 403" in low:
        return "YouTube recusou o download. Atualize o app e tente mais tarde"
    return err


def probe_codecs(ffprobe, path):
    r = run_quiet([ffprobe, "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                   "-of", "json", path], timeout=60)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or "ffprobe falhou")
    v = a = None
    for s in json.loads(r.stdout or "{}").get("streams", []):
        if s.get("codec_type") == "video" and v is None:
            v = s.get("codec_name")
        elif s.get("codec_type") == "audio" and a is None:
            a = s.get("codec_name")
    return v, a


# ── Download engine (sem Tk, testável) ────────────────────────────────────────
class Downloader:
    def __init__(self, ytdlp, deno, folder, quality, browser, log,
                 is_stopped=lambda: False, set_proc=lambda p: None):
        self.ytdlp, self.deno, self.folder = ytdlp, deno, folder
        self.quality, self.browser = quality, browser   # browser: None ou "firefox"/"chrome"/…
        self.log, self.is_stopped, self.set_proc = log, is_stopped, set_proc
        self.force_fail = set()   # índices de tentativa a simular com 403 (testes)

    def build_args(self, url, extra, use_cookies, no_continue):
        out = os.path.join(os.path.abspath(self.folder), "%(uploader)s - %(title).60s.%(ext)s")
        args = [self.ytdlp, "--no-playlist", "--no-quiet", "--newline", "-o", out,
                "--merge-output-format", "mp4",
                "--print", "after_move:SVDFILE:%(filepath)s"]
        if self.deno:
            args += ["--js-runtimes", f"deno:{self.deno}"]
        if IS_WIN:
            args += ["--windows-filenames", "--trim-filenames", "150"]
        if no_continue:
            args.append("--no-continue")
        args += extra
        if use_cookies and self.browser:
            args += ["--cookies-from-browser", self.browser]
        fmt = build_format(self.quality)
        if fmt is None:
            args += ["-x", "--audio-format", "mp3"]
        else:
            args += ["-f", fmt]
        args.append(url)
        return args

    def _run(self, args):
        """Roda yt-dlp; retorna (rc, linhas, destinos, arquivo_final)."""
        lines, dests, final = [], [], None
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace", bufsize=1,
                                env=_env(), **_proc_kwargs())
        self.set_proc(proc)
        for raw in proc.stdout:
            line = raw.strip()
            if not line:
                continue
            lines.append(line)
            if line.startswith("SVDFILE:"):
                final = line[len("SVDFILE:"):]
                continue
            m = re.match(r"\[download\] Destination: (.+)$", line)
            if m:
                dests.append(m.group(1))
            if "[download]" in line and "% of" in line and "100%" not in line:
                continue   # progresso intermediário: não inunda o log
            if any(t in line for t in ("[download]", "[Merger]", "[ffmpeg]", "[ExtractAudio]")):
                self.log(line)
        proc.wait()
        return proc.returncode, lines, dests, final

    def _cleanup(self, dests):
        """Apaga .part/.ytdl dos arquivos deste vídeo antes de nova tentativa."""
        for d in dests:
            victims = [d + ".part", d + ".ytdl"] + glob.glob(glob.escape(d) + ".part-*")
            for p in victims:
                try:
                    os.remove(p)
                except OSError:
                    pass

    def download(self, url):
        url, warn = clean_url(url)
        if warn:
            self.log(warn, "warn")
        yt = is_youtube(url)
        if yt:
            attempts = [(a, False) for a in YT_RETRY_ARGS]
            if self.browser:
                attempts.append(([], True))
            if not self.deno:
                self.log("Sem deno, alguns vídeos do YouTube podem falhar", "warn")
        else:
            attempts = [([], bool(self.browser))]

        i = 0
        all_dests = []
        report = ([], 1)
        while i < len(attempts):
            extra, use_cookies = attempts[i]
            if i in self.force_fail:
                rc, lines, dests, final = 1, ["ERROR: unable to download video data: HTTP Error 403: Forbidden"], [], None
            else:
                rc, lines, dests, final = self._run(self.build_args(url, extra, use_cookies, no_continue=i > 0))
            all_dests += dests
            if rc == 0:
                self._finish(final)
                return True
            if self.is_stopped():
                return False
            text = "\n".join(lines)
            if use_cookies and is_cookie_error(text):
                self.log(f"Não foi possível ler os cookies do {self.browser}. Feche o navegador ou use o Firefox.", "warn")
                if not yt:
                    attempts.append(([], False))   # segue sem cookies
                self._cleanup(all_dests)
                i += 1
                continue
            report = (lines, rc)
            if yt and is_retryable(text) and i + 1 < len(attempts):
                self.log(f"403 do YouTube, tentando outro método ({i + 2}/{len(attempts)})…", "warn")
                self._cleanup(all_dests)
                i += 1
                continue
            break
        self.log(f"✗ {translate_error(*report)}", "err")
        return False

    def _finish(self, path):
        """Verifica o arquivo final e só recodifica o necessário."""
        if self.quality == Q_AUDIO or not path or not os.path.isfile(path):
            self.log("✓ Concluído", "ok")
            return
        ffprobe, ffmpeg = find_media_tool("ffprobe"), find_media_tool("ffmpeg")
        if not ffprobe or not ffmpeg:
            self.log("ffmpeg/ffprobe não encontrados — não foi possível verificar a compatibilidade.", "warn")
        else:
            try:
                self.ensure_compatible(path, ffprobe, ffmpeg)
            except Exception as e:
                self.log(f"Não foi possível verificar/converter o arquivo: {e}", "warn")
        self.log("✓ Concluído", "ok")

    def ensure_compatible(self, path, ffprobe, ffmpeg):
        v, a = probe_codecs(ffprobe, path)
        if v == "h264" and (a == "aac" or a is None):
            self.log("Já compatível, sem conversão", "ok")
            return
        tmp = os.path.splitext(path)[0] + ".conv.mp4"
        if v == "h264":
            self.log("Convertendo áudio para AAC", "info")
            opts = ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
        else:
            self.log("Convertendo 4K para H.264, isso pode levar alguns minutos" if self.quality == Q_MAX
                     else "Convertendo vídeo para H.264", "info")
            opts = ["-c:v", "libx264", "-preset", "fast", "-crf", "20", "-c:a", "aac",
                    "-movflags", "+faststart"]
        cmd = [ffmpeg, "-y", "-v", "error", "-i", path] + opts + [tmp]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=_env(), **_proc_kwargs())
        self.set_proc(proc)
        out = proc.communicate()[0]
        if proc.returncode != 0 or not os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise RuntimeError((out or "ffmpeg falhou").strip().splitlines()[-1])
        os.replace(tmp, path)


# ── App ───────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        setup_environment()
        self.title("Social Video Downloader")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(640, 640)

        self.download_folder = os.path.join(os.path.expanduser("~"), "Downloads", "SocialVideos")
        self.is_downloading = False
        self._process = None
        self._ytdlp_bin = None
        self._deno_bin = None
        self._tool_lock = threading.Lock()   # mantido durante instalação/atualização do yt-dlp

        self._build()
        self._center()
        threading.Thread(target=self._bootstrap, daemon=True).start()

    def _center(self):
        self.update_idletasks()
        w, h = 700, 780
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── Layout ────────────────────────────────────────────────────────────────
    def _build(self):
        # ── Footer (versão do yt-dlp), empacotado primeiro para ficar na base ──
        footer = tk.Frame(self, bg=BG)
        footer.pack(side="bottom", fill="x")
        self.version_lbl = tk.Label(footer, text="yt-dlp …", font=("Menlo", 9), bg=BG, fg=TEXT_DIM)
        self.version_lbl.pack(side="right", padx=12, pady=(2, 4))

        # ── Bottom bar ──
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
            command=self._start, state="disabled"   # liberado quando as ferramentas estiverem prontas
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
        self._hdr = hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill="x", pady=(0, 16))
        tk.Label(hdr, text="⬇", font=("Helvetica Neue", 26), bg=BG, fg=ACCENT).pack(side="left", padx=(0, 10))
        blk = tk.Frame(hdr, bg=BG)
        blk.pack(side="left")
        tk.Label(blk, text="Social Video Downloader", font=TITLE, bg=BG, fg=TEXT).pack(anchor="w")
        tk.Label(blk, text="YouTube  ·  e outras plataformas", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")

        # Aviso de ferramenta (oculto até ocorrer um problema)
        self.banner = tk.Frame(main, bg="#2a1a00", pady=6)
        self.banner_lbl = tk.Label(self.banner, text="", font=SMALL, bg="#2a1a00", fg=WARNING,
                                   padx=12, justify="left", anchor="w", wraplength=520)
        self.banner_lbl.pack(side="left", fill="x", expand=True)
        self.banner_btn = tk.Button(self.banner, text="Abrir pasta", font=SMALL, bg=SURFACE2, fg=TEXT,
                                    relief="flat", padx=10, pady=4, cursor="hand2",
                                    activebackground=BORDER)
        self.banner_btn.pack(side="right", padx=8)

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
        tk.Label(main, text="Um link por linha  ·  otimizado para YouTube",
                 font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w", pady=(4, 12))

        # Options
        self._sep(main, "OPÇÕES")
        opts = tk.Frame(main, bg=BG)
        opts.pack(fill="x", pady=(4, 12))

        qf = tk.Frame(opts, bg=BG)
        qf.pack(side="left", fill="x", expand=True, padx=(0, 12))
        tk.Label(qf, text="Qualidade", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")
        self.quality = tk.StringVar(value=Q_BEST)
        ttk.Combobox(qf, textvariable=self.quality, state="readonly", font=UI, width=24,
                     values=[Q_BEST, Q_MAX, "720p", "480p", Q_AUDIO]).pack(fill="x", pady=(4, 0))

        cf = tk.Frame(opts, bg=BG)
        cf.pack(side="left")
        tk.Label(cf, text="Cookies do navegador", font=SMALL, bg=BG, fg=TEXT_DIM).pack(anchor="w")
        self.cookies = tk.StringVar(value="nenhum")
        browsers = (["nenhum", "firefox", "chrome", "edge", "brave"] if IS_WIN
                    else ["chrome", "safari", "firefox", "edge", "brave", "nenhum"])
        ttk.Combobox(cf, textvariable=self.cookies, state="readonly", font=UI, width=10,
                     values=browsers).pack(fill="x", pady=(4, 0))
        if IS_WIN:
            tk.Label(main, text="No Windows, use Firefox. Chrome e Edge precisam estar fechados e podem não funcionar.",
                     font=SMALL, bg=BG, fg=TEXT_DIM, wraplength=620, justify="left").pack(anchor="w", pady=(0, 8))

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
                  activebackground=BORDER, command=self._pick_folder).pack(side="left", padx=(8, 0))

        # Log (com botão Copiar log)
        row = tk.Frame(main, bg=BG)
        row.pack(fill="x", pady=(2, 0))
        tk.Label(row, text="LOG", font=("Menlo", 9, "bold"), bg=BG, fg=TEXT_DIM).pack(side="left")
        self.copy_btn = tk.Button(row, text="Copiar log", font=("Helvetica Neue", 9), bg=SURFACE2, fg=TEXT_DIM,
                                  relief="flat", padx=8, pady=0, cursor="hand2",
                                  activebackground=BORDER, activeforeground=TEXT, command=self._copy_log)
        self.copy_btn.pack(side="left", padx=(8, 0))
        tk.Frame(row, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)
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
        tk.Frame(row, bg=BORDER, height=1).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)

    # ── Ferramentas (yt-dlp, deno, atualização) ───────────────────────────────
    def _tlog(self, msg, tag=""):
        """Log thread-safe."""
        self.after(0, lambda: self._write_log(msg, tag))

    def _show_tool_problem(self, err):
        folder = err.folder or tools_dir()

        def show():
            self.banner_lbl.configure(text=str(err))
            self.banner_btn.configure(command=lambda: open_folder(folder))
            self.banner.pack(fill="x", pady=(0, 10), after=self._hdr)
        self.after(0, show)
        self._tlog(f"⚠ {err}", "err")

    def _bootstrap(self):
        with self._tool_lock:
            try:
                self._ytdlp_bin = ensure_ytdlp(self._tlog)
            except ToolError as e:
                self._show_tool_problem(e)
                self._refresh_version()
                return
            except Exception as e:
                self._tlog(f"Falha ao preparar o yt-dlp: {e}", "err")
                self._refresh_version()
                return
            try:
                self._deno_bin = ensure_deno(self._tlog)
            except ToolError as e:
                self._show_tool_problem(e)
                self._tlog("Sem deno, alguns vídeos do YouTube podem falhar", "warn")
            except Exception as e:
                self._tlog(f"Falha ao preparar o deno: {e}", "err")
                self._tlog("Sem deno, alguns vídeos do YouTube podem falhar", "warn")
            self.after(0, lambda: self.dl_btn.configure(state="normal"))
            self._refresh_version()

            cfg = load_config()
            if update_due(cfg):
                if update_ytdlp(self._ytdlp_bin, self._tlog):
                    cfg["last_ytdlp_update"] = date.today().isoformat()
                    save_config(cfg)
                self._refresh_version()

    def _refresh_version(self):
        v = ytdlp_version(self._ytdlp_bin) if self._ytdlp_bin else None
        self.after(0, lambda: self.version_lbl.configure(text=f"yt-dlp {v}" if v else "yt-dlp não encontrado"))

    # ── Actions ───────────────────────────────────────────────────────────────
    def _clear_hint(self, _=None):
        if self.links_box.get("1.0", "end-1c").strip().startswith("# Cole os links"):
            self.links_box.delete("1.0", "end")

    def _pick_folder(self):
        f = filedialog.askdirectory(title="Pasta de destino")
        if f:
            self.download_folder = os.path.normpath(f)
            self.folder_lbl.configure(text=self.download_folder)

    def _clear(self):
        self.links_box.delete("1.0", "end")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self.log.get("1.0", "end-1c"))
        self.update()
        self.copy_btn.configure(text="Copiado ✓")
        self.after(1500, lambda: self.copy_btn.configure(text="Copiar log"))

    def _write_log(self, msg, tag=""):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{ts}] {msg}\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _get_links(self):
        return [l.strip() for l in self.links_box.get("1.0", "end-1c").splitlines()
                if l.strip() and not l.strip().startswith("#")]

    def _set_ui(self, downloading):
        self.dl_btn.configure(state="disabled" if downloading else "normal")
        self.stop_btn.configure(state="normal" if downloading else "disabled")
        self.clear_btn.configure(state="disabled" if downloading else "normal")

    def _set_proc(self, p):
        self._process = p

    def _start(self):
        links = self._get_links()
        if not links:
            messagebox.showwarning("Sem links", "Cole pelo menos um link antes de baixar.")
            return
        if not self._ytdlp_bin:
            messagebox.showerror("yt-dlp não encontrado", "O yt-dlp ainda está sendo preparado. Aguarde alguns instantes.")
            return
        os.makedirs(self.download_folder, exist_ok=True)
        self.is_downloading = True
        self._set_ui(True)
        self.prog.start(12)
        self.log.configure(state="normal"); self.log.delete("1.0", "end"); self.log.configure(state="disabled")
        self._write_log(f"Iniciando {len(links)} download(s)...", "info")
        browser = self.cookies.get()
        engine = Downloader(
            self._ytdlp_bin, self._deno_bin, self.download_folder, self.quality.get(),
            None if browser == "nenhum" else browser, self._tlog,
            is_stopped=lambda: not self.is_downloading, set_proc=self._set_proc)
        threading.Thread(target=self._worker, args=(links, engine), daemon=True).start()

    def _stop(self):
        self.is_downloading = False
        if self._process:
            try:
                self._process.terminate()
            except Exception:
                pass
        self._write_log("Interrompido pelo usuário.", "warn")

    def _worker(self, links, engine):
        if self._tool_lock.locked():
            self._tlog("Aguardando o yt-dlp terminar de atualizar…", "info")
        with self._tool_lock:
            pass
        ok = fail = 0
        for i, url in enumerate(links, 1):
            if not self.is_downloading:
                break
            self._tlog(f"({i}/{len(links)}) {url}", "info")
            try:
                if engine.download(url):
                    ok += 1
                else:
                    fail += 1
            except Exception as e:
                self._tlog(f"✗ Erro: {e}", "err")
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
