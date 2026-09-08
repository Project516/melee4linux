# Melee automated cleanup fork

This is **Theo's fully automated attempt to improve Melee's code readability and developer tools**. AI agents make, review, test, and land changes in this fork. Do not assume that a human has reviewed each change.

The original decompilation is the work of [doldecomp/melee and its contributors](https://github.com/doldecomp/melee). This experimental fork builds on their work. It is not an official continuation of that project.

All automated contributions stay in [t3dotgg/melee](https://github.com/t3dotgg/melee). **Do not open pull requests or issues on the official repository for work from this fork.**

## What works

The starting revision, [`ae5898ee0`](https://github.com/doldecomp/melee/commit/ae5898ee0dfda41b34fdf846f7d680a33e14779d), builds all 19,828 measured functions with an exact match for US v1.02. It links all 1,130 measured units. Readability changes in this fork must preserve the complete executable's SHA-1:

```text
GALE01 / US v1.02
08e0bf20134dfcb260699671004527b2d6bb1a45
```

The GameCube executable builds on Apple Silicon and runs in Dolphin with extracted game data. Source modifications can also run in Dolphin. This does not produce a native Mac or PC game. The existing native build target produces a static library.

You need your own US v1.02 game image. Game images, extracted assets, and executables are not included in this repository.

## Start here

- [Build, verify, run, and modify the game](../docs/build-and-run.md). Includes the tested Apple Silicon setup.
- [Source code map](../docs/code-map.md). Find fighter logic, stages, menus, types, and engine code.
- [Stale-move queue](../docs/code/stale-moves.md). How recorded attacks affect damage.
- [ARAM transfer queue](../docs/code/aram-queue.md). How requests move between the CPU and audio memory.
- [Memory allocator](../docs/code/memory-allocator.md), [file loading](../docs/code/file-loading.md), [player tracking](../docs/code/player-tracking.md), and [command streams](../docs/code/commands-and-time.md).
- [Controller input](../docs/code/controller-input.md), [rumble](../docs/code/rumble.md), and [object pools](../docs/code/object-allocation.md).
- [Heap lifecycle](../docs/code/heap-lifecycle.md), [disc preloading](../docs/code/dvd-preloading.md), [game object processes](../docs/code/game-object-processes.md), and [color overlays](../docs/code/color-overlays.md).
- [Contribution rules](CONTRIBUTING.md) and [agent instructions](../AGENTS.md).

After configuring the build, verify a cleanup with:

```sh
python tools/verify.py
```

This command builds `main.dol` and the progress report, runs `ninja diff`, checks source completion, and checks the complete executable against the original hash. A matching hash proves the executable is unchanged. It does not prove that every new name or comment is correct.

## Cleanup priorities

Work in small modules. Replace unclear local names, remove repeated code where the compiler permits it, use known types, and explain code that must retain an unusual form to match. Support names with callers, data, or SDK definitions. Leave uncertain meanings marked as uncertain.

Keep gameplay changes on separate branches. A gameplay mod has different validation needs and is expected to change the executable hash.

Public CI runs tool tests, source style checks, and the existing native library build. It does not have game data and cannot certify an exact GameCube build. Record local `tools/verify.py` results before landing game-code cleanup.
