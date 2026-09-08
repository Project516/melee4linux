# Build and run Melee for Mac

**Melee for Mac is a fully automated slop experiment. It is not meant for serious
use or investigation. No support, maintenance, or human review is promised.**

These are instructions for trying the experiment with your own game data.
The build uses native ARM64 game code, Metal graphics, and the
macOS controller APIs through SDL. It requires an Apple Silicon Mac and your
own Melee USA v1.02 disc image. Build on the Mac where you intend to play.
The app records the minimum macOS version required by its compiled libraries.

The [runtime notes](../native/macos/README.md) explain static recompilation and
list the projects this build uses. This is separate from the native static
library compile check and the normal Dolphin launch described in
[build-and-run.md](build-and-run.md).

## Build

First follow [the matching build setup](build-and-run.md) to create `.venv` and
put your original executable at `orig/GALE01/sys/main.dol`. Then install the
Mac runtime's build dependencies with Homebrew:

```sh
brew install cmake ninja pkgconf python fmt libusb lzo lz4 zstd pugixml
. .venv/bin/activate
python native/macos/build.py --iso '/path/to/Melee.iso'
```

Use Python 3.11 or later. Xcode's command line tools must be installed. The
first build downloads pinned source dependencies and compiles the runtime and
game. Generated code and game data stay under the ignored `build/native/` path.
Use `--jobs 8` to limit compiler processes.

The build verifies the entire matching GameCube executable before translation.
Its SHA-1 must be `08e0bf20134dfcb260699671004527b2d6bb1a45`. The current native
runtime uses fixed OS vector addresses for that revision. Other revisions and
modified executables are rejected.

The result is `build/native/Melee for Mac.app`. It contains the runtime, native game
module, and local disc data. The app can be moved as one directory. It uses
separate settings and saves, so it does not change Dolphin's user folder.

## Play

```sh
open "build/native/Melee for Mac.app"
```

Select Play. Escape opens the app menu. Command-comma opens Settings.

Older builds were named `Melee.app` or displayed as "Melee Native". The bundle
ID and `Application Support/t3.melee.native` save folder remain the same.
Use `git pull` on `master` and repeat the build command to update. GitHub
redirects the old `t3dotgg/melee` repository URL to `t3dotgg/melee4mac`.

Faster loading is enabled for local play. It removes simulated GameCube disc
seek delays and raises the modeled buffer transfer rate to 256 MiB/s. Reads
keep their asynchronous completion order and 600 microsecond command delay.
To use the original disc timing, turn off Faster loading in Settings, General.
The preference is saved. It does not override netplay settings.

Bundled local startup skips unused whole-asset hashes. Executable checks still
run. Netplay, import tools, and builds that require an asset digest retain full
asset hashing.

The app keeps its pipeline list under `~/Library/Application Support/t3.melee.native/Cache`.
Known pipelines can compile before gameplay on later launches. Metal does not
store compiled pipeline binaries in this runtime, so a new effect can still
cause a first-use pause.

| Action | Keyboard | Xbox controller |
| --- | --- | --- |
| Move | W, A, S, D | Left stick |
| Attack | J | A |
| Special | K | B |
| Jump | Space or U | X or Y |
| Grab | O | RB |
| Shield | Q or E | LT or RT |
| C-stick | Arrow keys | Right stick |
| Start | Return | Menu |

Pair the Xbox controller in System Settings, Bluetooth. Select the connected
device in the app's input settings. macOS handles the Bluetooth connection.
Controller tests can use a software controller through Apple's GameController
framework. Those tests cannot verify the physical Bluetooth link.

## Limits

Strict native mode stops on uncovered game CPU code. This makes missing
translation visible instead of hiding it through a PowerPC interpreter.
Debugger single-step and interpreter comparison are unavailable in that mode.

The app is a local development build with an ad hoc signature. It is not a
published or notarized game. Intel Macs, Slippi, and online play are outside
this build path.

Do not commit or upload the app, game module, generated C, disc data, or saves.

## Checks on 2026-09-08

On an M5 Max with macOS 26.5.2, the native app completed a two-minute Mario
versus Fox match on Yoshi's Island, displayed results, and returned to
character select. Attacks, jumping, shielding, damage, stock losses, sound
generation, save-state loading, and settings pause/resume were checked.
The sampled gameplay section ran at 59.91 to 59.96 FPS. Shutdown reported zero
CPU fallback steps and zero failed code checks. This is one tested match,
not full coverage of every mode and stage.

The controller path passed 103 checks using Apple's software controller API.
Physical Bluetooth and rumble still need hardware testing.

The app also reopened from its Applications folder using the saved memory
card. Its runtime and game data were contained in that app directory.
The cache check wrote 215 pipeline entries and read them on the next launch.
The Faster loading switch saved and restored its preference, and its disabled
state restored the slower transition time.

The loading comparison used identical saved transitions, four runs per
setting, and the median of the last three runs. Each measurement includes
the same input hold and 30 rendered frames after it. These are transition
times on this Mac, not measurements of file I/O alone.

| Transition | Original disc timing | Faster loading |
| --- | ---: | ---: |
| VS menu to character select | 3.71 s | 0.94 s |
| Stage select to Yoshi's Island | 2.26 s | 0.85 s |

A second pass removed two full asset-hash scans at startup and tested a higher
local transfer rate. The comparison used the same Mac at 3x internal resolution,
the same assets and pipeline cache, and no diagnostic tracing during timing.

| Test | Before the second pass | After |
| --- | ---: | ---: |
| Normal launch to first rendered frame | 10.46 to 13.68 s | 1.60 to 1.65 s |
| Launch into the same saved menu, median | 14.99 s | 0.75 s |
| Warm character-select transition, 32 versus 256 MiB/s | 0.92 s | 0.79 s |
| Warm Yoshi's Island transition, 32 versus 256 MiB/s | 0.86 s | 0.81 s |

Normal startup used two old-build launches and three new-build launches. Saved
menu startup used three of each. The transfer comparison kept the startup
change enabled on both sides and used the last three of four transitions per
launch, across three 32 MiB/s launches and two 256 MiB/s launches. The same
input hold and 30-frame settling interval are included in each transition.
A 1024 MiB/s trial gave little additional benefit. `MELEE_DISC_MIB_PER_SECOND`
can select a rate from 32 to 1024 for developer comparisons. Normal local play
uses 256. The override only applies when Faster loading is enabled, the app is
bundled, and netplay is inactive.

The final build also completed a two-minute Mario versus Peach match on Fountain
of Dreams and restored a saved result screen. Its 242 sampled frame-rate readings
had a 59.94 FPS median. Shutdown reported no CPU fallback or failed code checks.
Turning Faster loading off restored approximately 3.74-second character-select
and 2.27-second stage transitions in the same test.

The original game keeps a 20-frame input wait on main-menu entry and five-frame
waits on submenu changes. This update preserves those waits and the normal game
clock. Graphics prewarming was also tested. An unused variant added about
102 ms to startup, so broader prewarming was not retained.

The complete GameCube executable still matches SHA-1
`08e0bf20134dfcb260699671004527b2d6bb1a45`. Public CI checks tools and the native
static library. It does not have the game data needed for this matching check
or the playable app build.
