# Personal Codex skills

Reusable personal skills, versioned separately from project code.
Public repository: https://github.com/benitezhm/codex-skills.

## Included skills

- [video-generator](video-generator/SKILL.md): narrated MP4 explainers using local
  Kokoro ONNX, Python/Pillow, optional Chromium HTML visuals and FFmpeg. Includes
  synchronized captions, component reuse and existing-video voice replacement.

Model weights, generated videos, private project examples and credentials are
not included. Each skill documents its own prerequisites and validation.

## Connect your installed skills

Use `~/.agents/skills` as the repository checkout, so installed skills and their
versioned source are the same files. If this folder does not exist, a normal clone
works. If it already contains skills, use the preserving helper instead:

```sh
git clone https://github.com/benitezhm/codex-skills.git /tmp/codex-skills-setup
python3 /tmp/codex-skills-setup/scripts/connect_local.py --register-preference
```

The helper compares existing tracked files first. Identical installed skills are
left untouched; conflicting files cause it to stop before copying or attaching
Git metadata. Extra local skills are preserved as untracked directories. It never
resets or deletes installed skills. If already connected to this remote, it keeps
local changes and does not auto-pull.

`--register-preference` adds a small managed block to global Codex instructions
(`$CODEX_HOME/AGENTS.md`, normally `~/.codex/AGENTS.md`; an active non-empty
AGENTS.override.md takes precedence). It preserves unrelated text and backs up an
existing file before its first edit. This makes the personal repository preference
available across projects. Start a new Codex session to load updated instructions.
See [official global instruction discovery](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
and [personal skill location](https://learn.chatgpt.com/docs/customization/overview).

Check the connection:

```sh
git -C ~/.agents/skills remote -v
git -C ~/.agents/skills status --short
```

## Future skills and updates

Ask Codex to create reusable personal skills in this repository. It should read
[AGENTS.md](AGENTS.md), use skill-creator, and create a top-level skill-name folder.
Project-specific/private skills can stay in their own projects when requested.

Run the relevant validators and a short synthetic sample; save generated output
outside this checkout. Review the public diff, stage the intended skill files,
commit and push when authorized. No automatic publishing hook is installed.

For updates made elsewhere, use `git -C ~/.agents/skills pull --ff-only` after
checking for local changes. Existing third-party/system/plugin skills are not
moved into this repository automatically.

## Validation baseline

video-generator was tested with Python/Pillow, FFmpeg H.264/AAC/libass, Chrome and
local Kokoro af_heart at speed 0.95, en-us. Two short generic explainers, caption-only
reuse, voice replacement, retiming, duration limits and browser playback passed.
Human listening/pronunciation review was not claimed. See the skill's workflow
reference for supported formats and animation limits.

The repository connection helper has isolated standard-library tests:

```sh
python3 -m unittest discover -s tests
```

They use temporary Git repositories and fake instruction files, not your installed
skills or global configuration.
