# Route loop — one-time setup

The `/route` skill orchestrates a two-model build loop: **Fable 5** (Claude)
plans and reviews; **GPT-5.6 Sol** builds and fixes via the Codex CLI. Do these
steps once per machine before running `/route`.

## 1. Install the Codex plugin in Claude Code

Run these in the Claude Code prompt (they are `/plugin` slash commands, not
shell commands):

```
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
```

## 2. Point Codex at the `gpt-5.6-sol` model

Edit `~/.codex/config.toml` so the default model is `gpt-5.6-sol` and add a
`reviewer` profile that runs at maximum reasoning effort. A ready-to-copy
snippet is in [`config.sample.toml`](./config.sample.toml).

Add (or merge) the following, **without** removing or changing any existing
`marketplaces`, `plugins`, or project entries:

```toml
model = "gpt-5.6-sol"

[profiles.reviewer]
model = "gpt-5.6-sol"
model_reasoning_effort = "xhigh"
```

## 3. Verify

```bash
codex --version                       # Codex CLI is on PATH
codex exec --model gpt-5.6-sol "ping" # model resolves
```

If `codex` is not found, the CLI is not installed in this environment — install
it first; the `/route` skill depends on it and will otherwise refuse to run.

## 4. Run the loop

In Claude Code, type `/route` (or "run the route loop"). Fable 5 will interview
you for the spec, draft `PLAN.md`, stress-test the plan against Sol, hand the
build to Sol with `-s workspace-write`, review the diff, and cycle until it
approves.

## Notes

- `~/.codex/config.toml` and any `~/.claude/skills/` install are per-machine and
  live outside git. This repo ships the skill under `.claude/skills/route/` so it
  is version-controlled and loads automatically when you work in this repo; the
  Codex CLI config still has to be applied locally per the steps above.
- Model/plugin availability (`gpt-5.6-sol`, `codex@openai-codex`) depends on your
  Codex/OpenAI access; confirm with step 3 before relying on the loop.
