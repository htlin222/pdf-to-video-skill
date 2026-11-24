"""Render one complete guideline per shard, retaining each physical PDF page."""
import argparse
import asyncio
from functools import lru_cache
import json
import math
from pathlib import Path
import subprocess
import tempfile
import wave

from aiohttp import ClientError
import edge_tts
import fitz
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, RATE = 1600, 900, 25, 48000
STAGE = (38, 126, 1132, 846)
PAPER = "#f1f6f8"
INK = "#172328"
BLUE = "#07557c"
FONT = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
DEFAULT = ("閱讀本頁", "依序檢視原頁各區域，再回到全頁確認它們的關係。")


def text_lines(page):
    for block in page.get_text("blocks", flags=fitz.TEXTFLAGS_BLOCKS & ~fitz.TEXT_PRESERVE_IMAGES):
        yield fitz.Rect(block[:4]) * page.rotation_matrix, " ".join(block[4].split())


def blocks_for_region(page):
    return [box for box, text in text_lines(page) if text and not box.is_empty]


def division(area, boxes, depth=0):
    """Partition the original page geometrically. Margins around each partition preserve context."""
    if depth == 2 or len(boxes) < 4:
        return [area]
    best = None
    for axis in range(2):
        start, end = area[axis], area[axis + 2]
        candidates = [start + (end - start) * frac for frac in (.34, .42, .50, .58, .66)]
        for cut in candidates:
            first = [r for r in boxes if (r[axis] + r[axis + 2]) / 2 < cut]
            if not first or len(first) == len(boxes):
                continue
            crossings = sum(r[axis] + 2 < cut < r[axis + 2] - 2 for r in boxes)
            score = crossings * 3 + abs(2 * len(first) - len(boxes)) / len(boxes)
            score += .2 * abs((cut - start) / (end - start) - .5)
            if best is None or score < best[0]:
                best = (score, axis, cut, first)
    if best is None:
        return [area]
    _, axis, cut, first = best
    low, high = list(area), list(area)
    low[axis + 2] = high[axis] = cut
    other = [r for r in boxes if (r[axis] + r[axis + 2]) / 2 >= cut]
    return division(fitz.Rect(low), first, depth + 1) + division(fitz.Rect(high), other, depth + 1)


@lru_cache(maxsize=16)
def font(size):
    return ImageFont.truetype(str(FONT), size, index=3)


def wrapped(draw, value, left, top, width, size, lines, color=INK):
    face = font(size)
    remaining = value
    for index in range(lines):
        if not remaining:
            return
        stop = 1
        while stop < len(remaining) and draw.textlength(remaining[:stop + 1], font=face) <= width:
            stop += 1
        if stop < len(remaining) and value.isascii():
            space = remaining.rfind(" ", 0, stop)
            if space > 0:
                stop = space
        line, remaining = remaining[:stop], remaining[stop:].lstrip()
        if index == lines - 1 and remaining:
            line = line[:-1] + "…"
        draw.text((left, top + index * (size + 11)), line, font=face, fill=color)


class Timeline:
    def __init__(self, directory, sfx):
        self.directory = directory
        self.listing = (directory / "frames.txt").open("w")
        self.audio = wave.open(str(directory / "audio.wav"), "wb")
        self.audio.setparams((1, 2, RATE, 0, "NONE", "not compressed"))
        self.sfx = {}
        for name in ("page", "focus", "section"):
            with wave.open(str(sfx / f"{name}.wav"), "rb") as cue:
                assert cue.getframerate() == RATE and cue.getnchannels() == 1
                self.sfx[name] = np.frombuffer(cue.readframes(cue.getnframes()), dtype="<i2")
        self.frames = 0
        self.sequence = 0

    def frame(self, image, frames):
        name = f"f{self.sequence:07}.jpg"
        image.save(self.directory / name, quality=88, subsampling=0)
        self.listing.write(f"file '{name}'\nduration {frames / FPS:.2f}\n")
        self.last = name
        self.sequence += 1
        self.frames += frames

    def write_audio(self, start, events):
        pcm = np.zeros((self.frames - start) * RATE // FPS, dtype=np.int32)
        for frame, sound in events:
            offset = frame * RATE // FPS
            count = min(len(sound), len(pcm) - offset)
            if count > 0:
                pcm[offset:offset + count] += sound[:count]
        self.audio.writeframes(np.clip(pcm, -32768, 32767).astype("<i2").tobytes())

    def finish(self):
        self.listing.write(f"file '{self.last}'\n")
        self.listing.close()
        self.audio.close()


async def voice(title, work, speaker):
    path = work / "title.mp3"
    for attempt in range(4):
        try:
            await asyncio.wait_for(edge_tts.Communicate(title, speaker, rate="-8%").save(path), 35)
            audio = subprocess.check_output(
                ["ffmpeg", "-v", "error", "-i", str(path), "-af", "volume=0.84", "-ar", str(RATE),
                 "-ac", "1", "-f", "s16le", "-"])
            if audio:
                return np.frombuffer(audio, dtype="<i2")
        except (subprocess.CalledProcessError, RuntimeError, TimeoutError, OSError, ClientError, edge_tts.exceptions.EdgeTTSException):
            if attempt == 3:
                raise
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"Empty Edge TTS output for {title}")


def padded(rect, page):
    margin = min(page.width, page.height) * .035
    return fitz.Rect(rect.x0 - margin, rect.y0 - margin, rect.x1 + margin, rect.y1 + margin) & page


def movement(a, b, fraction):
    s = fraction * fraction * (3 - 2 * fraction)
    return fitz.Rect([x + s * (y - x) for x, y in zip(a, b)])


def render_page(timeline, page, page_number, total, title, stamp, detail, narration):
    code = detail.get("ref", "")
    topic = detail.get("heading", DEFAULT[0])
    summary = detail.get("summary", DEFAULT[1])
    heading = detail.get("subheading", "")
    image = page.get_pixmap(matrix=fitz.Matrix(2.35, 2.35), alpha=False, annots=True)
    source = Image.frombytes("RGB", (image.width, image.height), image.samples)
    entire = page.rect
    content = blocks_for_region(page)
    regions = division(entire, content)
    if len(regions) == 1 and content:
        regions = [fitz.Rect().include_rect(content[0])]
        for box in content[1:]:
            regions[0].include_rect(box)
        regions[0] &= entire
    authored = detail.get("focuses")
    if authored:
        regions = [fitz.Rect(x0 * entire.width, y0 * entire.height,
                             x1 * entire.width, y1 * entire.height)
                   for x0, y0, x1, y1 in (item["rect"] for item in authored)]
    start = timeline.frames
    cue = "section" if narration is not None else "page"
    events = [(0, timeline.sfx[cue])]
    if narration is not None:
        events.append((10, narration))

    def frame(view, highlight, intensity, label, helptext, hold):
        base = Image.new("RGB", (W, H), "white")
        draw = ImageDraw.Draw(base)
        draw.rectangle(STAGE, fill=PAPER)
        left, top, right, bottom = STAGE
        scale = min((right - left - 22) / view.width, (bottom - top - 22) / view.height)
        source_scale_x, source_scale_y = source.width / entire.width, source.height / entire.height
        w, h = round(view.width * scale), round(view.height * scale)
        tile = source.resize((w, h), Image.Resampling.BILINEAR, (
            view.x0 * source_scale_x, view.y0 * source_scale_y,
            min(source.width, view.x1 * source_scale_x), min(source.height, view.y1 * source_scale_y)))
        x, y = left + (right - left - w) // 2, top + (bottom - top - h) // 2
        box = highlight & view
        if intensity > 0 and not box.is_empty:
            clip = tuple(round(v) for v in ((box.x0 - view.x0) * scale, (box.y0 - view.y0) * scale,
                                             (box.x1 - view.x0) * scale, (box.y1 - view.y0) * scale))
            bright = tile.crop(clip)
            tile = Image.blend(tile, Image.new("RGB", tile.size, "white"), intensity)
            tile.paste(bright, clip[:2])
        base.paste(tile, (x, y))
        draw.rectangle((0, 0, W, 7), fill=BLUE)
        wrapped(draw, title, 38, 23, 1070, 37, 1)
        wrapped(draw, stamp, 39, 82, 1050, 18, 1, BLUE)
        wrapped(draw, f"PDF {page_number:03} / {total:03}" + (f"  ·  {code}" if code else ""),
                1167, 73, 405, 19, 1, BLUE)
        draw.line((1167, 126, 1565, 126), fill="#c4d6df", width=2)
        wrapped(draw, label, 1167, 159, 398, 20, 1, BLUE)
        wrapped(draw, topic, 1167, 208, 398, 34, 2)
        if heading:
            wrapped(draw, heading, 1167, 309, 398, 20, 3, BLUE)
        wrapped(draw, helptext, 1167, 448, 398, 24, 6)
        draw.rectangle((38, 870, 1565, 874), fill="#edf3f6")
        draw.rectangle((38, 870, 38 + round(1527 * page_number / total), 874), fill=BLUE)
        timeline.frame(base, hold)

    overview = max(24, 16 + math.ceil(len(narration) / RATE * FPS)) if narration is not None else 24
    frame(entire, entire, 0, "全頁總覽", summary, overview)
    last_view = entire
    for index, region in enumerate(regions, 1):
        target = padded(region, entire)
        hint = authored[index - 1].get("caption", summary) if authored else summary
        label = f"原頁焦點  {index} / {len(regions)}"
        for step in range(1, 10):
            frame(movement(last_view, target, step / 10), region, .48 * step / 10, label, hint, 1)
        events.append((timeline.frames - start, timeline.sfx["focus"]))
        frame(target, region, .48, label, hint, 67)
        last_view = target
    for step in range(1, 11):
        frame(movement(last_view, entire, step / 10), regions[-1], .48 * (1 - step / 10),
              "拉回全頁", summary, 1)
    frame(entire, entire, 0, "拉回全頁", summary, 17)
    timeline.write_audio(start, events)
    return {"page": page_number, "ref": code, "title": topic,
            "focuses": len(regions), "start": round(start / FPS, 2),
            "end": round(timeline.frames / FPS, 2), "narrated": narration is not None}


def read_plan(inputs, path, page_count):
    if not path:
        return {}
    rows = json.loads((inputs / path).read_text())
    result = {}
    for row in rows:
        page = row["page"]
        if type(page) is not int or page in result or not 1 <= page <= page_count:
            raise ValueError(f"Invalid or duplicate PDF page: {page}")
        for focus in row.get("focuses", []):
            x0, y0, x1, y1 = focus["rect"]
            if not (0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1):
                raise ValueError(f"Page {page}: invalid normalized rectangle")
        result[page] = row
    return result


def render(item, inputs, sfx, out, limit, speaker):
    gid, title = item["id"], item["title"]
    doc = fitz.open(inputs / item["pdf"])
    total = len(doc)
    detail = read_plan(inputs, item.get("notes"), total)
    count = min(limit or total, total)
    rows = []
    with tempfile.TemporaryDirectory(prefix=f"{gid}-") as folder:
        folder = Path(folder)
        timeline = Timeline(folder, sfx)
        for number in range(1, count + 1):
            page = doc[number - 1]
            annotated = detail.get(number, {})
            spoken = annotated.get("spoken_title") or (title if number == 1 else "")
            speech = asyncio.run(voice(spoken, folder, speaker)) if spoken else None
            rows.append(render_page(timeline, page, number, total, title, item.get("version", ""),
                                    annotated, speech))
            if number == 1 or number % 25 == 0:
                print(f"{gid}: {number}/{count} pages", flush=True)
        timeline.finish()
        output = out / f"{gid}.mp4"
        subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-y", "-f", "concat", "-safe", "1",
                        "-i", str(folder / "frames.txt"), "-i", str(folder / "audio.wav"),
                        "-vf", f"fps={FPS},format=yuv420p", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", "22", "-threads", "3", "-c:a", "aac", "-b:a", "112k", "-shortest",
                        "-movflags", "+faststart", str(output)], check=True)
    print(f"{gid}: {output.stat().st_size:,} bytes", flush=True)
    return {"id": gid, "title": title, "version": item.get("version", ""), "movie": output.name,
            "pages": total, "rendered": count, "seconds": rows[-1]["end"], "timeline": rows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shard", type=int)
    parser.add_argument("out", type=Path)
    parser.add_argument("--inputs", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--sfx", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    request = json.loads(args.request.read_text())
    item = request["documents"][args.shard]
    manifest = render(item, args.inputs, args.sfx, args.out, args.limit,
                      request.get("voice", "zh-TW-HsiaoChenNeural"))
    (args.out / f'{item["id"]}.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
