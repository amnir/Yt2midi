import mido

from yt2midi import audio, midi
from yt2midi.engines import Note


def test_parse_time():
    assert audio.parse_time("90") == 90
    assert audio.parse_time("1:30") == 90
    assert audio.parse_time("0:01:30.5") == 90.5
    assert audio.parse_time(None) is None


def test_clean_notes_trims_same_pitch_overlap_and_drops_blips():
    notes = [Note(0.0, 1.0, 60, 80), Note(0.5, 1.5, 60, 80), Note(2.0, 2.01, 62, 80)]
    out = midi.clean_notes(notes)
    assert [(n.start, n.end) for n in out] == [(0.0, 0.5), (0.5, 1.5)]


def test_apply_pedal_extends_to_release_but_not_past_next_strike():
    notes = [Note(0.0, 0.2, 60, 80), Note(0.1, 0.3, 64, 80), Note(0.8, 1.0, 60, 80)]
    out = midi.apply_pedal(notes, [(0.1, 1.5)])
    ends = {(n.pitch, n.start): n.end for n in out}
    assert ends[(60, 0.0)] == 0.8  # cut at re-strike
    assert ends[(64, 0.1)] == 1.5
    assert ends[(60, 0.8)] == 1.5


def test_split_hands_fixed_point():
    notes = [Note(0, 1, 59, 80), Note(0, 1, 60, 80)]
    assert midi.split_hands(notes, split=60) == [midi.LEFT, midi.RIGHT]


def test_split_hands_auto_melody_over_bass():
    notes = []
    for i, (rh, lh) in enumerate(zip([72, 74, 76, 77, 79], [48, 55, 48, 55, 48])):
        notes += [Note(i * 0.5, i * 0.5 + 0.5, rh, 80), Note(i * 0.5, i * 0.5 + 0.5, lh, 80)]
    hands = midi.split_hands(notes)
    for n, h in zip(notes, hands):
        assert h == (midi.RIGHT if n.pitch >= 60 else midi.LEFT)


def test_split_hands_auto_follows_hand_across_middle_c():
    # A right-hand scale descending below middle C while the left hand stays low.
    notes = [Note(i * 0.25, i * 0.25 + 0.2, p, 80) for i, p in enumerate([64, 62, 60, 59, 57])]
    notes += [Note(0, 1.5, 36, 80)]
    hands = midi.split_hands(notes)
    assert hands[:5] == [midi.RIGHT] * 5
    assert hands[5] == midi.LEFT


def test_write_midi_round_trip(tmp_path):
    notes = [Note(0.0, 0.5, 72, 90), Note(0.0, 1.0, 48, 70)]
    path = tmp_path / "x.mid"
    midi.write_midi(str(path), notes, [midi.RIGHT, midi.LEFT], pedals=[(0.0, 1.0)], bpm=100)
    m = mido.MidiFile(str(path))
    assert [t.name for t in m.tracks[1:]] == ["Right Hand", "Left Hand"]
    rh = [x for x in m.tracks[1] if x.type == "note_on"]
    lh = [x for x in m.tracks[2] if x.type == "note_on"]
    assert [x.note for x in rh] == [72] and [x.note for x in lh] == [48]
    assert any(x.type == "control_change" and x.control == 64 for x in m.tracks[2])
    assert abs(m.length - 1.0) < 0.01
