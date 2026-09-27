"""Command line entry point: yt2midi <youtube-url-or-file> [-o out.mid]."""

import argparse
import os
import re
import sys
import tempfile

from . import audio as audio_mod
from . import engines, midi


def safe_filename(title):
    name = re.sub(r'[\\/:*?"<>|]+', "", title).strip()
    return (name or "output")[:120]


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="yt2midi",
        description="Convert a YouTube piano video (or a local audio/video file) to MIDI.",
    )
    p.add_argument("source", help="YouTube URL or path to a local audio/video file")
    p.add_argument("-o", "--output", help="output .mid path (default: <video title>.mid)")
    p.add_argument("--start", help="start time, e.g. 0:15 or 15")
    p.add_argument("--end", help="end time, e.g. 2:30")
    p.add_argument(
        "--engine",
        choices=("piano", "basic-pitch"),
        default="piano",
        help="piano: high accuracy solo-piano model with pedal (default); "
        "basic-pitch: lighter, works for any instrument",
    )
    p.add_argument(
        "--hands",
        default="auto",
        help="'auto' to guess left/right hand, 'none' for a single track, "
        "or a MIDI note number to split at (60 = middle C)",
    )
    p.add_argument(
        "--pedal",
        choices=("cc", "extend", "both", "none"),
        default="extend",
        help="how to handle the sustain pedal: extend note lengths to match (default, "
        "best for learning apps), write it as CC64, both, or drop it",
    )
    p.add_argument("--bpm", type=float, help="tempo written to the file (default: estimated)")
    p.add_argument("--min-velocity", type=int, default=0, help="drop notes quieter than this (1-127)")
    p.add_argument("--device", help="torch device for the piano engine, e.g. cpu or cuda")
    p.add_argument("--checkpoint", help="path to a local piano model checkpoint")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start = audio_mod.parse_time(args.start)
    end = audio_mod.parse_time(args.end)

    with tempfile.TemporaryDirectory() as tmp:
        if audio_mod.is_url(args.source):
            print("Downloading audio ...", file=sys.stderr)
            path, title = audio_mod.download_audio(args.source, tmp)
        else:
            if not os.path.exists(args.source):
                sys.exit(f"File not found: {args.source}")
            path, title = args.source, os.path.splitext(os.path.basename(args.source))[0]

        rate = engines.PIANO_SAMPLE_RATE if args.engine == "piano" else 22050
        samples = audio_mod.load_audio(path, rate, start, end)

    print(f"Transcribing {len(samples) / rate:.1f}s of audio with '{args.engine}' ...", file=sys.stderr)
    if args.engine == "piano":
        notes, pedals = engines.transcribe_piano(samples, args.device, args.checkpoint)
    else:
        notes, pedals = engines.transcribe_basic_pitch(samples, rate)

    notes = [n for n in notes if n.velocity >= args.min_velocity]
    notes = midi.clean_notes(notes)
    if args.pedal in ("extend", "both"):
        notes = midi.apply_pedal(notes, pedals)
    cc_pedals = pedals if args.pedal in ("cc", "both") else []

    if args.hands == "none":
        hands, two_tracks = [midi.RIGHT] * len(notes), False
    elif args.hands == "auto":
        hands, two_tracks = midi.split_hands(notes), True
    else:
        hands, two_tracks = midi.split_hands(notes, split=int(args.hands)), True

    bpm = args.bpm or midi.estimate_bpm(samples, rate)
    output = args.output or safe_filename(title) + ".mid"
    midi.write_midi(output, notes, hands, cc_pedals, bpm=bpm, two_tracks=two_tracks)

    right = sum(1 for h in hands if h == midi.RIGHT)
    print(
        f"Wrote {output}: {len(notes)} notes"
        + (f" ({right} right hand, {len(notes) - right} left hand)" if two_tracks else "")
        + f", {bpm:.0f} BPM",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
