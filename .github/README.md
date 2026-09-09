# Melee for Linux

**An automated experiment. Not meant for serious use or investigation. No
support, maintenance, or human review is promised.**

Based on Theo's Melee for Mac (`t3dotgg/melee4mac`). Project516 asked AI agents
to make Melee run natively on Linux, packaged as an AppImage, and improve the
fork's code and tools. This is the result. Please do not spend time
investigating, auditing, or maintaining this fork, and do not send its
problems to upstream projects.

This is an unofficial experiment. It builds on the work of
[doldecomp/melee](https://github.com/doldecomp/melee),
[Melee macOS Recompilation](https://github.com/McDandle/melee-macos-recomp),
ModernGekko, DolRecomp, RecompCore, Dolphin, and their contributors.
[Native Linux credits and licenses](../native/linux/README.md#source-and-licenses).
[Native macOS credits and licenses](../native/macos/README.md#source-and-licenses).

## Try the experiment

You need a Linux machine (x86_64 or aarch64, including a Raspberry Pi 5) and
your own Melee USA v1.02 disc image. No game image, extracted game data,
generated game code, or playable binary is included here.

1. Download `Melee-for-Linux-<arch>.AppImage` from this fork's
   [GitHub releases](https://github.com/Project516/melee4linux/releases),
   matching your architecture (`x86_64` or `aarch64`).
2. Make it executable and run it:

```sh
chmod +x Melee-for-Linux-*.AppImage
./Melee-for-Linux-*.AppImage
```

3. Use Browse to select your own Melee USA v1.02 disc image, then select
   Extract and Play.

The first run compiles the native game module locally from your disc image.
This takes a few minutes on a desktop and about half an hour on a Raspberry
Pi 5. The AppImage itself contains no game data or compiled game module.

See the [Linux build guide](../docs/native-linux.md) for build instructions
and known limits.

## Melee for Mac

The Mac build path is inherited from the origin fork and still works. You need
an Apple Silicon Mac and your own Melee USA v1.02 disc image. Follow the
[Melee for Mac guide](../docs/native-macos.md) to build and run
`build/native/Melee for Mac.app`.

## What the checks mean

Local checks covered builds, software controller input, complete matches,
saves, and several loading transitions on the Mac path. As of this writing,
this fork has not yet verified Linux gameplay on real hardware. Public CI
builds the AppImage without any game data, so its success does not certify
gameplay on Linux or the matching executable.

The matching GameCube executable keeps SHA-1
`08e0bf20134dfcb260699671004527b2d6bb1a45`. Public CI checks tools, formatting,
and a native static library. It has no game data and does not certify the
matching executable or a playable app.

## Work on this fork

Changes happen at Project516's explicit request. The
[contribution rules](CONTRIBUTING.md) and [agent instructions](../AGENTS.md)
define that work. The [source map](../docs/code-map.md) and
[matching build reference](../docs/build-and-run.md) are references, not an
invitation to investigate or maintain this experiment.

Keep all work in [Project516/melee4linux](https://github.com/Project516/melee4linux).
Never open a pull request, issue, review, or comment on `doldecomp/melee` or on
`t3dotgg/melee4mac` for work from this fork.
