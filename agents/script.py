import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai

load_dotenv()

MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
WORK = Path("work")

PROMPT = """You are a short-form video scriptwriter.
Write a script for a vertical video (under 75 seconds total) about: __TOPIC__

Return ONLY JSON in exactly this shape:
{
  "title": "short catchy title",
  "scenes": [
    {
      "id": 1,
      "narration": "1-2 spoken sentences, plain English, no emojis",
      "search_keywords": "2-4 words describing the visual for stock footage",
      "duration_sec": 8
    }
  ]
}

Rules:
- 5 to 8 scenes.
- Scene 1 must be a strong hook.
- The last scene ends with a short call to action.
- duration_sec is an estimate: about 2.5 spoken words per second.
- The total of all duration_sec must be between 30 and 75.
- search_keywords must be concrete, filmable things (for example "full moon night sky"), never abstract ideas.
"""


def clean_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return text.strip()


def validate(data):
    if not isinstance(data, dict):
        raise ValueError("Response is not a JSON object")
    if not isinstance(data.get("title"), str) or not data["title"].strip():
        raise ValueError("Missing title")
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or not (5 <= len(scenes) <= 8):
        raise ValueError("Need 5 to 8 scenes")
    total = 0
    for i, s in enumerate(scenes, 1):
        if not str(s.get("narration", "")).strip():
            raise ValueError(f"Scene {i}: empty narration")
        if not str(s.get("search_keywords", "")).strip():
            raise ValueError(f"Scene {i}: empty search_keywords")
        if not isinstance(s.get("duration_sec"), (int, float)):
            raise ValueError(f"Scene {i}: duration_sec must be a number")
        s["id"] = i
        total += s["duration_sec"]
    if not (30 <= total <= 80):
        raise ValueError(f"Total duration {total}s is outside 30-80s")
    return data


def generate_script(topic):
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        sys.exit("GEMINI_API_KEY not found. Check your .env file.")
    client = genai.Client(api_key=key)
    prompt = PROMPT.replace("__TOPIC__", topic)

    last_error = None
    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json"},
            )
            data = validate(json.loads(clean_json(response.text)))
            WORK.mkdir(exist_ok=True)
            (WORK / "script.json").write_text(
                json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return data
        except Exception as e:
            last_error = e
            print(f"Attempt {attempt} failed: {e}")
            time.sleep(5)
    sys.exit(f"Script generation failed after 2 attempts: {last_error}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit('Usage: python -m agents.script "your topic"')
    result = generate_script(" ".join(sys.argv[1:]))
    print(f"\nTitle: {result['title']}\n")
    for s in result["scenes"]:
        print(f"Scene {s['id']} ({s['duration_sec']}s): {s['narration']}")
        print(f"   visuals: {s['search_keywords']}")
    total = sum(s["duration_sec"] for s in result["scenes"])
    print(f"\nTotal: {total}s. Saved to work/script.json")