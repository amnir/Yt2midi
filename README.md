# yt2midi

Turn a YouTube video of someone playing piano into a MIDI file you can load into a piano teaching app (Synthesia, or anything else that imports `.mid`).

It downloads the audio with [yt-dlp](https://github.com/yt-dlp/yt-dlp), transcribes it with the [ByteDance high-resolution piano transcription model](https://github.com/bytedance/piano_transcription) (notes, velocities and sustain pedal), then writes a MIDI file tidied up for learning:

- **Two tracks, Right Hand and Left Hand**, so the app can let you practise each hand separately. The split follows where each hand is playing instead of cutting at a fixed note.
- **Pedal baked into note lengths**, so the falling-note or sheet view shows notes as long as they sound.
- **Estimated tempo**, so bars in notation view roughly line up with the music.

## Install

Needs Python 3.9+.

```bash
git clone https://github.com/amnir/Yt2midi.git
cd Yt2midi
python -m venv .venv && source .venv/bin/activate
pip install .
```

The first run downloads the piano model (~165 MB) to `~/piano_transcription_inference_data/`. ffmpeg is bundled through `imageio-ffmpeg`, so you don't need to install it separately.

## Use

```bash
yt2midi "https://www.youtube.com/watch?v=VIDEO_ID"
```

That writes `<video title>.mid` in the current folder. More examples:

```bash
# Only the part from 0:30 to 2:15, custom filename
yt2midi "https://youtu.be/VIDEO_ID" --start 0:30 --end 2:15 -o song.mid

# A local recording or video file works too
yt2midi my_recording.mp3

# Split hands at middle C instead of guessing
yt2midi URL --hands 60

# Single track, keep pedal as CC64 messages instead of lengthening notes
yt2midi URL --hands none --pedal cc

# Known tempo (makes notation views much cleaner)
yt2midi URL --bpm 72
```

| Option | Default | What it does |
| --- | --- | --- |
| `-o, --output` | video title | Output `.mid` path |
| `--start`, `--end` | whole video | Trim, as `90`, `1:30` or `0:01:30` |
| `--hands` | `auto` | `auto`, `none` (one track) or a MIDI note to split at (60 = middle C) |
| `--pedal` | `extend` | `extend` note lengths, write as `cc`, `both`, or `none` |
| `--bpm` | estimated | Tempo written to the file. Playback timing is identical either way; it only affects how bars are drawn |
| `--min-velocity` | `0` | Drop notes quieter than this, handy for removing ghost notes |
| `--engine` | `piano` | `piano` (best for solo piano) or `basic-pitch` (Spotify's lighter general model, install with `pip install ".[basic-pitch]"`) |
| `--device` | auto | `cuda` or `cpu` for the piano model |
| `--checkpoint` | auto download | Use a model file you already have |

## Getting good results

- Solo piano works best. Singing, drums or backing tracks will add wrong notes.
- Synthesia-style "falling notes" videos are usually ideal since they're clean digital piano audio.
- A 4 minute piece takes roughly 1–3 minutes on a laptop CPU, much less on a GPU.
- The hand split is a guess. Crossed hands or both hands in the same register can get mixed up; most apps let you reassign a track if needed.
- Only convert videos you have the rights to use.

## Development

```bash
pip install -e ".[dev]"
pytest
```
