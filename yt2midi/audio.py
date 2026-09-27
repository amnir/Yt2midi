"""Fetching audio from YouTube (or a local file) and decoding it."""

import os
import re
import subprocess

import numpy as np


def ffmpeg_exe():
    """Return a usable ffmpeg binary, preferring the one bundled with imageio-ffmpeg."""
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def is_url(source):
    return re.match(r"^https?://", source) is not None


def download_audio(url, out_dir):
    """Download the best audio stream of a video. Returns (path, title)."""
    import yt_dlp

    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(out_dir, "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "ffmpeg_location": ffmpeg_exe(),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = ydl.prepare_filename(info)
    return path, info.get("title") or info.get("id") or "output"


def load_audio(path, sample_rate, start=None, end=None):
    """Decode any audio/video file to mono float32 at `sample_rate` using ffmpeg."""
    cmd = [ffmpeg_exe(), "-nostdin", "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if end is not None:
        cmd += ["-to", str(end)]
    cmd += ["-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sample_rate), "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + proc.stderr.decode(errors="replace"))
    audio = np.frombuffer(proc.stdout, dtype=np.float32)
    if audio.size == 0:
        raise RuntimeError("No audio decoded from " + path)
    return audio


def parse_time(value):
    """Parse '90', '1:30' or '0:01:30' into seconds."""
    if value is None:
        return None
    seconds = 0.0
    for part in value.split(":"):
        seconds = seconds * 60 + float(part)
    return seconds
