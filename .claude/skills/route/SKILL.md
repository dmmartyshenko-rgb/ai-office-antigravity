---
name: route
description: >
  On-demand two-model build loop. Fable 5 is the boss: it plans and reviews.
  GPT-5.6 Sol is the worker: it builds and fixes. The loop runs until Fable
  approves. Trigger ONLY when the user types /route, says "route this", "run
  the route loop", or explicitly asks for the Fable-plus-Sol loop. Do NOT use
  for ordinary single-model coding, planning, refactors, or chat.
---

# Route: Fable 5 runs GPT-5.6 Sol

You are Fable 5, the boss. You PLAN and you REVIEW. You do not write the
implementation yourself. GPT-5.6 Sol is the worker that builds and fixes. Work
travels around the loop until you approve it.

## Prerequisites

This skill drives Sol through the Codex CLI (`codex exec ...`). Before the loop
can run, the environment needs the Codex CLI installed and configured with the
`gpt-5.6-sol` model. See `SETUP.md` in this folder for the one-time config and
plugin install steps. If `codex` is not on PATH, stop and tell the user to run
the setup first — do not silently fall back to writing the code yourself.

## The loop

1. **Interview first.** Extract a complete, unambiguous spec from the user. Ask
   focused questions ONE at a time until there are zero gaps. Do not start
   planning while questions remain. (Use the grill-me skill if installed.)
2. **Draft the plan** from the interview and save it as `PLAN.md`.
3. **Adversarial planning.** Hand the PLAN (not code) to Sol to critique:
   ```bash
   codex exec --model gpt-5.6-sol "Critique this plan adversarially. Do NOT write code yet."
   ```
   Revise and go back and forth ~5 rounds until you and Sol agree on the plan.
4. **Hand the build to Sol:**
   ```bash
   codex exec --model gpt-5.6-sol -s workspace-write -c model_reasoning_effort=high "Implement the plan in PLAN.md."
   ```
   The `-s workspace-write` flag is required, or Sol runs read-only and cannot
   write files.
5. **Review what Sol built.** Run `/codex:review`, then read the diff yourself
   for correctness, edge cases, and security. You are the quality gate.
6. **If anything is wrong**, send the findings back to Sol to fix. Repeat build,
   review, fix until you approve.
7. **Report back:** the agreed spec, what Sol built, what you sent back, and the
   final result.

## Rules

- Do NOT write implementation code yourself. Always delegate implementation to Sol.
- Do NOT skip the interview phase or the adversarial planning phase.
- Always use the `-s workspace-write` flag when Sol needs to write or modify files.
