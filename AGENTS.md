# Melee for Linux

This is Project516's automated experiment, based on Theo's Melee for Mac
(`t3dotgg/melee4mac`), which is itself based on `doldecomp/melee`.
It is not meant for serious use or investigation. No support, maintenance, or
human review is promised. Do not present it as an official port or maintained
project.

Work only on Project516's explicit requests. Do not start an unsolicited audit,
investigation, cleanup, or upstream contribution. When Project516 requests work,
use the rules below and keep the automated-experiment notice visible in the
README, app, contribution guidance, and pull request descriptions.

## Repository boundary

- Push only to `Project516/melee4linux` or a local branch.
- Never open a pull request, issue, review, or comment on `doldecomp/melee` or
  on `t3dotgg/melee4mac` for this work.
- Use `--repo Project516/melee4linux` for GitHub CLI mutations. Check the remote URL before pushing.
- The fork's default branch is `master`. Rebase onto its latest commit before opening a pull request.
- Open real pull requests within the fork when a review record is useful. Do not open drafts.
- Keep the automation notice in the README and contribution rules.

## Changes

- Read `.github/CONTRIBUTING.md` and the relevant source and callers first.
- Give each parallel agent a separate worktree and an explicit list of owned files.
- Prefer small, evidence-based changes. Do not guess the meaning of a field or function.
- Preserve known original names, data layouts, exported symbols, and gameplay behavior during cleanup.
- Local variable names, private helpers, known SDK types, and useful comments are good starting points.
- Retain compiler workarounds that matching requires. Explain the reason near the code or in `docs/code/`.
- Keep gameplay experiments separate from cleanup branches.
- Write in plain English. State what was checked and what remains uncertain.

## Verification

- Follow `docs/build-and-run.md`. Configure matching work with `--no-always-apply` to avoid automatic symbol-file writes.
- Run `python tools/verify.py` after every integrated batch that changes game code, headers, or build settings.
- The US v1.02 executable must keep SHA-1 `08e0bf20134dfcb260699671004527b2d6bb1a45`.
- Do not change `config/GALE01/build.sha1` or the original executable to make a cleanup pass.
- Run `python -m unittest discover -s native/linux/tests` after changing `native/linux`. With a fetched runtime under `build/native/recomp`, also run
  `MELEE_TEST_RUNTIME_DIR=build/native/recomp python -m unittest native/linux/tests/test_build.py`,
  which removes and reapplies every patch in build order.
- A progress report alone is not sufficient. Build and check the complete executable.
- Format only edited C and header files with the pinned clang-format version. Run the source checker on affected files.
- Add focused tests for tool behavior and failure cases. Avoid tests that only repeat the implementation.
- Include actual verification results and their limits in the commit or pull request record.
- Attribute automated pull requests to the verified public model and harness. If the model is unknown, name only the harness.

## Local files

- Never commit or upload game images, extracted game data, DOL files, or game build artifacts.
- The AppImage must never contain game data or a compiled game module; `import_game.py` builds the module into the user's directory.
- Keep experiments and extracted files under ignored `build/` or `orig/` paths.
- Do not add private machine paths to documentation.
- Public CI has no original game data. Do not report its tool and style checks as a matching build.
