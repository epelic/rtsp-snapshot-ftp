from __future__ import annotations

import json
import os
import queue
import socket
import sys
import threading
import time
import winreg
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from ftplib import FTP
from io import BytesIO
from pathlib import Path
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import cv2
from PIL import Image, ImageDraw, ImageFont, ImageTk
import pystray


APP_NAME = "RTSP Snapshot FTP"
APP_VERSION = "1.1.3"
STARTUP_REG_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
STARTUP_REG_NAME = "RTSP Snapshot FTP"


def bundled_path(relative: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / relative


def app_data_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    path = Path(base) / "RTSPSnapshotFTP"
    path.mkdir(parents=True, exist_ok=True)
    return path


SETTINGS_FILE = app_data_dir() / "settings.json"


@dataclass
class Settings:
    rtsp_url: str = "rtsp://192.168.0.110/11"
    preview_fps: float = 2.0
    interval_seconds: int = 60
    jpeg_quality: int = 90
    png_path: str = ""
    png_scale: int = 30
    png_x: float = 0.03
    png_y: float = 0.03
    datetime_enabled: bool = True
    datetime_format: str = "%d/%m/%Y %H:%M:%S"
    datetime_font: str = "C:/Windows/Fonts/arial.ttf"
    datetime_size: int = 34
    datetime_color: str = "#FFFFFF"
    datetime_outline_color: str = "#000000"
    datetime_outline: int = 2
    datetime_shadow: bool = True
    datetime_x: float = 0.97
    datetime_y: float = 0.03
    datetime_anchor: str = "ra"
    ftp_host: str = ""
    ftp_port: int = 21
    ftp_username: str = ""
    ftp_password: str = ""
    ftp_folder: str = ""
    ftp_filename: str = "webcam.jpg"
    ftp_passive: bool = True

    @classmethod
    def load(cls) -> "Settings":
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            allowed = cls.__dataclass_fields__.keys()
            return cls(**{k: v for k, v in data.items() if k in allowed})
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self) -> None:
        temp = SETTINGS_FILE.with_suffix(".tmp")
        temp.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        temp.replace(SETTINGS_FILE)


class VideoWorker:
    def __init__(self, frame_queue: queue.Queue, log):
        self.frame_queue = frame_queue
        self.log = log
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self, url: str, fps: float) -> None:
        self.stop()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(url, fps), daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
        self.thread = None

    def _run(self, url: str, fps: float) -> None:
        # TCP è generalmente più affidabile per IP camera e reti Wi-Fi. I timeout
        # evitano che FFmpeg blocchi per sempre la chiusura o la riconnessione.
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|stimeout;10000000|rw_timeout;10000000")
        preview_delay = 1.0 / max(0.2, fps)
        reconnect_attempt = 0
        while not self.stop_event.is_set():
            reconnect_attempt += 1
            suffix = "" if reconnect_attempt == 1 else f" (tentativo {reconnect_attempt})"
            self.log(f"Connessione al flusso RTSP via TCP{suffix}...")
            try:
                capture = cv2.VideoCapture(
                    url,
                    cv2.CAP_FFMPEG,
                    [cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 10000,
                     cv2.CAP_PROP_READ_TIMEOUT_MSEC, 10000])
            except Exception:
                capture = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
            capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if not capture.isOpened():
                capture.release()
                self.log("RTSP non disponibile; nuovo tentativo tra 3 secondi")
                self.stop_event.wait(3)
                continue

            self.log("Flusso RTSP connesso; attesa fotogrammi...")
            failures = 0
            next_preview = 0.0
            received_any = False
            try:
                while not self.stop_event.is_set():
                    # Legge continuamente per non lasciare accumulare il buffer RTSP.
                    if not capture.grab():
                        failures += 1
                        if failures >= 20:
                            self.log("RTSP interrotto; avvio riconnessione automatica")
                            break
                        self.stop_event.wait(0.05)
                        continue
                    failures = 0
                    now = time.monotonic()
                    if now < next_preview:
                        continue
                    ok, bgr = capture.retrieve()
                    if not ok:
                        continue
                    if not received_any:
                        self.log("Primo fotogramma RTSP ricevuto correttamente")
                        received_any = True
                        reconnect_attempt = 0
                    next_preview = now + preview_delay
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    image = Image.fromarray(rgb)
                    while True:
                        try:
                            self.frame_queue.get_nowait()
                        except queue.Empty:
                            break
                    self.frame_queue.put(image)
            finally:
                capture.release()
            if not self.stop_event.is_set():
                self.stop_event.wait(2)


class App(tk.Tk):
    PREVIEW_W, PREVIEW_H = 800, 450

    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        try:
            self.iconbitmap(str(bundled_path("assets/camera-icon.ico")))
        except tk.TclError:
            pass
        self.geometry("1280x790")
        self.minsize(1100, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.settings = Settings.load()
        self.frame_queue: queue.Queue = queue.Queue(maxsize=1)
        self.worker = VideoWorker(self.frame_queue, self.log_async)
        self.current_frame: Image.Image | None = None
        self.composited_frame: Image.Image | None = None
        self.preview_photo = None
        self.overlay_cache: tuple[str, float, Image.Image] | None = None
        self.running = False
        self.uploading = False
        self.waiting_for_first_frame = False
        self.next_upload = 0.0
        self.drag_target: str | None = None
        self.preview_fullscreen = False
        self.log_queue: queue.Queue[str] = queue.Queue()
        self._build_ui()
        self._load_vars()
        self._create_tray_icon()
        self.after(80, self._tick)
        self.after(1000, self._auto_start)
        self.log(f"Impostazioni: {SETTINGS_FILE}")

    def _build_ui(self):
        menu_bar = tk.Menu(self)
        file_menu = tk.Menu(menu_bar, tearoff=False)
        file_menu.add_command(label="Salva settings", command=self.save_settings)
        file_menu.add_command(label="Avvia con Windows", command=self.toggle_startup)
        file_menu.add_separator()
        file_menu.add_command(label="Esporta settings...", command=self.export_config)
        file_menu.add_command(label="Carica settings...", command=self.import_config)
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self.exit_app)
        menu_bar.add_cascade(label="File", menu=file_menu)
        menu_bar.add_command(label="Info", command=self.show_about)
        self.app_menu = menu_bar
        self.configure(menu=self.app_menu)
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        self.main_pane = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        left = ttk.Frame(self.main_pane)
        self.right_panel = ttk.Frame(self.main_pane, width=410)
        self.main_pane.add(left, weight=3)
        self.main_pane.add(self.right_panel, weight=2)

        self.canvas = tk.Canvas(left, width=self.PREVIEW_W, height=self.PREVIEW_H,
                                bg="#15181c", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.create_text(self.PREVIEW_W / 2, self.PREVIEW_H / 2,
                                text="Premi Test RTSP per avviare l'anteprima",
                                fill="#aab2bd", font=("Segoe UI", 14), tags="placeholder")
        self.canvas.bind("<Button-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_move)
        self.canvas.bind("<Double-Button-1>", self.toggle_preview_fullscreen)
        self.canvas.bind("<Configure>", lambda _e: self._render_preview())
        self.bind("<Escape>", self.exit_preview_fullscreen)

        self.preview_controls = ttk.Frame(left)
        self.preview_controls.pack(fill=tk.X, pady=(8, 0))
        for text, cmd in (("Test RTSP", self.test_rtsp), ("Start", self.start_service),
                          ("Stop", self.stop_service), ("Upload adesso", self.manual_upload)):
            ttk.Button(self.preview_controls, text=text, command=cmd).pack(side=tk.LEFT, padx=(0, 8))
        self.status_var = tk.StringVar(value="Fermo")
        ttk.Label(self.preview_controls, textvariable=self.status_var).pack(side=tk.RIGHT)

        notebook = ttk.Notebook(self.right_panel)
        notebook.pack(fill=tk.BOTH, expand=True)
        self.general_tab = ttk.Frame(notebook, padding=12)
        self.overlay_tab = ttk.Frame(notebook, padding=12)
        self.ftp_tab = ttk.Frame(notebook, padding=12)
        self.log_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self.general_tab, text="Generale")
        notebook.add(self.overlay_tab, text="Overlay")
        notebook.add(self.ftp_tab, text="FTP")
        notebook.add(self.log_tab, text="Log")
        self._build_general()
        self._build_overlay()
        self._build_ftp()
        self.log_text = tk.Text(self.log_tab, state=tk.DISABLED, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def show_about(self):
        about = tk.Toplevel(self)
        about.title(f"Info su {APP_NAME}")
        about.resizable(False, False)
        about.transient(self)
        about.grab_set()
        try:
            about.iconbitmap(str(bundled_path("assets/camera-icon.ico")))
        except tk.TclError:
            pass
        body = ttk.Frame(about, padding=24)
        body.pack(fill=tk.BOTH, expand=True)
        try:
            icon = Image.open(bundled_path("assets/camera-icon.png")).convert("RGBA")
            icon.thumbnail((112, 112), Image.Resampling.LANCZOS)
            about.icon_photo = ImageTk.PhotoImage(icon)
            ttk.Label(body, image=about.icon_photo).pack(pady=(0, 10))
        except Exception:
            pass
        ttk.Label(body, text=APP_NAME, font=("Segoe UI", 16, "bold")).pack()
        ttk.Label(body, text=f"Versione {APP_VERSION}").pack(pady=(3, 12))
        ttk.Label(
            body,
            text="Acquisizione RTSP, overlay grafici e upload FTP automatico.",
            wraplength=390,
            justify=tk.CENTER).pack(pady=(0, 12))
        ttk.Label(body, text="Copyright © 2026 Freewaves").pack()
        ttk.Label(body, text="Software distribuito gratuitamente.").pack(pady=(2, 14))
        link = ttk.Label(
            body,
            text="github.com/epelic/rtsp-snapshot-ftp",
            foreground="#0066cc",
            cursor="hand2")
        link.pack()
        link.bind(
            "<Button-1>",
            lambda _event: webbrowser.open("https://github.com/epelic/rtsp-snapshot-ftp"))
        ttk.Button(body, text="Chiudi", command=about.destroy).pack(fill=tk.X, pady=(18, 0))
        about.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - about.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - about.winfo_height()) // 2
        about.geometry(f"+{max(0, x)}+{max(0, y)}")

    def toggle_preview_fullscreen(self, _event=None):
        self.preview_fullscreen = not self.preview_fullscreen
        if self.preview_fullscreen:
            self.preview_controls.pack_forget()
            self.main_pane.forget(self.right_panel)
            self.configure(menu="")
            self.main_pane.pack_configure(padx=0, pady=0)
            self.attributes("-fullscreen", True)
        else:
            self.attributes("-fullscreen", False)
            self.main_pane.pack_configure(padx=10, pady=10)
            self.main_pane.add(self.right_panel, weight=2)
            self.preview_controls.pack(fill=tk.X, pady=(8, 0))
            self.configure(menu=self.app_menu)
        self.after(50, self._render_preview)

    def exit_preview_fullscreen(self, _event=None):
        if self.preview_fullscreen:
            self.toggle_preview_fullscreen()

    def _row(self, parent, row, label, variable, width=24, **opts):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=5)
        entry = ttk.Entry(parent, textvariable=variable, width=width, **opts)
        entry.grid(row=row, column=1, sticky="ew", pady=5)
        parent.columnconfigure(1, weight=1)
        return entry

    def _build_general(self):
        self.rtsp_var = tk.StringVar()
        self.fps_var = tk.DoubleVar()
        self.interval_var = tk.IntVar()
        self.quality_var = tk.IntVar()
        self._row(self.general_tab, 0, "URL RTSP", self.rtsp_var)
        self._row(self.general_tab, 1, "Anteprima FPS", self.fps_var)
        self._row(self.general_tab, 2, "Intervallo upload (s)", self.interval_var)
        self._row(self.general_tab, 3, "Qualità JPEG (1-100)", self.quality_var)
        ttk.Button(self.general_tab, text="Salva impostazioni", command=self.save_settings).grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(18, 5))
        self.startup_button = ttk.Button(self.general_tab, command=self.toggle_startup)
        self.startup_button.grid(row=5, column=0, columnspan=2, sticky="ew", pady=5)
        ttk.Button(self.general_tab, text="Esporta config...", command=self.export_config).grid(
            row=6, column=0, columnspan=2, sticky="ew", pady=5)
        self._refresh_startup_button()

    def _build_overlay(self):
        self.png_var = tk.StringVar()
        self.png_scale_var = tk.IntVar()
        self.dt_enabled_var = tk.BooleanVar()
        self.dt_format_var = tk.StringVar()
        self.font_var = tk.StringVar()
        self.font_size_var = tk.IntVar()
        self.color_var = tk.StringVar()
        self.outline_color_var = tk.StringVar()
        self.outline_var = tk.IntVar()
        self.shadow_var = tk.BooleanVar()
        self._row(self.overlay_tab, 0, "Immagine PNG", self.png_var)
        ttk.Button(self.overlay_tab, text="Sfoglia...", command=self.choose_png).grid(row=1, column=0, columnspan=2, sticky="ew")
        self._row(self.overlay_tab, 2, "Dimensione PNG (%)", self.png_scale_var)
        ttk.Separator(self.overlay_tab).grid(row=3, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Checkbutton(self.overlay_tab, text="Mostra data e ora", variable=self.dt_enabled_var,
                        command=self._render_preview).grid(row=4, column=0, columnspan=2, sticky="w")
        self._row(self.overlay_tab, 5, "Formato", self.dt_format_var)
        self._row(self.overlay_tab, 6, "Font", self.font_var)
        ttk.Button(self.overlay_tab, text="Scegli font...", command=self.choose_font).grid(row=7, column=0, columnspan=2, sticky="ew")
        self._row(self.overlay_tab, 8, "Dimensione testo", self.font_size_var)
        self._row(self.overlay_tab, 9, "Colore testo", self.color_var)
        ttk.Button(self.overlay_tab, text="Scegli colore testo", command=lambda: self.choose_color(self.color_var)).grid(row=10, column=0, columnspan=2, sticky="ew")
        self._row(self.overlay_tab, 11, "Colore contorno", self.outline_color_var)
        ttk.Button(self.overlay_tab, text="Scegli colore contorno", command=lambda: self.choose_color(self.outline_color_var)).grid(row=12, column=0, columnspan=2, sticky="ew")
        self._row(self.overlay_tab, 13, "Spessore contorno", self.outline_var)
        ttk.Checkbutton(self.overlay_tab, text="Ombra", variable=self.shadow_var, command=self._render_preview).grid(row=14, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Label(self.overlay_tab, text="Trascina logo o data/ora direttamente nell'anteprima.", wraplength=350).grid(row=15, column=0, columnspan=2, sticky="w", pady=(10, 0))
        for var in (self.png_scale_var, self.dt_format_var, self.font_size_var, self.color_var,
                    self.outline_color_var, self.outline_var):
            var.trace_add("write", lambda *_: self._render_preview())

    def _build_ftp(self):
        self.ftp_host_var = tk.StringVar()
        self.ftp_port_var = tk.IntVar()
        self.ftp_user_var = tk.StringVar()
        self.ftp_pass_var = tk.StringVar()
        self.ftp_folder_var = tk.StringVar()
        self.ftp_file_var = tk.StringVar()
        self.passive_var = tk.BooleanVar()
        self._row(self.ftp_tab, 0, "Host", self.ftp_host_var)
        self._row(self.ftp_tab, 1, "Porta", self.ftp_port_var)
        self._row(self.ftp_tab, 2, "Username", self.ftp_user_var)
        self._row(self.ftp_tab, 3, "Password", self.ftp_pass_var, show="•")
        self._row(self.ftp_tab, 4, "Cartella remota", self.ftp_folder_var)
        self._row(self.ftp_tab, 5, "Nome file", self.ftp_file_var)
        ttk.Checkbutton(self.ftp_tab, text="Modalità passiva", variable=self.passive_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Button(self.ftp_tab, text="Test FTP", command=self.test_ftp).grid(row=7, column=0, columnspan=2, sticky="ew", pady=8)

    def _load_vars(self):
        s = self.settings
        mapping = (
            (self.rtsp_var, s.rtsp_url), (self.fps_var, s.preview_fps),
            (self.interval_var, s.interval_seconds), (self.quality_var, s.jpeg_quality),
            (self.png_var, s.png_path), (self.png_scale_var, s.png_scale),
            (self.dt_enabled_var, s.datetime_enabled), (self.dt_format_var, s.datetime_format),
            (self.font_var, s.datetime_font), (self.font_size_var, s.datetime_size),
            (self.color_var, s.datetime_color), (self.outline_color_var, s.datetime_outline_color),
            (self.outline_var, s.datetime_outline), (self.shadow_var, s.datetime_shadow),
            (self.ftp_host_var, s.ftp_host), (self.ftp_port_var, s.ftp_port),
            (self.ftp_user_var, s.ftp_username), (self.ftp_pass_var, s.ftp_password),
            (self.ftp_folder_var, s.ftp_folder), (self.ftp_file_var, s.ftp_filename),
            (self.passive_var, s.ftp_passive),
        )
        for var, value in mapping:
            var.set(value)

    def _update_settings(self):
        s = self.settings
        s.rtsp_url = self.rtsp_var.get().strip()
        s.preview_fps = max(0.2, float(self.fps_var.get()))
        s.interval_seconds = max(1, int(self.interval_var.get()))
        s.jpeg_quality = min(100, max(1, int(self.quality_var.get())))
        s.png_path = self.png_var.get().strip()
        s.png_scale = min(100, max(1, int(self.png_scale_var.get())))
        s.datetime_enabled = self.dt_enabled_var.get()
        s.datetime_format = self.dt_format_var.get()
        s.datetime_font = self.font_var.get().strip()
        s.datetime_size = max(6, int(self.font_size_var.get()))
        s.datetime_color = self.color_var.get()
        s.datetime_outline_color = self.outline_color_var.get()
        s.datetime_outline = max(0, int(self.outline_var.get()))
        s.datetime_shadow = self.shadow_var.get()
        s.ftp_host = self.ftp_host_var.get().strip()
        s.ftp_port = int(self.ftp_port_var.get())
        s.ftp_username = self.ftp_user_var.get()
        s.ftp_password = self.ftp_pass_var.get()
        s.ftp_folder = self.ftp_folder_var.get().strip()
        s.ftp_filename = self.ftp_file_var.get().strip()
        s.ftp_passive = self.passive_var.get()

    def save_settings(self):
        try:
            self._update_settings()
            self.settings.save()
            self.log("Impostazioni salvate")
        except (ValueError, OSError) as exc:
            messagebox.showerror(APP_NAME, f"Impostazioni non valide:\n{exc}")

    def _startup_enabled(self) -> bool:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH) as key:
                winreg.QueryValueEx(key, STARTUP_REG_NAME)
            return True
        except OSError:
            return False

    def _refresh_startup_button(self):
        enabled = self._startup_enabled()
        self.startup_button.configure(
            text=f"Avvia con Windows: {'ATTIVO' if enabled else 'DISATTIVO'}")

    def toggle_startup(self):
        try:
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, STARTUP_REG_PATH) as key:
                if self._startup_enabled():
                    winreg.DeleteValue(key, STARTUP_REG_NAME)
                    self.log("Avvio automatico con Windows disattivato")
                else:
                    executable = Path(sys.executable).resolve()
                    if not getattr(sys, "frozen", False):
                        messagebox.showwarning(
                            APP_NAME,
                            "L'avvio automatico può essere attivato dalla versione installata dell'app.")
                        return
                    winreg.SetValueEx(
                        key, STARTUP_REG_NAME, 0, winreg.REG_SZ, f'"{executable}"')
                    self.log("Avvio automatico con Windows attivato")
            self._refresh_startup_button()
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Impossibile modificare l'avvio automatico:\n{exc}")

    def export_config(self):
        try:
            self._update_settings()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        password_choice = messagebox.askyesnocancel(
            APP_NAME,
            "Includere la password FTP nell'esportazione?\n\n"
            "Sì: configurazione completa, ma la password sarà leggibile nel file.\n"
            "No: la password verrà esclusa.")
        if password_choice is None:
            return
        path = filedialog.asksaveasfilename(
            title="Esporta configurazione",
            defaultextension=".json",
            initialfile="rtsp-ftp-config.json",
            filetypes=[("Configurazione JSON", "*.json")])
        if not path:
            return
        data = asdict(self.settings)
        if not password_choice:
            data["ftp_password"] = ""
        try:
            Path(path).write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
            self.log(f"Configurazione esportata: {path}")
            messagebox.showinfo(APP_NAME, "Configurazione esportata correttamente.")
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"Impossibile esportare la configurazione:\n{exc}")

    def import_config(self):
        path = filedialog.askopenfilename(
            title="Carica configurazione",
            filetypes=[("Configurazione JSON", "*.json"), ("Tutti i file", "*.*")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Il file non contiene una configurazione valida")
            allowed = Settings.__dataclass_fields__.keys()
            merged = asdict(self.settings)
            merged.update({k: v for k, v in data.items() if k in allowed})
            self.settings = Settings(**merged)
            self._load_vars()
            self.overlay_cache = None
            self._render_preview()
            self.settings.save()
            self.log(f"Configurazione caricata: {path}")
            messagebox.showinfo(APP_NAME, "Configurazione caricata correttamente.")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            messagebox.showerror(APP_NAME, f"Impossibile caricare la configurazione:\n{exc}")

    def choose_png(self):
        path = filedialog.askopenfilename(filetypes=[("Immagini PNG", "*.png")])
        if path:
            self.png_var.set(path)
            self.overlay_cache = None
            self._render_preview()

    def choose_font(self):
        path = filedialog.askopenfilename(initialdir="C:/Windows/Fonts", filetypes=[("Font TrueType/OpenType", "*.ttf *.otf")])
        if path:
            self.font_var.set(path)
            self._render_preview()

    def choose_color(self, var):
        color = colorchooser.askcolor(var.get(), parent=self)[1]
        if color:
            var.set(color)

    def test_rtsp(self):
        try:
            self._update_settings()
            self.worker.start(self.settings.rtsp_url, self.settings.preview_fps)
            self.status_var.set("Anteprima attiva")
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def test_ftp(self):
        try:
            self._update_settings()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc)); return
        threading.Thread(target=self._test_ftp_thread, daemon=True).start()

    def _connect_ftp(self, settings: Settings | None = None) -> FTP:
        s = settings or self.settings
        if not s.ftp_host:
            raise ValueError("Inserire l'host FTP")
        ftp = FTP()
        self.log_async(f"FTP: connessione a {s.ftp_host}:{s.ftp_port}...")
        ftp.connect(s.ftp_host, s.ftp_port, timeout=15)
        self.log_async(f"FTP: server connesso ({ftp.getwelcome() or 'risposta ricevuta'})")
        self.log_async(f"FTP: autenticazione utente '{s.ftp_username}'...")
        ftp.login(s.ftp_username, s.ftp_password)
        self.log_async("FTP: autenticazione riuscita")
        ftp.set_pasv(s.ftp_passive)
        self.log_async(f"FTP: modalità {'passiva' if s.ftp_passive else 'attiva'}")
        if s.ftp_folder:
            self.log_async(f"FTP: apertura cartella remota '{s.ftp_folder}'...")
            ftp.cwd(s.ftp_folder.replace("\\", "/"))
            self.log_async(f"FTP: cartella corrente {ftp.pwd()}")
        return ftp

    def _test_ftp_thread(self):
        self.log_async("Test connessione FTP...")
        try:
            with self._connect_ftp() as ftp:
                ftp.pwd()
                self.log_async("FTP: chiusura connessione")
            self.log_async("Test FTP riuscito")
        except Exception as exc:
            self.log_async(f"ERRORE FTP: {exc}")

    def start_service(self):
        try:
            self._update_settings()
            if not self.settings.ftp_filename:
                raise ValueError("Inserire il nome file FTP")
            self.settings.save()
        except (ValueError, OSError) as exc:
            messagebox.showerror(APP_NAME, str(exc)); return
        self.running = True
        self.waiting_for_first_frame = self.current_frame is None
        self.next_upload = time.monotonic()
        self.worker.start(self.settings.rtsp_url, self.settings.preview_fps)
        self.status_var.set("Servizio attivo")
        self.log("Servizio avviato: upload automatico attivo")
        if self.waiting_for_first_frame:
            self.log("Upload automatico: attesa del primo fotogramma RTSP")

    def _auto_start(self):
        try:
            self._update_settings()
        except ValueError as exc:
            self.log(f"Avvio automatico non riuscito: {exc}")
            return
        if self.settings.ftp_host and self.settings.ftp_filename:
            self.log("Avvio automatico del servizio")
            self.start_service()
        else:
            self.log("FTP non ancora configurato: avvio automatico della sola anteprima")
            self.worker.start(self.settings.rtsp_url, self.settings.preview_fps)
            self.status_var.set("Anteprima attiva — configurare FTP")

    def stop_service(self):
        self.running = False
        self.waiting_for_first_frame = False
        self.worker.stop()
        self.status_var.set("Fermo")
        self.log("Servizio fermato")

    def manual_upload(self):
        if self.current_frame is None:
            messagebox.showwarning(APP_NAME, "Nessun fotogramma disponibile. Avvia prima l'anteprima.")
            return
        try:
            self._update_settings()
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc)); return
        self._begin_upload()

    def _begin_upload(self):
        if self.current_frame is None:
            return False
        if self.uploading:
            self.log("Upload già in corso: nuovo tentativo rinviato")
            return False
        image = self.compose(self.current_frame.copy(), datetime.now())
        s = Settings(**asdict(self.settings))
        self.uploading = True
        threading.Thread(target=self._upload_thread, args=(image, s), daemon=True).start()
        return True

    def _upload_thread(self, image: Image.Image, settings: Settings):
        try:
            buf = BytesIO()
            image.convert("RGB").save(buf, "JPEG", quality=settings.jpeg_quality, optimize=True)
            buf.seek(0)
            with self._connect_ftp(settings) as ftp:
                self.log_async(f"FTP: invio di '{settings.ftp_filename}' ({len(buf.getbuffer()) // 1024} KB)...")
                ftp.storbinary(f"STOR {settings.ftp_filename}", buf)
                self.log_async("FTP: trasferimento accettato dal server")
                self.log_async("FTP: chiusura connessione")
            self.log_async(f"Upload completato: {settings.ftp_filename} ({buf.tell() // 1024} KB)")
        except Exception as exc:
            self.log_async(f"ERRORE upload: {exc}")
        finally:
            self.uploading = False

    def _get_logo(self, frame_w: int) -> Image.Image | None:
        path = self.png_var.get().strip()
        if not path:
            return None
        try:
            mtime = Path(path).stat().st_mtime
            key = f"{path}|{self.png_scale_var.get()}|{frame_w}"
            if self.overlay_cache and self.overlay_cache[:2] == (key, mtime):
                return self.overlay_cache[2]
            logo = Image.open(path).convert("RGBA")
            target_w = max(1, int(frame_w * self.png_scale_var.get() / 100))
            target_h = max(1, int(logo.height * target_w / logo.width))
            logo = logo.resize((target_w, target_h), Image.Resampling.LANCZOS)
            self.overlay_cache = (key, mtime, logo)
            return logo
        except Exception:
            return None

    def compose(self, image: Image.Image, stamp: datetime) -> Image.Image:
        image = image.convert("RGBA")
        w, h = image.size
        logo = self._get_logo(w)
        if logo:
            x = int(self.settings.png_x * max(1, w - logo.width))
            y = int(self.settings.png_y * max(1, h - logo.height))
            image.alpha_composite(logo, (x, y))
        if self.dt_enabled_var.get():
            draw = ImageDraw.Draw(image)
            try:
                font = ImageFont.truetype(self.font_var.get(), self.font_size_var.get())
            except (OSError, ValueError):
                font = ImageFont.load_default()
            text = stamp.strftime(self.dt_format_var.get())
            box = draw.textbbox((0, 0), text, font=font, stroke_width=max(0, self.outline_var.get()))
            tw, th = box[2] - box[0], box[3] - box[1]
            x = int(self.settings.datetime_x * max(1, w - tw))
            y = int(self.settings.datetime_y * max(1, h - th))
            if self.shadow_var.get():
                draw.text((x + 3, y + 3), text, font=font, fill="#000000A0")
            draw.text((x, y), text, font=font, fill=self.color_var.get(),
                      stroke_width=max(0, self.outline_var.get()), stroke_fill=self.outline_color_var.get())
        return image.convert("RGB")

    def _render_preview(self):
        if self.current_frame is None or not hasattr(self, "canvas"):
            return
        try:
            self._update_settings()
            rendered = self.compose(self.current_frame.copy(), datetime.now())
        except (ValueError, tk.TclError):
            return
        self.composited_frame = rendered
        cw, ch = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        scale = min(cw / rendered.width, ch / rendered.height)
        pw, ph = int(rendered.width * scale), int(rendered.height * scale)
        preview = rendered.resize((pw, ph), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image((cw - pw) // 2, (ch - ph) // 2, anchor="nw", image=self.preview_photo, tags="frame")
        self.preview_rect = ((cw - pw) // 2, (ch - ph) // 2, pw, ph)

    def _drag_start(self, event):
        if self.current_frame is None or not hasattr(self, "preview_rect"):
            return
        ox, oy, pw, ph = self.preview_rect
        fx = (event.x - ox) / max(1, pw) * self.current_frame.width
        fy = (event.y - oy) / max(1, ph) * self.current_frame.height
        logo = self._get_logo(self.current_frame.width)
        if logo:
            lx = self.settings.png_x * max(1, self.current_frame.width - logo.width)
            ly = self.settings.png_y * max(1, self.current_frame.height - logo.height)
            if lx <= fx <= lx + logo.width and ly <= fy <= ly + logo.height:
                self.drag_target = "png"; return
        self.drag_target = "datetime" if self.dt_enabled_var.get() else None

    def _drag_move(self, event):
        if not self.drag_target or not hasattr(self, "preview_rect"):
            return
        ox, oy, pw, ph = self.preview_rect
        nx = min(1.0, max(0.0, (event.x - ox) / max(1, pw)))
        ny = min(1.0, max(0.0, (event.y - oy) / max(1, ph)))
        if self.drag_target == "png":
            self.settings.png_x, self.settings.png_y = nx, ny
        else:
            self.settings.datetime_x, self.settings.datetime_y = nx, ny
        self._render_preview()

    def _tick(self):
        try:
            while True:
                self.current_frame = self.frame_queue.get_nowait()
        except queue.Empty:
            pass
        try:
            while True:
                self.log(self.log_queue.get_nowait())
        except queue.Empty:
            pass
        self._render_preview()
        if self.running:
            remaining = max(0, int(self.next_upload - time.monotonic()))
            if self.current_frame is None:
                self.status_var.set("Servizio attivo — attesa video")
            elif self.uploading:
                self.status_var.set("Servizio attivo — upload in corso")
            else:
                self.status_var.set(f"Servizio attivo — prossimo upload tra {remaining}s")
            if time.monotonic() >= self.next_upload:
                if self.current_frame is None:
                    self.next_upload = time.monotonic() + 1
                elif self._begin_upload():
                    if self.waiting_for_first_frame:
                        self.log("Primo fotogramma ricevuto: avvio upload automatico")
                        self.waiting_for_first_frame = False
                    self.next_upload = time.monotonic() + self.settings.interval_seconds
        self.after(200, self._tick)

    def log_async(self, message: str):
        self.log_queue.put(message)

    def log(self, message: str):
        if not hasattr(self, "log_text"):
            return
        line = f"[{datetime.now():%H:%M:%S}] {message}\n"
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, line)
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _create_tray_icon(self):
        try:
            tray_image = Image.open(bundled_path("assets/camera-icon.ico")).convert("RGBA")
            menu = pystray.Menu(
                pystray.MenuItem("Apri", lambda *_: self.after(0, self.show_window), default=True),
                pystray.MenuItem("Start", lambda *_: self.after(0, self.start_service)),
                pystray.MenuItem("Stop", lambda *_: self.after(0, self.stop_service)),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Esci", lambda *_: self.after(0, self.exit_app)),
            )
            self.tray_icon = pystray.Icon("rtsp_snapshot_ftp", tray_image, APP_NAME, menu)
            self.tray_icon.run_detached()
        except Exception as exc:
            self.tray_icon = None
            self.log(f"Area di notifica non disponibile: {exc}")

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def on_close(self):
        if self.tray_icon:
            self.withdraw()
            self.log("Finestra nascosta nell'area di notifica; il servizio continua")
            try:
                self.tray_icon.notify("L'app continua a funzionare in background.", APP_NAME)
            except Exception:
                pass
        else:
            self.exit_app()

    def exit_app(self):
        try:
            self._update_settings()
            self.settings.save()
        except Exception:
            pass
        self.worker.stop()
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
