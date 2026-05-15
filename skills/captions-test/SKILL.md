---
name: captions-test
description: >
  Run the blender-captions test suite (lint, unit, integration) and report
  pass/fail. Use when the user asks to verify the addon still works, run
  tests, check the repo before shipping, validate a refactor, or audit
  hygiene after edits. Trigger when the user says "run the tests,"
  "check the addon," "verify everything works," "is the repo healthy,"
  "before I ship," or any combination involving the captions addon and
  testing.
---

# Captions test suite runner

Three tiers, build up from cheap to expensive.

## Tier 1 — lint (no Blender, runs in under a second)

```powershell
cd <REPO_ROOT>
python tests\lint\check.py
```

Exit code 0 on pass, 1 on fail. Each check prints PASS / FAIL with a one-line
reason. Coverage:

- bl_info version matches README install link, SKILL.md install reference,
  dist zip filename
- dist zip contents byte-match the on-disk `captions_tool/` source
- every operator class appears in README operator table, api_docs.py
  CAPTIONS_README, and skills/headless-captions/SKILL.md
- cleanup.py CAPTION_CLASSES matches every `_CLASSES` tuple in props/operators/ui
- bl_idname strings are unique and prefixed `captions.`
- handlers have `@persistent`
- every operator has a docstring
- no hard-coded `"Captions"` in bpy.data lookups (use MASTER_NAME)

If anything fails, fix the actual issue. Don't soften the check unless the
check itself is wrong.

## Tier 2 — unit (pytest, no Blender)

```powershell
cd <REPO_ROOT>
pytest tests\unit
```

Covers `captions_tool/events.py` (the bpy-free encoding logic extracted from
`timeline.py`). Tests pin the keyframe-event generation rules: leading
sentinel position, overlap handling, gap_frames behavior, multi-line
covering edge cases.

## Tier 3 — Blender integration (requires Blender, ~30s startup)

**This tier is destructive.** It clears caption lines, removes the master
object, and mutates F-curves between tests. ALWAYS run in an isolated
`--background --factory-startup` Blender process. Never against the user's
working file, never via an MCP-connected live session.

```powershell
$blender = "<BLENDER_EXE>"
& $blender --background --factory-startup --python tests\integration\run.py
```

`<BLENDER_EXE>` is platform-specific; a typical Windows path is
`C:\Program Files\Blender Foundation\Blender 5.1\blender.exe`, but the
user must confirm the actual location.

Or the wrapper:

```powershell
.\tasks.ps1 test-blender
```

The runner refuses to start if Blender is interactive (UI is up) unless
`BLCAP_TEST_INTERACTIVE_OK=1` is set. Even with the bypass, it saves the
current .blend before starting -- but a crash mid-test can still corrupt
the in-memory scene. Don't bypass unless you understand the risk.

Covers:

- `bulk_import` round-trip via `timeline.read()`
- frame_change_pre body updates at every line boundary
- overlap "later start wins" regression (issue #9)
- save/reload survives -- re-attaches handlers, F-curve intact
- orphaned master object recovery (v0.1.6 fix)

## All tiers at once

```powershell
.\tasks.ps1 test-all
```

(If the user doesn't have `tasks.ps1` yet, run the three commands above in
order. Stop at the first failure.)

## When to run which tier

- **Editing docs or doc-adjacent files**: Tier 1 only.
- **Editing `timeline.py` encoding logic**: Tier 1 + Tier 2.
- **Editing operators, handlers, master.py**: all three tiers.
- **Before a release / `gh release create`**: all three.

## Adding a new test

- Lint check: edit `tests/lint/check.py`. Follow the existing pattern —
  `check(name, ok, detail)`. Each check is one function.
- Unit test: drop a `test_*.py` into `tests/unit/`. Use pytest.
- Integration test: add a function to `tests/integration/test_*.py`. The
  runner discovers `test_*` functions automatically.

If a bug surfaces in the wild, write a regression test for it BEFORE
landing the fix. The test should fail on `main`, pass on the fix branch.
