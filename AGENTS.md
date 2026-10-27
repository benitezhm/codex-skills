# Personal Codex skills

This public repository is the source of truth for reusable personal skills.
The canonical installed checkout is `~/.agents/skills`, with remote
`https://github.com/benitezhm/codex-skills`.

- Create future reusable personal skills as top-level `<skill-name>/` folders here,
  unless the user explicitly requests a different scope or location. Keep
  project-specific/confidential workflows in their own projects.
- Use skill-creator when available. Keep SKILL.md concise and put executable
  helpers/references inside the owning skill. Avoid copies in unrelated projects.
- Keep secrets, private project/customer data, recordings, generated media, model
  weights, caches and virtual environments out of this public repository.
- Validate a changed skill's frontmatter and run its relevant helpers with a short
  synthetic sample. Keep generated validation output outside this checkout.
- Inspect the diff and staged file list before committing. Commit/push when the
  user requests it; creating a skill does not automatically authorize publishing
  private material. Do not auto-stage every untracked file in the installed folder.
- Preserve existing skills and unrelated global instructions. Missing filesystem
  access is a blocker, not permission to replace directories or bypass the sandbox.
