"""Synthesize short, soft motion cues without sample libraries."""
import math
from pathlib import Path
import random
import struct
import sys
import wave

RATE = 48000
CUES = [
    ("page", 0.42, (440, 659), 0.12),
    ("focus", 0.20, (587, 880), 0.07),
    ("section", 0.72, (392, 523, 784), 0.15),
]


def render(out, name, duration, pitches, amplitude):
    randomizer = random.Random(name)
    previous = 0
    samples = bytearray()
    for i in range(round(RATE * duration)):
        t = i / RATE
        envelope = math.sin(math.pi * t / duration) ** 2
        previous = 0.94 * previous + 0.06 * randomizer.uniform(-1, 1)
        tone = sum(math.sin(math.tau * f * t * (1 - 0.06 * t)) for f in pitches)
        value = amplitude * envelope * (tone / len(pitches) + 0.22 * previous)
        samples.extend(struct.pack("<h", round(value * 32767)))
    with wave.open(str(out / f"{name}.wav"), "wb") as file:
        file.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        file.writeframes(samples)


shard, shards = map(int, sys.argv[1:3])
out = Path(sys.argv[3])
out.mkdir(parents=True, exist_ok=True)
for i, cue in enumerate(CUES):
    if i % shards == shard:
        render(out, *cue)
