"""Audio-to-notes transcription engines.

Each engine returns (notes, pedals) where notes is a list of Note and pedals a
list of (start, end) sustain-pedal intervals in seconds.
"""

import math
import os
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Note:
    start: float
    end: float
    pitch: int
    velocity: int


PIANO_SAMPLE_RATE = 16000
PIANO_CHECKPOINT_URL = (
    "https://zenodo.org/record/4034264/files/"
    "CRNN_note_F1%3D0.9677_pedal_F1%3D0.9186.pth?download=1"
)
PIANO_CHECKPOINT_PATH = (
    Path.home() / "piano_transcription_inference_data" / "note_F1=0.9677_pedal_F1=0.9186.pth"
)


def _ensure_checkpoint(path):
    if path.exists() and path.stat().st_size > 1.6e8:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading piano model (~165 MB) to {path} ...", file=sys.stderr)
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(PIANO_CHECKPOINT_URL, tmp)
    tmp.replace(path)


def transcribe_piano(audio, device=None, checkpoint=None):
    """High-resolution piano transcription (Kong et al., ByteDance). Includes pedal."""
    import torch
    from piano_transcription_inference import PianoTranscription

    path = Path(checkpoint) if checkpoint else PIANO_CHECKPOINT_PATH
    if not checkpoint:
        _ensure_checkpoint(path)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"

    # Newer torch defaults to weights_only=True, which this checkpoint predates.
    original_load = torch.load

    def load(*args, **kwargs):
        kwargs.setdefault("weights_only", False)
        return original_load(*args, **kwargs)

    torch.load = load
    try:
        model = PianoTranscription(checkpoint_path=str(path), device=torch.device(device))
    finally:
        torch.load = original_load

    result = model.transcribe(audio, None)
    notes = [
        Note(e["onset_time"], e["offset_time"], int(e["midi_note"]), int(e["velocity"]))
        for e in result["est_note_events"]
    ]
    pedals = [
        (e["onset_time"], e["offset_time"])
        for e in result["est_pedal_events"]
        if math.isfinite(e["onset_time"]) and math.isfinite(e["offset_time"])
    ]
    return notes, pedals


def transcribe_basic_pitch(audio, sample_rate):
    """Spotify Basic Pitch. Instrument-agnostic, lighter, no pedal detection."""
    import soundfile as sf
    from basic_pitch import ICASSP_2022_MODEL_PATH
    from basic_pitch.inference import predict

    fd, wav = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        sf.write(wav, audio, sample_rate)
        _, _, events = predict(
            wav,
            ICASSP_2022_MODEL_PATH,
            minimum_frequency=27.5,
            maximum_frequency=4186.0,
            multiple_pitch_bends=False,
        )
    finally:
        os.remove(wav)
    notes = [
        Note(float(start), float(end), int(pitch), max(1, min(127, int(round(amp * 127)))))
        for start, end, pitch, amp, _ in events
    ]
    return notes, []
