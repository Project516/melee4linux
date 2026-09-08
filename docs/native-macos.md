# Build native Melee on an Apple Silicon Mac

This experimental build uses native ARM64 game code, Metal graphics, and the
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

The result is `build/native/Melee.app`. It contains the runtime, native game
module, and local disc data. The app can be moved as one directory. It uses
separate settings and saves, so it does not change Dolphin's user folder.

## Play

```sh
open build/native/Melee.app
```

Select Play. Escape opens the app menu. Command-comma opens Settings.

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
