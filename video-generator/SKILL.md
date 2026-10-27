---
name: video-generator
description: Create short narrated MP4 explainers from a topic, script, or brief using local Kokoro, Python visuals, optional Chromium HTML rendering, and FFmpeg; also update voiceovers or captions while preserving existing work.
---

# Video Generator

Produce readable, synchronized narrated videos using the working Python/Pillow →
local Kokoro ONNX → FFmpeg approach. Use Chromium only for self-contained local
HTML visuals when helpful. No cloud media API or model download is needed.

## Choose the operation

- **New video:** turn the topic/brief into a concise script and scene JSON. Preserve
  the user's audience, facts, tone, duration and resolution; do not invent completed
  work. Keep spoken claims consistent with verified evidence.
- **Existing video:** locate its script, SRT/timeline and visual masters before
  editing. Preserve originals and produce a new output. For a voice-only change,
  use `scripts/revoice.py`, not the original video builder.
- **Component edit:** reuse cached audio, posters and visual clips. Read the
  stage commands in [references/workflow.md](references/workflow.md); do not
  regenerate speech for caption-only changes or redraw artwork for voice changes.

## Local defaults and prerequisites

Python 3.10+ with Pillow; FFmpeg/ffprobe with H.264, AAC and libass; fontconfig.
Use available Open Sans/Montserrat or configure installed fonts. Chromium/Chrome
is optional for HTML scenes. Inspect with:

```sh
python3 <skill-dir>/scripts/video.py doctor
```

Kokoro is already installed at `~/tools/kokoro-tts`: use its `.venv/bin/python`,
`kokoro-v1.0.onnx` and `voices-v1.0.bin`. Defaults: **af_heart**, **0.95**, **en-us**.
The worker uses that environment's kokoro_onnx, numpy, soundfile and onnxruntime;
do not duplicate those packages into the rendering environment. Report missing
prerequisites instead of silently downloading models or changing environments.

## Generate and review

Read [references/workflow.md](references/workflow.md) for the JSON format, controls,
component commands and replacement limits. Work in the user's output directory,
separate from source projects and skill files.

```sh
python3 <skill-dir>/scripts/video.py all --project brief.json --out video-output
```

This creates narration, measured cue timing, SRT/ASS, independently cached visual
clips, a caption-free visual master, and `video.mp4`. Defaults are 1280×720, 24 fps,
burned captions, gentle zoom, fade-through-black transitions, and a 120-second cap.
Change them to fit the brief. Timing follows actual speech; a requested shorter
limit fails visibly rather than truncating narration or silently accelerating it.

Run `validate` after the last mux. Inspect the **encoded** contact sheet/frames for
clipping, glyphs, contrast, caption placement and intended visuals. Check duration,
codec, non-silent audio, subtitle boundaries and full-file decoding. Listen to a
sample if audio playback is available; automated waveform/decode checks are not
proof of pronunciation or a human listening review. Do not claim playback was
watched/listened to when only decoding was checked.

Return the MP4 link, duration, editable transcript/captions and any material limits.
Keep originals and script wording intact for voice-only requests. Rendering a
video does not authorize publishing, uploading or sending it to anyone.

## Provenance and scope

The core helpers extract the verified La Tienda slide layout, sentence-level
narration, caption timeline, H.264/AAC encoding and existing-video retiming. They
contain no project credentials or private project content. Chromium posters and
zoom/fade controls extend that core; they do not record a running remote website
or simulate proof of a live integration. Read the reference's limits for existing
burned captions or complex animation requirements.
