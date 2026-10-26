"""Fetch the Salamander Grand Piano samples the chat player uses and trim them into site/piano/.

    uv run --with soundfile python tools/piano_samples.py

Six loudness layers, one sample every three semitones from A0 to C8. Bass notes keep 16 seconds,
the middle 10 and the treble 6, each with a fade at the end.
"""

import io
import urllib.request
from pathlib import Path

import numpy as np
import soundfile as sf

LAYERS = (4, 7, 9, 11, 13, 14)
NAMES = {0: "C", 3: "Ds", 6: "Fs", 9: "A"}
SOURCE = "https://cdn.jsdelivr.net/npm/@audio-samples/piano-mp3-velocity{layer}@1.0.5/audio/{name}{octave}v{layer}.mp3"
TARGET = Path(__file__).parent.parent / "site/piano"


def seconds(pitch: int) -> float:
    return 16.0 if pitch < 48 else 10.0 if pitch < 72 else 6.0


def main() -> None:
    TARGET.mkdir(exist_ok=True)
    for layer in LAYERS:
        for pitch in range(21, 109, 3):
            name, octave = NAMES[pitch % 12], pitch // 12 - 1
            url = SOURCE.format(layer=layer, name=name.replace("s", "%23"), octave=octave)
            audio, rate = sf.read(io.BytesIO(urllib.request.urlopen(url).read()), always_2d=True)
            loudest = np.abs(audio).max(axis=1)
            start = int(np.argmax(loudest > 0.01 * loudest.max()))
            clip = audio[start : start + int(rate * seconds(pitch))].copy()
            fade = int(rate * 1.5)
            clip[-fade:] *= np.linspace(1, 0, fade)[:, None]
            sf.write(TARGET / f"{name}{octave}v{layer}.mp3", clip, rate, format="MP3", compression_level=0.3)


if __name__ == "__main__":
    main()
