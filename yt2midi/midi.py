"""Note post-processing and MIDI writing tuned for piano teaching apps."""

import math
from dataclasses import replace

import mido

TICKS_PER_BEAT = 480
RIGHT, LEFT = 0, 1
MAX_HAND_SPAN = 14  # semitones, about a ninth


def clean_notes(notes, min_duration=0.03):
    """Drop tiny or malformed notes and fix overlapping notes of the same pitch."""
    notes = [n for n in notes if math.isfinite(n.start) and math.isfinite(n.end) and 21 <= n.pitch <= 108]
    notes = sorted((n for n in notes if n.end - n.start >= min_duration), key=lambda n: (n.start, n.pitch))
    last_by_pitch = {}
    for n in notes:
        prev = last_by_pitch.get(n.pitch)
        if prev is not None and prev.end > n.start:
            prev.end = n.start
        last_by_pitch[n.pitch] = n
    return [n for n in notes if n.end > n.start]


def apply_pedal(notes, pedals):
    """Lengthen notes to the pedal release, like a sustain pedal would.

    Makes the note lengths shown in falling-notes / sheet views match what is heard.
    Each note is cut off at the next onset of the same pitch.
    """
    if not pedals:
        return notes
    pedals = sorted(pedals)
    out = []
    for n in notes:
        end = n.end
        for p_start, p_end in pedals:
            if p_start > end:
                break
            if p_start <= end <= p_end:
                end = max(end, p_end)
        out.append(replace(n, end=end))
    return clean_notes(out, min_duration=0)


def split_hands(notes, split=None, chord_window=0.05):
    """Assign each note to RIGHT or LEFT hand.

    With `split` set (a MIDI pitch) notes at or above it go to the right hand.
    Otherwise a heuristic is used: notes starting together form a chord, which
    is divided between the hands based on where each hand has recently been
    playing and how far a hand can stretch.
    """
    if split is not None:
        return [RIGHT if n.pitch >= split else LEFT for n in notes]

    order = sorted(range(len(notes)), key=lambda i: (notes[i].start, notes[i].pitch))
    hands = [RIGHT] * len(notes)
    centers = {RIGHT: 67.0, LEFT: 50.0}
    alpha = 0.3

    i = 0
    while i < len(order):
        group = [order[i]]
        t0 = notes[order[i]].start
        i += 1
        while i < len(order) and notes[order[i]].start - t0 <= chord_window:
            group.append(order[i])
            i += 1
        group.sort(key=lambda k: notes[k].pitch)
        pitches = [notes[k].pitch for k in group]

        # Try every split of the (sorted) chord into a lower left-hand part and an
        # upper right-hand part; prefer notes near each hand's recent position and
        # penalise parts wider than a hand can reach.
        def cost(cut):
            total = 0.0
            for hand, part in ((LEFT, pitches[:cut]), (RIGHT, pitches[cut:])):
                if part:
                    total += sum(abs(p - centers[hand]) for p in part)
                    total += 3 * max(0, part[-1] - part[0] - MAX_HAND_SPAN)
            return total

        cut = min(range(len(pitches) + 1), key=cost)
        parts = ((LEFT, group[:cut]), (RIGHT, group[cut:]))

        for hand, members in parts:
            if not members:
                continue
            for k in members:
                hands[k] = hand
            mean = sum(notes[k].pitch for k in members) / len(members)
            centers[hand] = (1 - alpha) * centers[hand] + alpha * mean
        # Keep the hands from drifting past each other.
        if centers[RIGHT] - centers[LEFT] < 5:
            mid = (centers[RIGHT] + centers[LEFT]) / 2
            centers[RIGHT], centers[LEFT] = mid + 2.5, mid - 2.5
    return hands


def estimate_bpm(audio, sample_rate):
    """Rough tempo estimate so bars in notation views line up with the music."""
    import librosa
    import numpy as np

    tempo, _ = librosa.beat.beat_track(y=audio, sr=sample_rate)
    bpm = float(np.atleast_1d(tempo)[0])
    return bpm if 30 <= bpm <= 240 else 120.0


def write_midi(path, notes, hands, pedals=(), bpm=120.0, two_tracks=True):
    """Write a type-1 MIDI file: a tempo track plus one track per hand."""
    tempo = mido.bpm2tempo(bpm)
    ticks_per_second = TICKS_PER_BEAT * 1e6 / tempo

    def tick(seconds):
        return int(round(seconds * ticks_per_second))

    mid = mido.MidiFile(type=1, ticks_per_beat=TICKS_PER_BEAT)
    meta = mido.MidiTrack()
    meta.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))
    meta.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
    mid.tracks.append(meta)

    if two_tracks:
        layout = ((RIGHT, "Right Hand", 0), (LEFT, "Left Hand", 1))
    else:
        layout = ((None, "Piano", 0),)

    for hand, name, channel in layout:
        events = []  # (tick, order, message); note-offs sort before note-ons at the same tick
        for n, h in zip(notes, hands):
            if hand is not None and h != hand:
                continue
            events.append((tick(n.start), 1, mido.Message("note_on", channel=channel, note=n.pitch, velocity=n.velocity)))
            events.append((tick(n.end), 0, mido.Message("note_off", channel=channel, note=n.pitch, velocity=0)))
        for start, end in pedals:
            events.append((tick(start), 1, mido.Message("control_change", channel=channel, control=64, value=127)))
            events.append((tick(end), 0, mido.Message("control_change", channel=channel, control=64, value=0)))
        events.sort(key=lambda e: (e[0], e[1]))

        track = mido.MidiTrack()
        track.append(mido.MetaMessage("track_name", name=name, time=0))
        track.append(mido.Message("program_change", channel=channel, program=0, time=0))
        now = 0
        for t, _, msg in events:
            track.append(msg.copy(time=t - now))
            now = t
        mid.tracks.append(track)

    mid.save(path)
    return mid
