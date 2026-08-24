# GhostInk

<p align="center">
  <strong>Transparent ink, recorded.</strong><br>
  Draw with your pen tablet on a transparent canvas and get a video file with a
  real alpha channel — no screen recording, no chroma key. Every frame is
  grabbed straight from the in-memory RGBA canvas and piped into
  <code>ffmpeg</code> as it happens (or spooled and rendered after you stop).
</p>

---

## Features

- **Real alpha output** — WebM (VP9 + alpha) or MOV (QuickTime Animation,
  lossless). Compositing-ready for OBS, DaVinci Resolve, Premiere, Shotcut.
- **Two render modes**
  - **Live** — encodes with ffmpeg *while* you draw; the file is ready the
    moment you hit stop.
  - **After stop** — frames are spooled to disk while you draw, then encoded
    when you stop, with a live progress bar.
- **Pen-tablet native** — pressure-sensitive stroke width via the generic
  Linux HID tablet driver (Huion, Wacom, XP-Pen, …).
- **Ghost-minimal UI** — flat, sharp-cornered dark theme with a color palette,
  live brush preview, undo (25 strokes), and keyboard shortcuts.

## Install (Ubuntu 24.04)

```bash
sudo apt update
sudo apt install python3-venv ffmpeg

git clone <this-repo> ghostink
cd ghostink
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> Ubuntu 24 blocks plain `pip install` outside a venv — that's what
> `python3-venv` and `source venv/bin/activate` are for.

## Run

```bash
source venv/bin/activate
python3 main.py
```

1. Draw with the tablet pen (mouse works too, for testing).
2. Pick a color / width, choose an output format and render mode.
3. Hit **Record**, choose where to save, write, hit **Stop**.
4. In *After stop* mode, watch the render progress bar — done.

The checkerboard behind the canvas is preview-only; it is never recorded.

## Output formats

| Format | Codec | Best for |
|--------|-------|----------|
| WebM | VP9 + alpha (`yuva420p`) | Web, Chrome/Firefox, OBS browser/media sources. Smaller files. |
| MOV | QuickTime Animation (`qtrle`, lossless) | DaVinci Resolve, Premiere, Shotcut. Much bigger files. |

## Keyboard shortcuts

| Keys | Action |
|------|--------|
| `Ctrl+Z` | Undo last stroke |
| `Ctrl+N` | Clear canvas |
| `Ctrl+R` | Start / stop recording |
| `Esc` | Stop recording |

## Tablet notes (Huion H430P and friends)

The H430P has had mainline Linux kernel support since ~2015 via the generic
HID tablet driver, so on Ubuntu 24 it is recognized out of the box through
`libinput`, pressure included.

To confirm pressure is being read:

```bash
sudo libinput debug-events
```

Touch the pen to the surface with varying force and watch for tablet tool
events where the pressure value changes. If pressure is stuck at 0/1:

1. Huion's official Linux driver (huion.com, lists the H430P).
2. The community DIGImend driver package
   (`Huion-Linux/DIGImend-kernel-drivers-for-Huion` on GitHub,
   docs at digimend.github.io).

## Tweaks

- Canvas size and frame rate are constants at the top of `main.py`
  (`CANVAS_WIDTH`, `CANVAS_HEIGHT`, `FPS`) — change and restart.
- The theme lives in the `STYLESHEET` string and the color constants at the
  top of `main.py`.

## License

MIT — see [LICENSE](LICENSE).
