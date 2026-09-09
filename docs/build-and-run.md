# Matching GameCube build for Melee for Mac

Melee for Mac is a fully automated slop experiment, not meant for serious use
or investigation. No support, maintenance, or human review is promised.
For the Mac app, use [the Melee for Mac guide](native-macos.md).

This reference builds the GameCube executable and runs it in Dolphin. The steps
were tested on an Apple Silicon Mac with Dolphin 2606a and WiBo 1.1.0.
The matching build reproduces Melee US v1.02 byte for byte.

Run these commands from the repository root. For another operating system,
start with the [upstream dependency instructions](https://github.com/doldecomp/melee/blob/ae5898ee0dfda41b34fdf846f7d680a33e14779d/.github/README.md#dependencies),
but clone `https://github.com/Project516/melee4linux.git` for work on this fork.
The [code map](code-map.md) explains where to make source changes.

## Get the original executable

You need your own Melee US v1.02 disc image. Other revisions have different
executables. The build also extracts font data from the original executable,
so complete C source does not remove this requirement.

In [Dolphin](https://dolphin-emu.org/), add the folder that contains your disc
image to the game list. Open the game's Properties, select Filesystem,
right-click `Disc - GALE01`, and select Extract System Data. Choose
`orig/GALE01` in this checkout. The required result is:

```text
orig/GALE01/sys/main.dol
```

If you already have an extracted `main.dol`, copy it to that path. Check it:

```sh
shasum -a 1 orig/GALE01/sys/main.dol
```

The expected SHA-1 is `08e0bf20134dfcb260699671004527b2d6bb1a45`.
This is recorded in [the version configuration](../config/GALE01/config.yml).
The executable is enough to build. Running the game also needs the other
disc files, which the launch steps below extract.

## Install the build tools

Install Python 3 if it is not available. Then create and activate a virtual
environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r reqs/build.txt ninja
```

Activate this environment again when you open a new shell. Ninja downloads
the compiler and other project tools during the first build.

The original compiler is a Windows program. On the tested Mac, WiBo runs it
without a Wine installation. The released Mac wrapper is an Intel binary.
Apple Silicon therefore needs Rosetta 2. If Rosetta is not installed, run
Apple's installer and follow its license prompt:

```sh
softwareupdate --install-rosetta
```

On Intel and Apple Silicon Macs, Ninja downloads WiBo 1.1.0 to
`build/tools/wibo` during the first build. No manual wrapper download is needed.
Version 1.2.0 failed in the project's Shift JIS wrapper with
`GetProcAddressFail` during the Mac test, so the Mac build uses 1.1.0.

If you need a different wrapper, pass `--wrapper /path/to/wibo-or-wine` to
`configure.py`. An explicit wrapper disables the automatic WiBo download.

## Build and verify the original game

```sh
python configure.py --map --no-always-apply
python tools/verify.py
```

The verification command builds the executable and progress report, checks
the object differences, checks source completion, and checks the final
executable hash. It uses the existing configuration. Its `--version` option
selects the game version, and `--ninja` selects a Ninja executable. See
[`tools/verify.py`](../tools/verify.py) for its options.

To run the build and hash checks manually:

```sh
ninja build/GALE01/main.dol build/GALE01/report.json
ninja diff
shasum -a 1 build/GALE01/main.dol
```

Compare the final hash with `08e0bf20134dfcb260699671004527b2d6bb1a45`.
These manual commands do not check source completion. The build can use an
original object for a source file marked incomplete, so use `tools/verify.py`
to accept a cleanup.

`--no-always-apply` stops the build from automatically applying linked symbols
back to the project configuration. With this option, plain `ninja` defaults
to progress generation. Request `main.dol` explicitly so that you also link
the game.

Useful generated files are:

| File | Use |
| --- | --- |
| `build/GALE01/main.dol` | GameCube executable to run in Dolphin |
| `build/GALE01/main.elf.MAP` | Symbol addresses from this build |
| `build/GALE01/report.json` | Matching and completion measurements |
| `objdiff.json` | Project configuration for objdiff |
| `compile_commands.json` | Include paths and compile flags for editor tools |

## Run with the disc files

Close any existing Dolphin test session. Set `MELEE_DISC_IMAGE` to your
disc image, then extract it into the ignored build directory:

```sh
MELEE_DISC_IMAGE='/path/to/Melee.iso'
build/tools/dtk disc extract -q "$MELEE_DISC_IMAGE" build/disc
cp build/GALE01/main.dol build/disc/sys/main.dol
/Applications/Dolphin.app/Contents/MacOS/Dolphin \
  --user "$PWD/build/dolphin-user" \
  --exec "$PWD/build/disc/sys/main.dol" \
  --config Dolphin.Display.RenderToMain=True
```

Adjust the application path if Dolphin is installed elsewhere. Extract the
disc once. After each rebuild, close emulation, repeat the `cp` command, and
launch Dolphin again. Copy only into `build/disc`. Keep the original at
`orig/GALE01/sys/main.dol` for matching checks.

The separate user folder contains this test session's settings and saves.
Set port 1 to Standard Controller in Dolphin's Controllers dialog, then
configure your keyboard, controller, or adapter. The first launch may ask
you to create a game save.

The extracted layout ran successfully in the Mac test. Launching a lone
DOL with a default ISO stalled during startup in that test. If your DOL
boots to a black screen, first check that you launched
`build/disc/sys/main.dol` and that `build/disc/files` contains the extracted
assets. Dolphin's Movie > TAS Input window can supply controller input for
repeatable manual checks.

## Make and inspect a source change

For cleanup that should preserve the original executable, keep the matching
configuration above. Make one focused change, then run:

```sh
python tools/verify.py
git diff --check
```

If a C change stops matching, open [objdiff](https://github.com/encounter/objdiff),
select this checkout as its project directory, and inspect the changed
object. The generated `objdiff.json` supplies the paths. Compare the
instructions before changing compiler flags or removing matching controls.

For a gameplay experiment, configure a non-matching build:

```sh
python configure.py --map --no-always-apply --non-matching
ninja build/GALE01/main.dol
```

For example, changing `gm_IsCKindUnlocked` in
[`gm_1601.c`](../src/melee/gm/gm_1601.c) to return `true` enables the full
selectable roster. This source change was built and tested in Training on
Onett. It changes an unlock check, rather than writing every unlock flag in
the save file.

Non-matching mode changes compiler controls even without a source edit.
Debug builds also imply non-matching mode. Neither mode should pass the
original hash check. Test changed behavior in Dolphin. Record the mode,
characters, stage, input, and result so that someone else can repeat it.

Relinking can move function and data addresses. Existing patches that use
fixed addresses need a separate compatibility check against the new map.
Before returning to cleanup, restore your experimental source changes,
rerun the matching configuration, and run `tools/verify.py` again.

## What the native target does

For the separate playable ARM64 build, see
[native Melee on macOS](native-macos.md). It translates the verified GameCube
executable and joins it to a macOS compatibility runtime.

The [native CMake target](../.nix/CMakeLists.txt) builds a static library.
The [Nix configuration](../.nix/overlay.nix) selects 32-bit Linux for it.
It is useful for compile checks, but it does not produce a playable Mac or
PC application. A native port still needs host graphics, audio, input,
disc access, and other platform services. The
[archive loader](../src/sysdolphin/baselib/archive.c) also depends on the
disc's byte order and 32-bit pointer layout.

Keep disc images, extracted assets, generated executables, and local saves
out of commits. The `orig` and `build` paths used here are ignored by Git.
