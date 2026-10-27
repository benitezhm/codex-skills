# Configuration and component workflow

## Scene format

Use UTF-8 JSON; paths are relative to the JSON file. The agent supplies factual,
audience-appropriate script text from the topic or structured brief. No LLM API is
called by these scripts. Example:

```json
{
  "title": "A team workflow",
  "brand": "Studio",
  "width": 1280,
  "height": 720,
  "fps": 24,
  "max_duration": 120,
  "motion": "zoom",
  "transition_seconds": 0.18,
  "caption_mode": "burn",
  "scenes": [{
    "kicker": "How we work",
    "title": "From a clear brief to a reviewed result",
    "cards": [
      {"title": "Prepare", "body": "Write a concise script"},
      {"title": "Create", "body": "Narrate and render locally"},
      {"title": "Review", "body": "Check the final video"}
    ],
    "narration": [
      "Start with a clear brief and a concise script.",
      {"text": "Then create and review the video.", "caption": "Create, then review the video."}
    ]
  }]
}
```

A narration string is both spoken and captioned. An object separates `text`
(spoken) from `caption` (displayed), useful for acronyms or concise subtitles.
Each cue has its own measurable audio file. Captions include a short trailing pause.
Use short cues; the renderer rejects text that overflows the layout or caption band.

- `target_duration` (optional): pad with silence to a longer exact target on the fps
  grid; too-short targets fail. `max_duration` is a cap, not a speech truncation tool.
- Dimensions: even pixels, at least 640×360. FPS: integer 1–60. Landscape layout is
  the default; author custom HTML/images for unusual aspect ratios.
- `pause`: per-cue silence, default 0.3 seconds. `motion`: `zoom` or `none`.
- `transition_seconds`: fade out/in within cues, through black. Zero gives cuts.
  This preserves caption timing without overlapping narration. It is not an xfade
  between simultaneous scenes.
- `caption_mode`: `burn` (default, works muted everywhere), `soft` (selectable MP4
  mov_text), or `none`. External `captions.srt` is still useful as an editable source.
- `voice`: optional object overriding `voice`, `speed`, `language`, `model_dir`,
  `python` or `threads`. Defaults: af_heart, 0.95, en-us, ~/tools/kokoro-tts, its
  .venv/bin/python, 4 CPU threads. The original `.95` speed is kept unless requested.
- `theme`: optional background/ink/accent/muted hex colors and font/heading_font
  fontconfig names or installed font paths. Defaults match the proven warm explainer
  layout but brand/title/content are project-independent.

## Custom visuals and Chromium

Default scenes use 1–3 cards and optional `footer`. For bespoke diagrams use a
same-size `image`, or a self-contained local `html` page instead of cards. HTML
must reserve the lower 19% for burned captions. `html_time_ms` (default 500) sets
Chromium's virtual-time screenshot budget; set a viewport-sized page with zero
body margin. The script opens only that local file in a fresh temporary Chrome
profile, without disabling the sandbox or touching the user's browser session.
Use local/embedded assets to avoid network dependencies and information leakage.

Chromium captures a **poster**, not a video of arbitrary JavaScript/CSS animation.
FFmpeg applies the supported zoom/pan and fade motion. For complex motion, author
appropriate frames/renderer explicitly; do not claim web animation was recorded.
The HTML cache hashes its document, not linked assets: embed assets or edit the
HTML/change its path when a referenced asset changes.

## Commands

Replace `<skill-dir>` with this skill's actual directory (no cwd assumption).
All stages take `--project brief.json --out output-directory` except `doctor`.

```sh
python3 <skill-dir>/scripts/video.py all --project brief.json --out output
python3 <skill-dir>/scripts/video.py narrate --project brief.json --out output
python3 <skill-dir>/scripts/video.py captions --project brief.json --out output
python3 <skill-dir>/scripts/video.py visuals --project brief.json --out output
python3 <skill-dir>/scripts/video.py mux --project brief.json --out output
python3 <skill-dir>/scripts/video.py validate --project brief.json --out output
```

- Caption-only edit: change `caption`, then `captions`, `mux`, `validate`. Speech
  and visual assets are reused. Burn mode needs final video re-encoding; soft mode
  stream-copies visuals. Neither rerenders source artwork.
- Voice/script change: `narrate`, `captions`, `visuals`, `mux`, `validate` (or `all`).
  The cache regenerates only missing speech/assets/clips. Changed cue lengths need
  retimed clips but the same posters. Requested duration limits remain enforced.
- Visual-only edit: `visuals`, `mux`, `validate`; existing narration is reused.
- Resolution/fps change: use `all`; geometry/timeline can change. Prefer a new output
  folder for variants. Repeated stages update generated output files intentionally;
  original project/input assets are never edited by the helper.

Audio cache keys include spoken text, voice settings, model file metadata and the
worker code. Visual keys include source artwork, geometry, motion and cue duration.
Do not manually edit cache files. Outputs include `audio/`, `posters/`, `clips/`,
`narration.wav`, `timeline.json`, `captions.srt`, `captions.ass`, `visuals.mp4`,
`video.mp4`, and `verification.json`. Keep these to enable inexpensive revisions.

## Existing MP4 voice-only replacement

This is the reusable version of the validated La Tienda replacement, preserving
captioned source visuals and the original file. It requires matching original SRT
with contiguous cues starting at zero, an H.264 source and constant integer fps.
The SRT text is spoken verbatim: use the original spoken script, not paraphrased
subtitles, when narration wording must be preserved. If needed, prepare a matching
SRT from the original script and cue boundaries before calling the helper.

```sh
python3 <skill-dir>/scripts/revoice.py \
  --source original.mp4 --srt original-captions.srt \
  --output original-kokoro.mp4
```

Defaults match the voice configuration above; `--voice`, `--speed`, `--language`
and `--model-dir` are available. Without `--keep-timing`, measured new speech
retimes source segments and embedded captions. It matches visible caption cuts
within 0.2 seconds of original SRT boundaries and stops if matching fails or
produces duplicate/out-of-order cuts. Inspect the encoded result after retiming. This narrow route fits the original captioned slide
videos; it is not a general editor for live footage or overlapping transitions.

`--keep-timing` stream-copies the original video and pads each cue with silence;
it fails if any new speech exceeds its old slot. Neither mode overwrites an existing
output. A sibling output SRT, work directory and verification record are retained.
Re-encoding during retiming can introduce small visual compression differences.
For the generated videos, use the caption-free visual master/component stages
when changing caption wording. Existing burned captions cannot simply be removed
or rewritten by an audio remux.

## Validation and costs

`validate` checks H.264/AAC/dimensions, narration/video duration agreement, subtitle
text/count/monotonic boundaries, coverage of measured speech, non-silent PCM audio,
and full FFmpeg decoding. It extracts encoded frames and a contact sheet. Inspect
the actual frames, not only source posters; optionally play/listen locally. It
cannot certify facts, pronunciation, human listening, or all players/devices.

This environment has Python/Pillow, fontconfig, Chrome, FFmpeg/libopenh264/AAC/libass,
and the existing Kokoro venv. No new dependencies were installed. Other machines
need those prerequisites. libx264 is preferred when present; libopenh264 is the
verified local fallback. Missing encoders/fonts/models should be reported, not
worked around by downloading paid services. Local rendering incurs CPU, storage
and electricity use; no media API charge is introduced by the helper.
