# Automated Melee cleanup

This is Theo's experimental, fully automated fork of `doldecomp/melee`.
AI agents make and review its changes. Human review is not implied.

## Repository boundary

- Push only to `t3dotgg/melee` or a local branch.
- Never open a pull request, issue, review, or comment on `doldecomp/melee` for this work.
- Use `--repo t3dotgg/melee` for GitHub CLI mutations. Check the remote URL before pushing.
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
- A progress report alone is not sufficient. Build and check the complete executable.
- Format only edited C and header files with the pinned clang-format version. Run the source checker on affected files.
- Add focused tests for tool behavior and failure cases. Avoid tests that only repeat the implementation.
- Include actual verification results and their limits in the commit or pull request record.
- Attribute automated pull requests to the verified public model and harness. If the model is unknown, name only the harness.

## Local files

- Never commit or upload game images, extracted game data, DOL files, or game build artifacts.
- Keep experiments and extracted files under ignored `build/` or `orig/` paths.
- Do not add private machine paths to documentation.
- Public CI has no original game data. Do not report its tool and style checks as a matching build.
