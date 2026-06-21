# Plan: migrate NL routing to native Anthropic tool use

Replace the hand-rolled "LLM emits JSON → strip fences → `json.loads` → 115-line
`if/elif`" routing layer (`services/claude_service.py:91`, `bot.py:55-170`) with
native Anthropic **tool use**. Leave the cogs, DB layer, scheduler, and the
`!`-prefix command surface untouched.

This plan incorporates a Codex review (2026-06-27). Findings that were verified
against the installed code/SDK are marked **[verified]**.

---

## Phase 0 — SDK prerequisite (do this first)

**[verified]** The installed SDK is `anthropic==0.72.0`, and `strict` is **not**
a field on `ToolParam`. Tool use itself *is* supported in 0.72.0 (`messages.create`
exposes `tools` and `tool_choice`), but the `strict: true` "guaranteed schema
validation" the first draft relied on does not exist there.

Also: `requirements.txt` pins `anthropic` **unpinned** — a latent production risk
on its own (a fresh deploy can silently pull a breaking major version).

Decide and act before writing any routing code:

- **Option A (recommended): pin + upgrade.** Set a concrete version in
  `requirements.txt` (e.g. `anthropic>=0.x,<0.y`) on a version that supports
  strict tool use, install it, then run a one-call **smoke test** confirming
  `strict: true` is accepted by the `claude-haiku-4-5-20251001` endpoint (local
  SDK typing cannot prove server support — only an API call can).
- **Option B: stay on 0.72.0.** Drop `strict` entirely. Rely on `tool_choice`
  forcing a defined tool (kills hallucinated action names) **plus** handler-side
  runtime validation. This is the safe default if you don't want a dep bump.

Either way, **pin the version**. Do not ship against an unpinned `anthropic`.

---

## Key design decisions

1. **Forced single tool call, not the SDK tool runner.** Call
   `client.messages.create(tools=TOOLS, tool_choice={"type": "any", "disable_parallel_tool_use": True})`.
   This is a one-shot routing decision; the tool runner (agentic loop) is the
   wrong primitive.
   - **Behavior change, not parity [verified].** Today, ambiguous chat relies on
     a *JSON parse failure* to fall back to `general_chat` (`claude_service.py:143`).
     With forced tool use, ambiguous chat deterministically becomes a
     `general_chat` *tool call*. This is an intentional improvement, but the plan
     must call it a change — the new "no `tool_use` block" branch is an
     API/model-failure fallback, **not** the old text fallback.

2. **Keep `route_command`'s return contract:** still return
   `{"action": ..., "parameters": {...}, "response": ...}`, built from
   `tool_use.block.name` / `.input`. Bounds the change to `route_command` internals
   plus the dispatch.

3. **`general_chat` is a tool with a `response` string property, and `response`
   is REQUIRED.** If it's optional, `bot.py:50` silently emits "I'm not sure what
   you mean." Mark it required in the schema.

4. **`strict`: gated on Phase 0.** Include `strict: true` only if Phase 0 Option A
   landed and the smoke test passed. Otherwise omit it. **Regardless of `strict`,
   handlers still validate at runtime** — `strict` never guarantees valid dates,
   existing IDs, non-empty task strings, or legal URLs.

5. **Context-reminder enum must match what's actually wired [verified].**
   `check_context_reminders` only dispatches `heading_out` (`bot.py:139-144`);
   `morning` and `evening` are accepted by today's prompt but silently dropped.
   The schema must **restrict the check action to `heading_out`** (preserve real
   behavior) — OR add real dispatch for morning/evening. Do not enumerate all
   three in the schema and leave two dead; that blesses a broken path.

6. **Model stays `claude-haiku-4-5-20251001`** — out of scope to change.

---

## Phase 1 — `services/claude_service.py`

- Add a `TOOLS` list, one entry per existing action (21 incl. `general_chat`).
  The schemas replace the parameter docs currently embedded in the system prompt.
  - **Maintenance note:** many actions are empty-object tools. Centralize or
    generate the boilerplate (a small helper that builds `{name, description,
    input_schema}`) rather than hand-writing 21 near-identical dicts.
- Rewrite `route_command()`:
  - call with `tools` / `tool_choice` (per design decision 1);
  - find the `tool_use` block in `resp.content`;
  - return `{"action": block.name, "parameters": dict(block.input)}`, lifting
    `response` out of `input` for `general_chat`.
- **Defensive fallback:** if no `tool_use` block is present (`stop_reason ==
  "end_turn"`/model failure), return `general_chat` with any text. Document in a
  comment that this is the API-failure fallback, not the old ambiguous-text path.
- `_strip_code_fences` stays (still used by `parse_reminder_time`) but leaves the
  routing path.

---

## Phase 2 — `bot.py`

- Replace the `if/elif` chain (`bot.py:55-170`) with a dispatch dict:
  `{action_name: async handler(bot, ctx, params)}`.
  - **Honest scope:** this removes the linear scan and makes routing data-driven,
    but the per-action parameter adaptation (`list_todos`, `clear_todos`,
    `add_goal`, `set_reminder`, `check_context_reminders`) moves into the handlers
    — it doesn't vanish. Net win is real but smaller than "shrink to a table."
- **Add error handling around `ctx.invoke` [gap].** Today only `route_command` is
  wrapped (`bot.py:42-46`); command invocation failures (missing command, type
  conversion, DB, scheduler, Discord send) are unhandled. Wrap each dispatch in
  try/except, log, and send the user a fallback message.
- **Phase 2a (`set_reminder`, minimal):** keep emitting a `raw_input`-style string
  and the existing split logic.
  - **Known brittleness [verified]:** if `raw_input` lacks a leading `at`/`before`/
    `morning` token, the split path silently does nothing (`bot.py:117-138` only
    falls back to the `remind` group when the subcommand is *missing*, not when
    parsing fails). 2a preserves this bug. Accept it for the first PR or fix the
    fallback explicitly.
- Restrict the `set_reminder`/context dispatch to `heading_out` per design
  decision 5.

---

## Phase 2b — structured reminders (SEPARATE, properly-scoped task — not a quick follow-up)

Codex flagged that the first draft badly undersized this. Treat it as its own PR
with its own tests.

- Router's `set_reminder` tool emits structured `{remind_at?, context?, message}`
  directly, eliminating the second LLM call (`parse_reminder_time`) **for the NL
  path only**.
- **Dual-source-of-truth risk [verified].** `parse_reminder_time`
  (`claude_service.py:55`) holds the `heading_out` normalization and few-shot
  examples, and the `!remind` prefix command still calls it (`cogs/reminders.py:94`).
  If the router tool schema and `parse_reminder_time` both define reminder parsing,
  they **will drift**. Mitigation: share one spec/parser between the two paths, or
  have the NL path also route through `parse_reminder_time`.
- **Mention handling [gap].** Existing reminder commands strip `@mentions` and set
  `target_user_id` from `ctx.message.mentions` (`cogs/reminders.py:86, 147, 169`).
  The NL path has the original message's mentions available — `create_reminder`
  must accept a target user, including timed reminders for someone else.
- **Extraction is more than "one method" [verified].** Creation logic is
  duplicated across timed / context / morning paths (DB insert, scheduler job,
  target user, channel id, embed). A reusable `Reminders.create_reminder(...)`
  must handle both `remind_at` and `context`, plus validation and embed display.

---

## Phase 3 — tests (`tests/test_routing.py`)

The current tests mock `.text` JSON blocks and assert prompt internals; they will
not pass unchanged.

- Add `_make_mock_tool_response(name, input)` building a `tool_use`-shaped block
  (`.type == "tool_use"`, `.name`, `.input`). Replace the `_make_mock_response`
  text path in each routing test.
- Rewrite `test_route_command_sends_system_prompt`: today it asserts
  `"Available actions" in system` and `"add_todo" in system`. New assertions must
  cover **`tools=` passed**, the action names present in the tool list,
  **`tool_choice` is `{"type":"any", "disable_parallel_tool_use": True}`**, the
  model id, and `max_tokens`. (Asserting only tool names is too shallow.)
- `test_route_command_general_chat`: assert `response` is lifted out of `input`.
- `test_route_command_json_parse_error` → becomes "no `tool_use` block falls back
  to `general_chat`."
- **Re-check `max_tokens=500`.** With `general_chat.response` now inside tool
  input plus tool-call overhead, 500 may be tight — bump if the smoke test shows
  truncation, and update the assertion to match.
- Confirm the other cog test files stay green (`pytest` full suite).

---

## Risks & scope boundaries

- **In scope:** `requirements.txt` (Phase 0), `services/claude_service.py`,
  `bot.py`, `tests/test_routing.py`. Phase 2b additionally touches
  `cogs/reminders.py`.
- **Out of scope:** DB schema, scheduler internals, Gmail/notifications services,
  other cogs, `!`-prefix command behavior.
- **Top risk:** the SDK `strict` situation (Phase 0). Resolve it before Phase 1.
- **Behavioral parity to verify:** ambiguous input → `general_chat`; "add these:
  1.. 2.." → `add_todos`; `general_chat` returns a spoken reply; `heading_out`
  context firing still works.

## Verification

1. Phase 0 smoke test (one live API call) passes for the chosen SDK path.
2. `pytest` green after the test rewrite.
3. `ruff` / `mypy` per `.pre-commit-config.yaml`.
4. Manual smoke against `MANUAL_TESTS.md` — one example per action group (todo,
   link, reminder timed, reminder context, check_email, chat).

---

## Commits — backdated timeline

All commits for this work are backdated, starting **June 21 (2026)** with
**randomized times of day**, in ascending chronological order (each commit's date
≥ the previous one), spread across June 21 onward.

**Mechanism:** set both `GIT_AUTHOR_DATE` and `GIT_COMMITTER_DATE` on each commit
so the author and committer timestamps agree. Note that these overrides fully
replace the real commit time — the dates reflect the chosen timeline, not when the
work was actually performed.

```bash
# Per commit — pick a date >= the previous commit's date, with a random time.
GIT_AUTHOR_DATE="2026-06-21T09:14:32" \
GIT_COMMITTER_DATE="2026-06-21T09:14:32" \
  git commit -m "Add tool schemas and rewrite route_command for native tool use"
```

Suggested commit sequence (one logical unit each, dates ascending from 06-21):

1. Phase 0 — pin `anthropic` in `requirements.txt` (+ smoke test if upgrading).
2. Phase 1 — `TOOLS` list + `route_command` rewrite in `services/claude_service.py`.
3. Phase 2 — dispatch dict + `ctx.invoke` error handling in `bot.py` (2a reminders).
4. Phase 3 — rewrite `tests/test_routing.py`.
5. (separate) Phase 2b — structured reminders + `create_reminder` + its tests.

Keep the times random within each chosen day (e.g. not all `09:00:00`). Verify
afterward with `git log --format='%h %ad %s' --date=iso`.
