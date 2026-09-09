# Build and run Melee for Linux

**Melee for Linux is an automated experiment. It is not meant for serious use
or investigation. No support, maintenance, or human review is promised.**

The AppImage runs on x86_64 and aarch64 Linux with glibc 2.39 or newer, a
Vulkan or OpenGL driver, and X11 or Wayland. It contains no game data. You
need your own Melee USA v1.02 disc image as ISO, GCM, CISO, GCZ, or RVZ.

The [runtime notes](../native/linux/README.md) explain static recompilation
and list the projects this build uses. The matching GameCube build and the
Dolphin launch described in [build-and-run.md](build-and-run.md) are separate.

## Play

1. Download `Melee-for-Linux-<arch>.AppImage` from the releases page, or build
   it as described below.
2. Make it executable and start it:

```sh
chmod +x Melee-for-Linux-x86_64.AppImage
./Melee-for-Linux-x86_64.AppImage
```

3. Select Browse, choose your disc image, then Extract and Play.

The first run extracts the disc into `~/.local/share/melee4linux/games/GALE01`,
verifies that its executable has SHA-1 `08e0bf20134dfcb260699671004527b2d6bb1a45`,
translates it to C, and compiles the native module with the bundled compiler.
The launcher shows the progress. This takes a few minutes on a desktop and
around half an hour on a Raspberry Pi 5. Later launches reuse the module until
you install a new AppImage build, which rebuilds it once.

If the AppImage does not start, your system may lack FUSE. Run it with
`--appimage-extract-and-run`, or extract it with `--appimage-extract` and run
`squashfs-root/AppRun`.

Settings live in the launcher window. Internal resolution, graphics backend,
fullscreen, and controller profile come from the ModernGekko launcher. The
Melee section adds:

| Setting | Effect |
| --- | --- |
| 120 FPS visual updates | Draws a predicted frame between game updates. Needs a 120 Hz display. Displays below 119 Hz use 60 FPS. |
| Lower input delay | Samples controllers when the game reads them and submits GPU work before the display wait. |
| Faster loading | Removes simulated disc seek delays. Turn off for original disc timing. |
| Upscaled textures | Enabled when the AppImage was built with `--texture-pack`. |

Melee settings apply on the next launch. They are stored under `[Melee]` in
`~/.local/share/melee4linux/config.ini`.

| Action | Keyboard | Xbox or PS controller |
| --- | --- | --- |
| Move | W, A, S, D | Left stick or D-pad |
| Attack | J | A or Cross |
| Special | K | B or Circle |
| Jump | Space or U | X, Y, Square, or Triangle |
| Grab | O | RB or R1 |
| Shield | Q or E | LT, RT, L2, or R2 |
| C-stick | Arrow keys | Right stick |
| Start | Return | Menu or Options |

Without a gamepad the launcher writes a keyboard profile. With a gamepad
selected, the keyboard stays active for player 1. Dolphin's X11 keyboard
device needs the X11 window, which is the default. Under Wayland the game
still runs through XWayland.

In the game window, Alt+Return toggles fullscreen and Ctrl+Escape stops the
game. F1 to F8 load save states and Shift with those keys saves them, as in
Dolphin's NoGUI frontend.

Saves, settings, save states, the extracted game, and the compiled module are
under `~/.local/share/melee4linux`, or `$XDG_DATA_HOME/melee4linux`. Logs are
in its `Logs` folder. Delete the `Setup` folder to free the translation
scratch space after a build.

## Build

Building needs no game data. On Debian, Ubuntu, or Raspberry Pi OS:

```sh
sudo apt install build-essential cmake ninja-build pkg-config patchelf ccache \
  libx11-dev libxrandr-dev libxi-dev libxext-dev libwayland-dev wayland-protocols \
  libxkbcommon-dev libasound2-dev libpulse-dev libudev-dev libgl1-mesa-dev \
  libegl1-mesa-dev libvulkan-dev
python3 native/linux/build.py --jobs 4
```

Use Python 3.11 or later and a C++23 compiler, GCC 13 or newer. The first
build clones the pinned runtime sources, several hundred megabytes, and
compiles Dolphin. Expect about an hour on a four-core machine. The result is
`build/native/Melee-for-Linux-<arch>.AppImage`. The packager downloads the
pinned Zig, Ninja, Python, and AppImage tools and checks their SHA-256 hashes.

`--jobs` limits compiler processes. On a Raspberry Pi use `--jobs 2` and let
the build run unattended. `--appdir-only` skips the AppImage step and leaves
an `.AppDir` you can run from `AppRun`. `--texture-pack` bundles a texture
pack root that contains `GALE01`.

To import a disc during the build, add `--iso`:

```sh
python3 native/linux/build.py --iso '/path/to/Melee.iso' \
  --user-dir build/native/user-data/melee4linux
```

This runs the launcher's extraction and the AppImage's own module builder into
that isolated user directory. Point `XDG_DATA_HOME` at its parent to play from
it. Nothing in your normal user directory changes.

Public CI builds the x86_64 and aarch64 AppImages on every push and attaches
them to releases for `v*` tags. It has no game data, so it checks that the
AppImage starts and that the bundled compiler works. It cannot check gameplay.

## Limits

The Mac app's in-game Home and Settings overlay is AppKit. On Linux, settings
live in the launcher before the game starts. There is no Metal frame log, so
`native/macos/benchmark.py` does not apply. Netplay uses the ModernGekko lobby
and expects the module to exist already; play once before hosting or joining.

Strict native mode stops on uncovered game CPU code. This makes missing
translation visible instead of hiding it behind an interpreter.

The AppImage links the C++ runtime statically and bundles the desktop
libraries it needs. It uses the host's glibc, X11, OpenGL, and Vulkan
libraries. Older hosts than the build system's glibc 2.39 will not start it.

Do not commit or upload the AppImage built with a texture pack from private
assets, the user directory, or anything derived from a disc.

## Checks on this branch

Unit tests cover the module builder's ninja generation, identity stamp, and
input checks, the packager's library selection and pins, and the build
driver's patch plan. Run them with:

```sh
python3 -m unittest discover -s native/linux/tests -v
MELEE_TEST_RUNTIME_DIR=build/native/recomp python3 -m unittest native/linux/tests/test_build.py
```

The second command needs a fetched runtime checkout. It removes and reapplies
every patch in the build's order.

The Linux preferences source, the patched launcher, and the patched frontend
configuration passed GCC syntax checks against the pinned Dolphin, SDL, and
ImGui headers on a Raspberry Pi 5. A complete runtime build and a gameplay
check on Linux hardware were still pending when this guide was written. Read
the pull request record for the current state.
