import asyncio
import json
import subprocess
import sys
from pathlib import Path

import edge_tts

WORK = Path("work")
AUDIO = WORK / "audio"
VOICE = "en-US-AriaNeural"
RATE = "+5%"   # slightly faster than default, feels natural on short-form video


# ── helpers ────────────────────────────────────────────────────────────────────

def load_script():
    p = WORK / "script.json"
    if not p.exists():
        sys.exit("work/script.json not found. Run Phase 1 first.")
    return json.loads(p.read_text(encoding="utf-8"))


def get_duration(path):
    """Return audio duration in seconds using ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
        return float(out)
    except Exception as e:
        sys.exit(f"ffprobe failed on {path}: {e}")


def seconds_to_srt(s):
    """Convert float seconds to SRT timestamp string."""
    ms = int((s % 1) * 1000)
    s  = int(s)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02}:{m:02}:{sec:02},{ms:03}"


# ── TTS per scene ───────────────────────────────────────────────────────────────

async def synthesise_scene(scene_id, narration, out_path):
    communicate = edge_tts.Communicate(narration, VOICE, rate=RATE)
    await communicate.save(str(out_path))


async def make_scene_audio(scenes):
    AUDIO.mkdir(parents=True, exist_ok=True)
    paths = []
    for s in scenes:
        out = AUDIO / f"scene_{s['id']:02d}.mp3"
        print(f"  Generating voice for scene {s['id']}...")
        await synthesise_scene(s["id"], s["narration"], out)
        real_dur = get_duration(out)
        s["duration_sec"] = round(real_dur, 3)   # overwrite estimate with real value
        paths.append(out)
        print(f"    Done. Real duration: {real_dur:.2f}s")
    return paths


# ── concatenate all scenes into one MP3 ────────────────────────────────────────

def concatenate_audio(scene_paths):
    """Write a concat list and join with ffmpeg."""
    list_file = WORK / "audio_list.txt"
    lines = [f"file '{p.resolve()}'\n" for p in scene_paths]
    list_file.write_text("".join(lines), encoding="utf-8")

    out = WORK / "voice.mp3"
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"ffmpeg concat failed:\n{result.stderr}")
    total = get_duration(out)
    print(f"\nVoice file: {out}  ({total:.2f}s total)")
    return out, total


# ── build SRT subtitle file ─────────────────────────────────────────────────────

def build_srt(scenes):
    out = WORK / "subs.srt"
    lines = []
    cursor = 0.0
    for i, s in enumerate(scenes, 1):
        dur = s["duration_sec"]
        start = seconds_to_srt(cursor)
        end   = seconds_to_srt(cursor + dur)
        lines.append(f"{i}\n{start} --> {end}\n{s['narration']}\n")
        cursor += dur
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Subtitles: {out}  ({len(scenes)} entries)")
    return out


# ── save updated script with real durations ─────────────────────────────────────

def save_script(data):
    (WORK / "script.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ── main ────────────────────────────────────────────────────────────────────────

async def run():
    print("Loading script...")
    data = load_script()
    scenes = data["scenes"]

    print(f"\nGenerating voice for {len(scenes)} scenes...")
    scene_paths = await make_scene_audio(scenes)

    print("\nConcatenating audio...")
    voice_path, total = concatenate_audio(scene_paths)

    print("\nBuilding subtitles...")
    build_srt(scenes)

    print("\nSaving updated durations back to script.json...")
    save_script(data)

    print("\n✓ Phase 2 complete.")
    print(f"  work/audio/scene_XX.mp3  — one file per scene")
    print(f"  work/voice.mp3           — full voiceover ({total:.1f}s)")
    print(f"  work/subs.srt            — subtitles with real timings")
    print(f"  work/script.json         — updated with real durations")


if __name__ == "__main__":
    asyncio.run(run())