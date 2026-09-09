# Melee for Linux

**An automated experiment. Not meant for serious use or investigation.**

This is Project516's Linux port of Theo's Melee for Mac fork. No support,
maintenance, or human review is promised. Please do not send its problems to
upstream projects.

The AppImage holds the Dolphin-derived runtime, the ModernGekko launcher, the
DolRecomp translator, and a small compiler toolchain. It holds no game data.
On first play the launcher extracts your own Melee USA v1.02 disc, DolRecomp
translates the verified executable and disc loader to C, and the bundled
compiler builds the native module into your user directory. The game
executable and disc files stay unchanged.

This is static recompilation. It does not compile the decompiled game C
against Linux libraries. The runtime stops if game CPU execution would need a
PowerPC interpreter. Graphics use Vulkan or OpenGL through Dolphin's video
backends. The native render hooks, exact 60 or 120 Hz video timing, and
faster loading are the same code the Mac build applies after translation.

See [the build and play guide](../../docs/native-linux.md).

## Layout

| Path | Role |
| --- | --- |
| `build.py` | Fetches the pinned runtime, applies patches, builds, and packages |
| `package.py` | Assembles the AppDir and AppImage; pins the bundled tool downloads |
| `import_game.py` | Runs inside the AppImage: verifies the disc, translates, compiles the module |
| `AppRun`, `melee-import-game`, `melee4linux.desktop` | AppImage entry points |
| `runtime/MeleeLinuxPreferences.cpp` | Applies launcher settings inside the runtime |
| `patches/linux-runtime.patch` | Compiles the preferences source and calls it at boot |
| `patches/linux-launcher.patch` | Module build step, Melee settings, keyboard profile in the launcher |
| `patches/vulkan-present.patch` | Early GPU submission for the Vulkan backend |

Shared code lives beside the Mac port: `../macos/patches` (the Dolphin and
runtime patches that are not AppKit or Metal specific), `recompile_boot.py`,
`high_refresh.py`, and the texture and render headers. `build.py` lists which
of those it applies.

## Source and licenses

The integration in this directory is GPL-3.0-or-later. Existing notices in
patch context keep their original terms. The pinned projects are the same as
the Mac build's:

| Project | Pinned commit | Role |
| --- | --- | --- |
| [Melee macOS Recompilation](https://github.com/McDandle/melee-macos-recomp) | `39e30dec9fa7d90fba960ca9189b573a7938e3df` | Runtime patches and credits |
| [ModernGekko-Template](https://github.com/ExpansionPak/ModernGekko-Template) | `eedda2b02dde3aefc02796d859f0033b916aad03` | Dependency pins |
| [ModernGekko](https://github.com/ExpansionPak/ModernGekko) | `5417826c31187d4dadf8588c7aa25bf107782936` | Runtime integration and launcher |
| [DolRecomp](https://github.com/ExpansionPak/DolRecomp) | `1bec3554ecc4817cf78319ca3d8a0669477f29fa` | PowerPC to C translation |
| [RecompCore](https://github.com/ExpansionPak/RecompCore) | `55c7b023fa0f4eba1cf3fdbbb25b1c5ec468d5ac` | Dolphin-derived runtime |

The AppImage also carries [Zig](https://ziglang.org) 0.15.2 as the C compiler
for the game module, [Ninja](https://ninja-build.org) 1.13.2, and
[python-build-standalone](https://github.com/astral-sh/python-build-standalone)
CPython 3.12. Their licenses are in `usr/share/melee/licenses` inside the
AppImage. Credit belongs to these projects, the Dolphin contributors,
ExpansionPak, MrPoloGit, McDandle, and Theo's melee4mac agents.

Game images, extracted data, generated C, compiled modules, and saves stay in
your user directory. Do not upload them.
