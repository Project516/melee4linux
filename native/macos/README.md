# Melee for Mac

**A fully automated slop experiment. Not meant for serious use or investigation.**

Theo's agents made this fork. No support, maintenance, or human review is
promised. Please do not spend time investigating it or send its problems to
upstream projects. Changes here happen at Theo's request.

The build first creates and verifies this fork's GameCube executable. DolRecomp
translates that executable and the disc's loader into C. Apple Clang then
compiles them for ARM64. A separate compilation input adds the loader at its
original load address. The game executable and disc files stay unchanged.
ModernGekko and its Dolphin-derived runtime supply Metal graphics, audio,
controller input, memory, timing, and GameCube services.

This is static recompilation. It does not compile the decompiled game C directly
against macOS libraries. The original 32-bit data layout remains in guest memory.
The runtime stops if game CPU execution would require a PowerPC interpreter or
JIT. Graphics and other console services still use the compatibility runtime.

See [the build and play guide](../../docs/native-macos.md).

## Source and licenses

The integration in this directory is GPL-3.0-or-later. Existing notices in
patch context keep their original terms. This does not change the licenses of
the game decompilation or third-party dependencies.

| Project | Pinned commit | Role |
| --- | --- | --- |
| [Melee macOS Recompilation](https://github.com/McDandle/melee-macos-recomp) | `39e30dec9fa7d90fba960ca9189b573a7938e3df` | Mac build, frontend, and runtime patches |
| [ModernGekko-Template](https://github.com/ExpansionPak/ModernGekko-Template) | `eedda2b02dde3aefc02796d859f0033b916aad03` | Dependency pins |
| [ModernGekko](https://github.com/ExpansionPak/ModernGekko) | `5417826c31187d4dadf8588c7aa25bf107782936` | Runtime integration |
| [DolRecomp](https://github.com/ExpansionPak/DolRecomp) | `1bec3554ecc4817cf78319ca3d8a0669477f29fa` | PowerPC to C translation |
| [RecompCore](https://github.com/ExpansionPak/RecompCore) | `55c7b023fa0f4eba1cf3fdbbb25b1c5ec468d5ac` | Dolphin-derived runtime and static CPU execution |

Credit belongs to these projects, the Dolphin contributors, ExpansionPak,
MrPoloGit, and the other authors named in the pinned runtime's `CREDITS.md`.
SDL supplies the macOS GameController backend. Cubeb supplies audio output.
Their source licenses remain in the downloaded dependency trees.

Game images, extracted data, generated C, executables, app bundles, and saves
stay local. Do not upload the playable app or its game module. The app package
contains data from the user's own disc.
