# 🎮 Commentary / Brainrot Mode: Complete Architecture & Rollback Reference

This directory serves as a **complete operational reference and rollback blueprint** for the **Commentary / Brainrot Mode** of the Reddit-to-Shorts Automation pipeline.

If you are an **AI agent** (e.g. Antigravity, Claude, Cursor) or a **developer** tasked with restoring or modifying Commentary Mode, everything you need is documented here. You do **not** need the user to re-explain anything.

---

## 📌 What is Commentary / Brainrot Mode?

Unlike **Curator Mode** (which compiles original Reddit video clips with authentic audio and a Twitter/X creator card), **Commentary Mode** builds dynamic 12–60 second vertical Shorts from scratch:

```
┌───────────────────────────────────────────────┐
│              1080 x 1920 (9:16)               │
│                                               │
│   ┌───────────────────────────────────────┐   │
│   │ [r/subreddit] Posted by u/author      │   │  <-- Dark Mode Reddit Post Card
│   │ "Reddit post title text..."           │   │      (Rendered via Pillow)
│   └───────────────────────────────────────┘   │
│                                               │
│   ┌───────────────────────────────────────┐   │
│   │                                       │   │
│   │         GAMEPLAY BACKGROUND           │   │  <-- Minecraft Parkour /
│   │      (Subway Surfers / Satisfying)    │   │      Subway Surfers (1080x1920)
│   │                                       │   │
│   │        [ BOUNCING ASS SUBTITLES ]     │   │  <-- Kinetic word-highlighting
│   │                                       │   │      karaoke-style captions
│   │    ┌─────────────────────────────┐    │   │
│   │    │  CAT REACTION (Chromakey)   │    │   │  <-- Optional green-screen cat
│   │    └─────────────────────────────┘    │   │      overlay keyed via FFmpeg
│   └───────────────────────────────────────┘   │
│                                               │
│   🔊 AI Voiceover (Edge-TTS / ElevenLabs)     │
└───────────────────────────────────────────────┘
```

---

## 🏗️ Core Architectural Components

### 1. Reddit Post Ingestion
* **Module**: `src/reddit/client.py`
* **How it works**: Fetches top or hot text/image submissions from target subreddits (e.g., `memes`, `AskReddit`, `Showerthoughts`, `dankmemes`).
* **Settings**:
  * `ONLY_VIDEOS=False` (allows text and image submissions)
  * `REDDIT_MIN_SCORE=100`, `REDDIT_MIN_COMMENTS=10`
  * Deduplication via `data/database/processed_reddit_posts.json`.

---

### 2. AI Script Generation & Narration
* **Module**: `src/narration/`
  * `prompts.py`: System prompts for commentary generation.
  * `groq.py` / `gemini.py` / `openai_like.py`: LLM providers.
* **Output structure**:
  ```python
  {
      "title": "Punchy Short Title",
      "narration": "Full spoken voiceover script (30-60 words)...",
      "emphasis": ["KEYWORD1", "KEYWORD2"],  # Words to emphasize/highlight in subtitles
      "yt_title": "SEO Optimized YouTube Title #Shorts",
      "yt_hook": "First 3-second hook",
      "yt_summary": "Description summary",
      "yt_category": "Entertainment",
      "yt_content_tags": ["tag1", "tag2"]
  }
  ```

---

### 3. Voiceover & Character Timing Alignment
* **Module**: `src/voice/`
  * `edge.py`: Microsoft Edge TTS (100% free, no API key needed).
    * Supported voices: `en-US-AndrewNeural` (chaotic/meme), `en-US-BrianNeural` (story), `en-US-GuyNeural` (npc).
  * `elevenlabs.py`: Optional ultra-realistic ElevenLabs TTS (`ELEVENLABS_API_KEY`).
  * `helpers.py`: Maps words to exact audio start/end timestamps based on character duration ratios for word-level karaoke sync.

---

### 4. Background Gameplay Scraping & Slicing
* **Module**: `src/video/background.py`
* **How it works**:
  1. Searches YouTube via `yt-dlp` for gameplay queries configured in `BACKGROUND_PROVIDERS` (e.g. `minecraft parkour gameplay 1080p`, `subway surfers gameplay 1080p`, `satisfying videos 1080p`).
  2. Downloads full-length high-resolution source video into `data/raw/`.
  3. Uses FFmpeg to slice the video into 12–60 second vertical clips and stores them in `data/clips/`.
  4. Keeps track of used clips in `data/database/used_backgrounds.json` to prevent repetitive footage.
* **Cache Requirement**: In GitHub Actions, `data/clips/` is cached between runs using `actions/cache` so the runner doesn't have to re-download 500MB on every execution.

---

### 5. Cat Reactions & Greenscreen Keying
* **Modules**:
  * `src/video/cat_selector.py`: Selects random reaction clips from `data/assets/cat_reactions/`.
  * `src/video/greenscreen.py`: Slices a random 4.5-second reaction segment from `Long green screen video.mp4`.
* **FFmpeg Chromakey Filter**:
  ```text
  chromakey=color=0x00B140:similarity=0.12:blend=0.08
  ```
* **Layout Constraints**:
  * `CAT_LAYOUT_HEIGHT=0.25` (Bottom 25% of screen allocated to reaction)
  * `MEME_LAYOUT_HEIGHT=0.75` (Top 75% for gameplay & Reddit card)
  * `GREENSCREEN_MAX_WIDTH=800`, `GREENSCREEN_MAX_HEIGHT=800`

---

### 6. Dark-Mode Reddit Post Card Overlay
* **Module**: `src/video/overlay.py` (`generate_reddit_card`)
* **How it works**:
  * Renders a 900px wide rounded rectangle dark card (`#1A1A1B`, 94% opacity).
  * Subreddit name in Reddit Orange (`#FF4500`).
  * Upvote icon and score badge (`⬆ 14.2k`).
  * Author handle (`u/username`) and timestamp.
  * Word-wrapped title in bold Arial / Segoe UI / DejaVu Sans.
  * Saved as a transparent PNG (`data/output/reddit_card.png`).

---

### 7. Kinetic ASS Subtitle Generation
* **Module**: `src/video/renderer.py` (`_build_ass_subtitles`)
* **Styles**:
  * `chaotic`: Orange/Red palette with random Y-offset hopping.
  * `meme`: Neon green palette (`#00FF00`, `#32CD32`).
  * `story`: Crisp white/silver typography.
  * `npc`: Purple/pink synthwave palette.
* Subtitles are burned directly into the video stream using FFmpeg's `subtitles` filter with custom ASS formatting.

---

## 🔄 How to Restore Commentary Mode (Step-by-Step)

If the user asks to switch from Curator Mode back to Commentary / Brainrot Mode:

### Step 1: Update `.env` (or environment variables)
Set the following variables in `.env`:
```dotenv
# 1. Disable Curator Mode
CURATOR_MODE=False

# 2. Allow text and image Reddit posts
ONLY_VIDEOS=False
ONLY_REDDIT_HOSTED=False

# 3. Target subreddits suitable for commentary/stories
SUBREDDITS=memes, dankmemes, me_irl, AskReddit

# 4. Enable narration and voice synthesis
NARRATION_MODE=commentary
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
TTS_PROVIDER=edge
TTS_VOICE=en-US-AndrewNeural

# 5. Background gameplay settings
BACKGROUND_PROVIDERS=minecraft parkour gameplay 1080p, subway surfers gameplay 1080p
LOCAL_BACKGROUNDS_DIR=data/raw
YTDL_MAX_DOWNLOADS=2

# 6. Optional: Enable cat reaction overlays
ENABLE_CAT_REACTIONS=True
USE_GREENSCREEN=True
GREENSCREEN_PROBABILITY=0.40
```
*(A complete reference file is saved at `archive/commentary_mode_reference/.env.commentary.example`)*.

---

### Step 2: Restore GitHub Actions Workflow Cache
In `.github/workflows/daily_brainrot.yml`, replace the workflow with the copy saved at:
`archive/commentary_mode_reference/workflow_commentary_mode.yml`

This restores the `actions/cache/restore` and `actions/cache/save` steps so `data/clips/` are preserved across runs.

---

### Step 3: Test Locally
Run the commentary pipeline locally without uploading to verify:
```bash
python run_pipeline.py --force --no-upload --style chaotic
```
Check `data/output/final_short.mp4` to inspect the generated gameplay short with voiceover and subtitles.

