#!/usr/bin/env python3
"""
GhostInk
--------
Draw with a pen tablet on a fully transparent canvas and record it
straight to a video file that keeps the transparent background --
no screen recording, no chroma key.

How it works: the canvas is an in-memory RGBA image. While recording,
a timer fires at a fixed frame rate, grabs the raw bytes of that image
exactly as it looks (including alpha), and pipes them straight into a
running ffmpeg process, which encodes them into a WebM (VP9 + alpha)
or MOV (QuickTime Animation, lossless) file.

Requirements:
    - Python 3.10+
    - PySide6            (pip install PySide6)
    - ffmpeg on PATH     (sudo apt install ffmpeg)

Run:
    python3 main.py
"""

import os
import re
import sys
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QEvent, QRectF, QThread, Signal, QSettings, QUrl
from PySide6.QtGui import (
    QImage, QPainter, QPen, QColor, QTabletEvent, QPixmap,
    QShortcut, QKeySequence,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QPushButton, QSlider,
    QColorDialog, QComboBox, QFileDialog, QMessageBox, QStatusBar,
    QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea, QButtonGroup,
    QGraphicsDropShadowEffect, QSizePolicy, QProgressBar, QCheckBox,
)

try:
    from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink
    MEDIA_OK = True
except Exception:
    MEDIA_OK = False

# ---------------------------------------------------------------------------
# Tweak these if you want a different canvas / video size or frame rate.
# ---------------------------------------------------------------------------
CANVAS_WIDTH = 1280
CANVAS_HEIGHT = 720
FPS = 30

SIDEBAR_WIDTH = 248

BG        = "#0a0a0d"
PANEL_A   = "#121217"
PANEL_B   = "#0e0e12"
PANEL_2   = "#181820"
PANEL_3   = "#20202a"
BORDER    = "#24242e"
BORDER_HI = "#363642"
TEXT      = "#f4f4f6"
DIM       = "#8f8f9e"
ACCENT    = "#79e6c3"
RED       = "#ff4d5e"

PALETTE = [
    "#ffffff", "#141414", "#8e8e9a", "#ff4d5e", "#ff9f0a", "#ffd60a",
    "#30d158", "#64d2ff", "#4cc9f0", "#5e5ce6", "#bf5af2", "#ff375f",
]

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mkv", ".mov", ".webm", ".avi", ".m4v", ".ts", ".flv"}
MEDIA_FILTER = "Media (*.png *.jpg *.jpeg *.bmp *.webp *.gif *.tif *.tiff " \
               "*.mp4 *.mkv *.mov *.webm *.avi *.m4v *.ts *.flv)"

STYLESHEET = """
* { outline: none; }

QWidget {
    background: %(bg)s;
    color: %(text)s;
    font-family: 'Space Grotesk', 'Inter', 'Segoe UI', 'Noto Sans', 'Ubuntu', sans-serif;
    font-size: 13px;
}

QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { width: 0px; }
QScrollBar:horizontal { height: 0px; }

#sidebar {
    background: %(panelA)s;
    border-right: 1px solid %(border)s;
}

#canvasHost { background: #0b0b0f; }

#brandMark {
    background: %(accent)s;
    color: #0a0a0d;
    font-weight: 800;
    font-size: 16px;
}
#brandTitle { font-size: 14px; font-weight: 700; letter-spacing: 0.5px; background: transparent; }
#brandSub   { font-size: 11px; color: %(dim)s; background: transparent; }

QLabel[cls="section"] {
    color: %(dim)s;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
    background: transparent;
}
QLabel[cls="rule"] { background: %(border)s; }
#sizeVal { color: %(dim)s; font-weight: 600; font-size: 11px; background: transparent; }
#hintLbl { color: %(dim)s; font-size: 10px; background: transparent; }
#recChip {
    color: %(text)s;
    font-weight: 700;
    letter-spacing: 1px;
    background: #1c1114;
    border: 1px solid rgba(255, 77, 94, 0.35);
    padding: 5px 12px;
}
#statusPerm { color: %(dim)s; }

QPushButton {
    background: %(panel2)s;
    color: %(text)s;
    border: 1px solid %(border)s;
    padding: 7px 12px;
    font-weight: 600;
}
QPushButton:hover  { background: %(panel3)s; border-color: %(borderHi)s; }
QPushButton:pressed { background: %(bg)s; }
QPushButton:disabled { color: %(dim)s; background: %(panelA)s; }

QPushButton#recordBtn {
    border: none;
    padding: 13px 0px;
    font-size: 14px;
}

QComboBox {
    background: %(panel2)s;
    border: 1px solid %(border)s;
    padding: 7px 10px;
    color: %(text)s;
    font-weight: 600;
}
QComboBox:hover  { background: %(panel3)s; border-color: %(borderHi)s; }
QComboBox:disabled { color: %(dim)s; background: %(panelA)s; }
QComboBox::drop-down { border: none; width: 22px; }
QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid %(dim)s;
    margin-right: 6px;
}
QComboBox QAbstractItemView {
    background: %(panel2)s;
    border: 1px solid %(borderHi)s;
    selection-background-color: %(selBg)s;
    selection-color: #ffffff;
    outline: none;
}
QComboBox QAbstractItemView::item { min-height: 32px; padding: 2px 8px; }

QSlider::groove:horizontal {
    height: 4px;
    background: %(panel2)s;
}
QSlider::sub-page:horizontal { background: %(accent)s; }
QSlider::add-page:horizontal { background: %(panel2)s; }
QSlider::handle:horizontal {
    width: 12px;
    height: 18px;
    margin: -7px 0px;
    background: %(text)s;
    border: none;
}
QSlider::handle:horizontal:hover { background: %(accent)s; }

QStatusBar {
    background: %(panelB)s;
    color: %(dim)s;
    border-top: 1px solid %(border)s;
}
QStatusBar::item { border: none; }

QToolTip {
    background: #060608;
    color: %(text)s;
    border: 1px solid %(borderHi)s;
    padding: 5px 8px;
}

QMessageBox, QDialog { background: %(panelA)s; }
QMessageBox QLabel { background: transparent; color: %(text)s; }

QProgressBar {
    background: %(panel2)s;
    border: 1px solid %(border)s;
    text-align: center;
    color: %(text)s;
    font-size: 10px;
}
QProgressBar::chunk { background: %(accent)s; }

QCheckBox {
    spacing: 9px;
    background: transparent;
    color: %(text)s;
    font-weight: 600;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border: 1px solid %(borderHi)s;
    background: %(panel2)s;
}
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked {
    background: %(accent)s;
    border-color: %(accent)s;
}
"""

REC_QSS_IDLE = """
QPushButton#recordBtn {
    background: %(red)s;
    color: #ffffff;
    font-weight: 800;
}
QPushButton#recordBtn:hover { background: #ff6575; }
QPushButton#recordBtn:pressed { background: #e13a4c; }
""" % dict(red=RED)

REC_QSS_ACTIVE = """
QPushButton#recordBtn {
    background: #1c1216;
    border: 1px solid rgba(255, 77, 94, 0.45);
    color: #ff96a1;
    font-weight: 800;
}
QPushButton#recordBtn:hover { background: #241419; }
"""


def _swatch_qss(hex_color):
    return f"""
QPushButton {{
    background: {hex_color};
    border: 2px solid rgba(255, 255, 255, 0.08);
    padding: 0px;
}}
QPushButton:hover {{ border-color: rgba(255, 255, 255, 0.45); }}
QPushButton:checked {{ border: 2px solid {ACCENT}; }}
QPushButton:pressed {{ background: {hex_color}; }}
"""


class BrushPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(48, 48)
        self.brush_color = QColor(20, 20, 20, 255)
        self.brush_w = 4.0

    def set_params(self, color, width):
        self.brush_color = QColor(color)
        self.brush_w = float(width)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        cx, cy = self.width() / 2, self.height() / 2
        ring = QPen(QColor(BORDER_HI))
        ring.setWidth(1)
        p.setPen(ring)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(cx - 21, cy - 21, 42, 42))
        d = 4 + (self.brush_w - 1) * (26.0 / 29.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self.brush_color)
        p.drawEllipse(QRectF(cx - d / 2, cy - d / 2, d, d))


# ---------------------------------------------------------------------------
# Canvas: the persistent RGBA surface you draw into with the pen.
# This is the exact thing that gets recorded, frame by frame.
# The checkerboard / rounded corners below are preview-only cosmetics and
# never reach the recorded bytes.
# ---------------------------------------------------------------------------
class Canvas(QWidget):
    def __init__(self, width, height, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WidgetAttribute.WA_StaticContents)
        self.setAttribute(Qt.WidgetAttribute.WA_TabletTracking, True)

        self.image = QImage(width, height, QImage.Format.Format_RGBA8888)
        self.image.fill(Qt.GlobalColor.transparent)

        self.pen_color = QColor(255, 255, 255, 255)
        self.base_width = 4.0

        self.bg_image = None
        self.bg_opacity = 1.0

        self._drawing = False
        self._last_point = None
        self._undo_stack = []
        self._max_undo = 25

        dpr = self.devicePixelRatioF()
        self._checker = QPixmap(int(width * dpr), int(height * dpr))
        self._checker.setDevicePixelRatio(dpr)
        cp = QPainter(self._checker)
        light = QColor("#191920")
        dark = QColor("#141419")
        size = 12
        for y in range(0, height, size):
            for x in range(0, width, size):
                cp.fillRect(x, y, size, size,
                            light if (x // size + y // size) % 2 == 0 else dark)
        cp.end()

    def _stroke_width(self, pressure):
        return max(1.0, self.base_width * (0.25 + 0.9 * pressure))

    def _draw_segment(self, p1, p2, pressure):
        painter = QPainter(self.image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self.pen_color)
        pen.setWidthF(self._stroke_width(pressure))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawLine(p1, p2)
        painter.end()
        self.update()

    def _push_undo(self):
        self._undo_stack.append(self.image.copy())
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)

    def undo(self):
        if self._undo_stack:
            self.image = self._undo_stack.pop()
            self.update()

    def clear(self):
        self._push_undo()
        self.image.fill(Qt.GlobalColor.transparent)
        self.update()

    def tabletEvent(self, event: QTabletEvent):
        pos = event.position()
        pressure = event.pressure()
        etype = event.type()

        if etype == QEvent.Type.TabletPress:
            self._push_undo()
            self._drawing = True
            self._last_point = pos
        elif etype == QEvent.Type.TabletMove and self._drawing:
            self._draw_segment(self._last_point, pos, pressure)
            self._last_point = pos
        elif etype == QEvent.Type.TabletRelease:
            self._drawing = False
            self._last_point = None

        event.accept()

    def mousePressEvent(self, event):
        self._push_undo()
        self._drawing = True
        self._last_point = event.position()

    def mouseMoveEvent(self, event):
        if self._drawing:
            self._draw_segment(self._last_point, event.position(), 1.0)
            self._last_point = event.position()

    def mouseReleaseEvent(self, event):
        self._drawing = False
        self._last_point = None

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.drawPixmap(0, 0, self._checker)
        bg = self.bg_image
        if bg is not None and not bg.isNull():
            p.setOpacity(max(0.0, min(1.0, self.bg_opacity)))
            p.drawImage(0, 0, bg)
            p.setOpacity(1.0)
        p.drawImage(0, 0, self.image)
        p.setPen(QPen(QColor("#363642"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    def frame_bytes(self):
        img = self.image
        if img.format() != QImage.Format.Format_RGBA8888:
            img = img.convertToFormat(QImage.Format.Format_RGBA8888)
        ptr = img.constBits()
        try:
            return bytes(ptr)
        except TypeError:
            ptr.setsize(img.sizeInBytes())
            return bytes(ptr)


# ---------------------------------------------------------------------------
# Recorder: captures raw RGBA frames and turns them into a video.
#   mode == "live"      -> frames stream to ffmpeg while recording
#   mode == "deferred"  -> frames spooled to a temp file, encoded on stop
# ---------------------------------------------------------------------------
class Recorder:
    FORMATS = {
        "webm": {
            "label": "WebM · VP9 alpha",
            "ext": "webm",
            "args": ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p",
                      "-b:v", "0", "-crf", "28", "-row-mt", "1"],
        },
        "mov": {
            "label": "MOV · lossless",
            "ext": "mov",
            "args": ["-c:v", "qtrle"],
        },
    }

    def __init__(self, width, height, fps):
        self.width = width
        self.height = height
        self.fps = fps
        self.proc = None
        self.mode = None
        self.output_path = None
        self.fmt_key = None
        self.frame_count = 0
        self.temp_path = None
        self.temp_file = None

    def start(self, mode, output_path, fmt_key):
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "ffmpeg not found. Install it with: sudo apt install ffmpeg"
            )
        self.mode = mode
        self.output_path = output_path
        self.fmt_key = fmt_key
        self.frame_count = 0

        fmt = self.FORMATS[fmt_key]
        if mode == "live":
            cmd = self._ffmpeg_cmd("-")
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            fd, path = tempfile.mkstemp(suffix=".rgba")
            os.close(fd)
            self.temp_path = Path(path)
            self.temp_file = open(self.temp_path, "wb")

    def _ffmpeg_cmd(self, input_source):
        fmt = self.FORMATS[self.fmt_key]
        return [
            "ffmpeg", "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{self.width}x{self.height}",
            "-r", str(self.fps),
            "-i", str(input_source),
            *fmt["args"],
            str(self.output_path),
        ]

    def write_frame(self, frame_bytes):
        if self.mode == "live":
            if self.proc and self.proc.stdin:
                try:
                    self.proc.stdin.write(frame_bytes)
                except BrokenPipeError:
                    pass
        else:
            self.temp_file.write(frame_bytes)
            self.frame_count += 1

    def close_live(self):
        if self.proc and self.proc.stdin:
            try:
                self.proc.stdin.close()
            except BrokenPipeError:
                pass

    def close_temp(self):
        if self.temp_file:
            try:
                self.temp_file.close()
            except Exception:
                pass
            self.temp_file = None

    def finalize_live(self):
        if self.proc:
            self.proc.wait()
            self.proc = None

    def encode_command(self):
        return self._ffmpeg_cmd(self.temp_path)

    def frame_total(self):
        return self.frame_count


class EncodeWorker(QThread):
    progress = Signal(int, str)
    done = Signal(bool, str)

    def __init__(self, cmd, total, temp_path):
        super().__init__()
        self.cmd = cmd
        self.total = total
        self.temp_path = Path(temp_path)

    def run(self):
        try:
            proc = subprocess.Popen(
                self.cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
            )
            for raw in proc.stderr:
                if not self.total:
                    continue
                line = raw.decode("utf-8", "ignore")
                m = re.search(r"frame=\s*(\d+)", line)
                if m:
                    f = int(m.group(1))
                    pct = min(99, int(f / self.total * 100))
                    self.progress.emit(pct, f"Rendering… {pct}%")
            proc.wait()
            ok = proc.returncode == 0
            if self.temp_path.exists():
                self.temp_path.unlink(missing_ok=True)
            self.done.emit(ok, "Recording saved." if ok else "Encoding failed.")
        except Exception as e:
            if self.temp_path.exists():
                try:
                    self.temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            self.done.emit(False, f"Encoding error: {e}")


class FinalizeWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, proc):
        super().__init__()
        self.proc = proc

    def run(self):
        self.proc.wait()
        self.done.emit(self.proc.returncode == 0, "Recording saved.")


def _fmt_time(seconds):
    s = int(seconds)
    return f"{s // 60:02d}:{s % 60:02d}"


# ---------------------------------------------------------------------------
# Main window / UI
# ---------------------------------------------------------------------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GhostInk")
        self.setMinimumSize(1120, 880)
        self.resize(1520, 980)

        self.canvas = Canvas(CANVAS_WIDTH, CANVAS_HEIGHT)
        self.recorder = Recorder(CANVAS_WIDTH, CANVAS_HEIGHT, FPS)
        self.recording = False
        self.record_start_time = None
        self._pulse_on = True

        self.settings = QSettings("GhostInk", "GhostInk")
        self.bg_is_video = False
        self._scrubbing = False
        self._frame_parity = 0
        self._primed_src = None

        self.player = None
        if MEDIA_OK:
            self.audio_out = QAudioOutput()
            self.audio_out.setVolume(1.0)
            self.player = QMediaPlayer()
            self.player.setAudioOutput(self.audio_out)
            self.video_sink = QVideoSink()
            self.player.setVideoSink(self.video_sink)
            self.video_sink.videoFrameChanged.connect(self._on_video_frame)
            self.player.positionChanged.connect(self._on_position)
            self.player.durationChanged.connect(self._on_duration)
            self.player.mediaStatusChanged.connect(self._on_media_status)
            self.player.playbackStateChanged.connect(self._on_play_state)
            self.player.errorOccurred.connect(self._on_media_error)

        self._build_ui()
        self._build_shortcuts()
        self._restore_settings()

        self.frame_timer = QTimer(self)
        self.frame_timer.setInterval(int(1000 / FPS))
        self.frame_timer.timeout.connect(self._capture_frame)

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(200)
        self.ui_timer.timeout.connect(self._update_status)

    # -- layout ------------------------------------------------------------
    def _build_ui(self):
        root = QWidget()
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._build_sidebar())

        host = QWidget(objectName="canvasHost")
        host.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        host_layout = QVBoxLayout(host)
        host_layout.setContentsMargins(44, 36, 44, 36)

        stage = QWidget()
        stage_layout = QVBoxLayout(stage)
        stage_layout.setContentsMargins(0, 0, 0, 0)
        stage_layout.setSpacing(14)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 170))
        self.canvas.setGraphicsEffect(shadow)
        stage_layout.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter)
        stage_layout.addWidget(self._build_transport())
        host_layout.addWidget(stage, 0, Qt.AlignmentFlag.AlignCenter)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(host)

        root_layout.addWidget(scroll, 1)
        self.setCentralWidget(root)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status = status
        status.showMessage("Ready — draw with the tablet pen, only the canvas gets recorded.")
        perm = QLabel(f"{CANVAS_WIDTH} × {CANVAS_HEIGHT} · {FPS} fps", objectName="statusPerm")
        status.addPermanentWidget(perm)

    def _build_transport(self):
        bar = QWidget()
        bar.setFixedHeight(42)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(12)

        self.play_btn = QPushButton("Play")
        self.play_btn.setFixedWidth(84)
        self.play_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.setToolTip("Play / pause background (Space)")
        self.play_btn.clicked.connect(self._toggle_play)
        h.addWidget(self.play_btn)

        self.time_cur = QLabel("00:00", objectName="sizeVal")
        self.time_cur.setMinimumWidth(42)
        h.addWidget(self.time_cur)

        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 0)
        self.scrub.sliderPressed.connect(self._on_scrub_pressed)
        self.scrub.sliderReleased.connect(self._on_scrub_released)
        self.scrub.sliderMoved.connect(self._on_scrub_moved)
        h.addWidget(self.scrub, 1)

        self.time_dur = QLabel("00:00", objectName="sizeVal")
        self.time_dur.setMinimumWidth(42)
        h.addWidget(self.time_dur)

        self.mute_btn = QPushButton("Mute")
        self.mute_btn.setCheckable(True)
        self.mute_btn.setFixedWidth(84)
        self.mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.mute_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.mute_btn.setToolTip("Mute / unmute background audio")
        self.mute_btn.toggled.connect(self._toggle_mute)
        h.addWidget(self.mute_btn)

        self.transport = bar
        bar.setVisible(False)
        return bar

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setProperty("cls", "section")
        return lbl

    def _rule(self):
        lbl = QLabel()
        lbl.setProperty("cls", "rule")
        lbl.setFixedHeight(1)
        return lbl

    def _build_sidebar(self):
        side = QWidget(objectName="sidebar")
        side.setFixedWidth(SIDEBAR_WIDTH)
        col = QVBoxLayout(side)
        col.setContentsMargins(18, 18, 18, 18)
        col.setSpacing(12)

        brand = QHBoxLayout()
        brand.setSpacing(11)
        mark = QLabel("G", objectName="brandMark")
        mark.setFixedSize(40, 40)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        t1 = QLabel("GhostInk", objectName="brandTitle")
        t2 = QLabel("transparent ink, recorded", objectName="brandSub")
        titles.addWidget(t1)
        titles.addWidget(t2)
        brand.addWidget(mark)
        brand.addLayout(titles, 1)
        col.addLayout(brand)

        col.addWidget(self._rule())

        col.addWidget(self._section_label("PEN"))

        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 2, 0, 2)
        grid.setSpacing(9)
        self._preset_group = QButtonGroup(self)
        self._preset_group.setExclusive(True)
        default_hex = self.canvas.pen_color.name().lower()
        checked_idx = 0
        for i, hex_color in enumerate(PALETTE):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(30, 30)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(hex_color.upper())
            btn.setStyleSheet(_swatch_qss(hex_color))
            btn.clicked.connect(lambda _=False, c=hex_color: self._use_preset(c))
            self._preset_group.addButton(btn, i)
            grid.addWidget(btn, i // 6, i % 6)
            if hex_color.lower() == default_hex:
                checked_idx = i
        self._preset_group.button(checked_idx).setChecked(True)

        self.custom_btn = QPushButton("  Custom…")
        self.custom_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.custom_btn.setIcon(self._rainbow_icon())
        self.custom_btn.setIconSize(QPixmap(18, 18).size())
        self.custom_btn.setToolTip("Pick any color")
        self.custom_btn.setStatusTip("Pick a custom pen color")
        self.custom_btn.clicked.connect(self._pick_custom_color)
        col.addWidget(grid_holder)
        col.addWidget(self.custom_btn)

        width_row = QHBoxLayout()
        width_row.setSpacing(10)
        self.width_slider = QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(1, 30)
        self.width_slider.setValue(int(self.canvas.base_width))
        self.width_slider.valueChanged.connect(self._set_width)
        self.preview = BrushPreview()
        self.preview.set_params(self.canvas.pen_color, self.canvas.base_width)
        width_row.addWidget(self.width_slider, 1)
        width_row.addWidget(self.preview)
        col.addLayout(width_row)

        col.addWidget(self._rule())
        col.addWidget(self._section_label("CANVAS"))

        actions = QHBoxLayout()
        actions.setSpacing(9)
        undo_btn = QPushButton("Undo")
        undo_btn.setStatusTip("Undo last stroke (Ctrl+Z)")
        undo_btn.clicked.connect(self.canvas.undo)
        clear_btn = QPushButton("Clear")
        clear_btn.setStatusTip("Clear the canvas")
        clear_btn.clicked.connect(self._clear_canvas)
        actions.addWidget(undo_btn, 1)
        actions.addWidget(clear_btn, 1)
        col.addLayout(actions)

        col.addWidget(self._rule())
        col.addWidget(self._section_label("BACKGROUND"))

        bg_actions = QHBoxLayout()
        bg_actions.setSpacing(9)
        self.load_bg_btn = QPushButton("Load…")
        self.load_bg_btn.setStatusTip("Load an image or video as preview background")
        self.load_bg_btn.clicked.connect(self._load_background)
        self.clear_bg_btn = QPushButton("Remove")
        self.clear_bg_btn.setStatusTip("Remove the background preview")
        self.clear_bg_btn.clicked.connect(self._clear_background)
        self.clear_bg_btn.setEnabled(False)
        bg_actions.addWidget(self.load_bg_btn, 1)
        bg_actions.addWidget(self.clear_bg_btn, 1)
        col.addLayout(bg_actions)

        self.bg_opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.bg_opacity_slider.setRange(10, 100)
        self.bg_opacity_slider.setValue(100)
        self.bg_opacity_slider.setToolTip("Background opacity")
        self.bg_opacity_slider.valueChanged.connect(self._set_bg_opacity)
        col.addWidget(self.bg_opacity_slider)

        self.play_on_record_cb = QCheckBox("Play when recording starts")
        self.play_on_record_cb.setChecked(True)
        self.play_on_record_cb.toggled.connect(self._bg_setting_changed)
        col.addWidget(self.play_on_record_cb)

        self.light_preview_cb = QCheckBox("Light preview while recording")
        self.light_preview_cb.toggled.connect(self._bg_setting_changed)
        col.addWidget(self.light_preview_cb)

        self.loop_cb = QCheckBox("Loop background")
        self.loop_cb.setChecked(True)
        self.loop_cb.toggled.connect(self._toggle_loop)
        col.addWidget(self.loop_cb)

        col.addWidget(self._rule())
        col.addWidget(self._section_label("OUTPUT"))

        self.format_combo = QComboBox()
        for key, fmt in Recorder.FORMATS.items():
            self.format_combo.addItem(fmt["label"], key)
        col.addWidget(self.format_combo)

        col.addWidget(QLabel("Render", objectName="hintLbl"))
        self.render_mode_combo = QComboBox()
        self.render_mode_combo.addItem("Live · encode now", "live")
        self.render_mode_combo.addItem("After stop", "deferred")
        col.addWidget(self.render_mode_combo)

        col.addStretch(1)

        self.render_box = QWidget()
        rbox = QVBoxLayout(self.render_box)
        rbox.setContentsMargins(0, 4, 0, 4)
        rbox.setSpacing(6)
        self.progress_label = QLabel("Rendering…", objectName="hintLbl")
        self.progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(14)
        rbox.addWidget(self.progress_label)
        rbox.addWidget(self.progress)
        self.render_box.hide()
        col.addWidget(self.render_box)

        self.rec_chip = QLabel("● REC  00:00", objectName="recChip")
        self.rec_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.rec_chip.hide()
        col.addWidget(self.rec_chip)

        self.record_btn = QPushButton("●  Record", objectName="recordBtn")
        self.record_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.record_btn.setStyleSheet(REC_QSS_IDLE)
        self.record_btn.setToolTip("Start / stop recording (Ctrl+R)")
        self.record_btn.setStatusTip("Record the canvas to an alpha video")
        self.record_btn.clicked.connect(self._toggle_recording)
        col.addWidget(self.record_btn)

        hints = QLabel("Ctrl+Z undo · Ctrl+R record · Esc stop", objectName="hintLbl")
        hints.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(hints)

        return side

    @staticmethod
    def _rainbow_icon():
        pm = QPixmap(18, 18)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        n = 9
        w = 18 / n
        for i in range(n):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor.fromHsvF(i / n, 0.85, 0.95))
            p.drawRect(QRectF(i * w, 0, w + 0.5, 18))
        p.end()
        return pm

    def _build_shortcuts(self):
        QShortcut(QKeySequence.Undo, self, activated=self.canvas.undo)
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self._clear_canvas)
        QShortcut(QKeySequence("Ctrl+R"), self, activated=self._toggle_recording)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._escape)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=self._toggle_play)

    def _repolish(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    # -- pen controls --------------------------------------------------------
    def _set_mark(self, color):
        self.canvas.pen_color = QColor(color)
        self.preview.set_params(self.canvas.pen_color, self.canvas.base_width)

    def _use_preset(self, hex_color):
        self._set_mark(hex_color)
        self.custom_btn.setProperty("sel", False)
        self._repolish(self.custom_btn)

    def _pick_custom_color(self):
        color = QColorDialog.getColor(self.canvas.pen_color, self, "Pen color")
        if not color.isValid():
            return
        self._set_mark(color)
        for btn in self._preset_group.buttons():
            btn.setChecked(False)
        self.custom_btn.setProperty("sel", True)
        self._repolish(self.custom_btn)

    def _set_width(self, value):
        self.canvas.base_width = float(value)
        self.preview.set_params(self.canvas.pen_color, self.canvas.base_width)

    # -- canvas actions ------------------------------------------------------
    def _clear_canvas(self):
        if self.recording:
            QMessageBox.warning(self, "Recording",
                                 "Stop recording before clearing the canvas.")
            return
        self.canvas.clear()

    def _escape(self):
        if self.recording:
            self._stop_recording()

    # -- background preview ---------------------------------------------------
    def _load_background(self):
        videos_dir = Path.home() / "Videos"
        path, _ = QFileDialog.getOpenFileName(
            self, "Load background", str(videos_dir), MEDIA_FILTER
        )
        if not path:
            return
        self._apply_background(path)

    def _apply_background(self, path):
        ext = Path(path).suffix.lower()
        if ext in VIDEO_EXTS:
            if not MEDIA_OK:
                QMessageBox.warning(
                    self, "Background",
                    "Video preview needs Qt Multimedia, which is not available"
                    " in this environment. Images still work.")
                return
            try:
                self.bg_is_video = True
                self.player.setSource(QUrl.fromLocalFile(path))
                self.transport.setVisible(True)
            except Exception as e:
                self.bg_is_video = False
                self.transport.setVisible(False)
                QMessageBox.warning(self, "Background",
                                    f"Could not open this video: {e}")
                return
        elif ext in IMAGE_EXTS:
            self.bg_is_video = False
            if self.player:
                self.player.setSource(QUrl())
                self.player.pause()
            pm = QPixmap(path)
            if pm.isNull():
                QMessageBox.warning(self, "Background", "Could not load image.")
                return
            scaled = pm.scaled(
                CANVAS_WIDTH, CANVAS_HEIGHT,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            self.canvas.bg_image = scaled.toImage()
            self.canvas.update()
            self.transport.setVisible(False)
        else:
            QMessageBox.warning(self, "Background", "Unsupported file type.")
            return

        self.bg_path = path
        self.clear_bg_btn.setEnabled(True)
        self.settings.setValue("bg_path", path)

    def _clear_background(self):
        self.bg_path = None
        self.bg_is_video = False
        if self.player:
            self.player.pause()
            self.player.setSource(QUrl())
        self.canvas.bg_image = None
        self.canvas.update()
        self.transport.setVisible(False)
        self.clear_bg_btn.setEnabled(False)
        self.settings.remove("bg_path")

    def _set_bg_opacity(self, value):
        self.canvas.bg_opacity = value / 100.0
        self.settings.setValue("bg_opacity", value)
        self.canvas.update()

    def _bg_setting_changed(self):
        self.settings.setValue("play_on_record", self.play_on_record_cb.isChecked())
        self.settings.setValue("light_preview", self.light_preview_cb.isChecked())

    def _toggle_loop(self, checked):
        self.settings.setValue("loop", checked)

    def _toggle_play(self):
        if not (self.player and self.bg_is_video):
            return
        state = self.player.playbackState()
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            return
        dur = self.player.duration()
        if dur > 0 and self.player.position() >= dur - 100:
            self.player.setPosition(0)
        self.player.play()

    def _toggle_mute(self, checked):
        self.mute_btn.setText("Muted" if checked else "Mute")
        if self.audio_out:
            self.audio_out.setMuted(checked)
        self.settings.setValue("mute", checked)

    def _on_video_frame(self, frame):
        if not frame.isValid():
            return
        if self.recording and self.light_preview_cb.isChecked():
            self._frame_parity ^= 1
            if self._frame_parity:
                return
        img = frame.toImage()
        if img.size() != self.canvas.size():
            img = img.scaled(
                CANVAS_WIDTH, CANVAS_HEIGHT,
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.FastTransformation)
        self.canvas.bg_image = img
        self.canvas.update()

    def _on_scrub_pressed(self):
        self._scrubbing = True

    def _on_scrub_released(self):
        self._scrubbing = False
        if self.player:
            self.player.setPosition(self.scrub.value())

    def _on_scrub_moved(self, value):
        if self.player:
            self.player.setPosition(value)
        self.time_cur.setText(_fmt_time(value / 1000))

    def _on_position(self, ms):
        if not self._scrubbing:
            self.scrub.setValue(ms)
        self.time_cur.setText(_fmt_time(ms / 1000))

    def _on_duration(self, ms):
        self.scrub.setRange(0, max(ms, 0))
        self.time_dur.setText(_fmt_time(ms / 1000))

    def _on_play_state(self, state):
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.play_btn.setText("Pause" if playing else "Play")

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia:
            if self._primed_src != self.bg_path:
                self._primed_src = self.bg_path
                self.player.pause()
                self.player.setPosition(0)
        elif status == QMediaPlayer.MediaStatus.EndOfMedia:
            if self.bg_is_video and self.loop_cb.isChecked():
                self.player.setPosition(0)
                self.player.play()

    def _on_media_error(self, error, error_string):
        if self.bg_is_video:
            QMessageBox.warning(self, "Background",
                                f"Could not play this video: {error_string}")
            self._clear_background()

    def _restore_settings(self):
        self.play_on_record_cb.setChecked(
            self.settings.value("play_on_record", "true") in ("true", True))
        self.light_preview_cb.setChecked(
            self.settings.value("light_preview", "false") in ("true", True))
        self.loop_cb.setChecked(self.settings.value("loop", "true") in ("true", True))
        mute = self.settings.value("mute", "false") in ("true", True)
        self.mute_btn.setChecked(mute)
        self.mute_btn.setText("Muted" if mute else "Mute")
        if self.audio_out:
            self.audio_out.setMuted(mute)
        opacity = int(self.settings.value("bg_opacity", 100))
        self.bg_opacity_slider.setValue(max(10, min(100, opacity)))
        self.canvas.bg_opacity = self.bg_opacity_slider.value() / 100.0
        saved = self.settings.value("bg_path", "")
        if saved and Path(saved).exists():
            self._apply_background(saved)

    # -- recording -----------------------------------------------------------
    def _toggle_recording(self):
        if not self.recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        fmt_key = self.format_combo.currentData()
        ext = Recorder.FORMATS[fmt_key]["ext"]

        videos_dir = Path.home() / "Videos"
        videos_dir.mkdir(exist_ok=True)
        default_name = f"writing_{time.strftime('%Y%m%d_%H%M%S')}.{ext}"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save video as", str(videos_dir / default_name),
            f"Video (*.{ext})",
        )
        if not path:
            return

        mode = self.render_mode_combo.currentData()
        try:
            self.recorder.start(mode, path, fmt_key)
        except (RuntimeError, OSError) as e:
            QMessageBox.critical(self, "Could not start recording", str(e))
            return

        self.recording = True
        self.record_start_time = time.time()
        self.record_btn.setText("■  Stop")
        self.record_btn.setStyleSheet(REC_QSS_ACTIVE)
        self.format_combo.setEnabled(False)
        self.render_mode_combo.setEnabled(False)
        self.rec_chip.show()
        self.frame_timer.start()
        self.ui_timer.start()
        self.status.showMessage(f"Recording to {path} …")

        if (self.bg_is_video and self.player
                and self.play_on_record_cb.isChecked()):
            dur = self.player.duration()
            if dur > 0 and self.player.position() >= dur - 100:
                self.player.setPosition(0)
            self.player.play()

    def _stop_recording(self):
        self.frame_timer.stop()
        self.ui_timer.stop()
        self.recording = False
        if self.player:
            self.player.pause()
        self.record_btn.setText("●  Record")
        self.record_btn.setStyleSheet(REC_QSS_IDLE)
        self.rec_chip.hide()

        mode = self.recorder.mode
        if mode == "live":
            self.recorder.close_live()
            self._busy(True)
            self._show_progress(True)
            self.progress.setRange(0, 0)
            self.progress_label.setText("Finalizing…")
            self._finalize_worker = FinalizeWorker(self.recorder.proc)
            self._finalize_worker.done.connect(self._on_live_finalized)
            self._finalize_worker.start()
        else:
            self.recorder.close_temp()
            total = self.recorder.frame_total()
            self._busy(True)
            self._show_progress(True)
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(0)
            self.progress_label.setText("Rendering… 0%")
            self._encode_worker = EncodeWorker(
                self.recorder.encode_command(), total, self.recorder.temp_path
            )
            self._encode_worker.progress.connect(self._on_encode_progress)
            self._encode_worker.done.connect(self._on_encode_done)
            self._encode_worker.start()

    def _busy(self, on):
        self.record_btn.setEnabled(not on)
        self.render_mode_combo.setEnabled(not on)
        self.format_combo.setEnabled(not on)

    def _show_progress(self, on):
        self.render_box.setVisible(on)

    def _capture_frame(self):
        self.recorder.write_frame(self.canvas.frame_bytes())

    def _on_encode_progress(self, pct, text):
        self.progress.setValue(pct)
        self.progress_label.setText(text)

    def _on_encode_done(self, ok, message):
        self._finish_render(ok, message)

    def _on_live_finalized(self, ok, message):
        self.recorder.proc = None
        self._finish_render(ok, message)

    def _finish_render(self, ok, message):
        self._show_progress(False)
        self._busy(False)
        self.progress.setRange(0, 100)
        if not ok:
            QMessageBox.warning(self, "Recording", message)
        self.status.showMessage(message)

    def _update_status(self):
        elapsed = time.time() - self.record_start_time
        mmss = _fmt_time(elapsed)
        self.status.showMessage(f"Recording… {elapsed:0.1f}s")
        self.record_btn.setText(f"■  Stop   {mmss}")
        dot = "#ff4d5e" if self._pulse_on else "#6e2230"
        self._pulse_on = not self._pulse_on
        self.rec_chip.setText(
            f'<span style="color:{dot};">●</span>  REC&nbsp;&nbsp;{mmss}'
        )

    def closeEvent(self, event):
        if self.player:
            self.player.stop()
        for w in (getattr(self, "_encode_worker", None),
                  getattr(self, "_finalize_worker", None)):
            if w is not None and w.isRunning():
                w.terminate()
                w.wait()
        if self.recording:
            self._force_stop()
        event.accept()

    def _force_stop(self):
        self.frame_timer.stop()
        self.ui_timer.stop()
        self.recording = False
        if self.player:
            self.player.pause()
        self.record_btn.setText("●  Record")
        self.record_btn.setStyleSheet(REC_QSS_IDLE)
        self.rec_chip.hide()
        self._busy(False)
        self._show_progress(False)
        if self.recorder.mode == "live":
            self.recorder.close_live()
            self.recorder.finalize_live()
        else:
            self.recorder.close_temp()
            cmd = self.recorder.encode_command()
            self.recorder.temp_path.unlink(missing_ok=True)
            try:
                subprocess.run(cmd, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, check=True)
            except Exception as e:
                QMessageBox.warning(self, "Recording", f"Encoding failed: {e}")


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET % dict(
        bg=BG, panelA=PANEL_A, panelB=PANEL_B, panel2=PANEL_2, panel3=PANEL_3,
        border=BORDER, borderHi=BORDER_HI, text=TEXT, dim=DIM,
        accent=ACCENT, selBg="#1d3b33",
    ))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
