# macOS controller input

The native runtime uses SDL 3's Apple GameController backend for Xbox One and
Xbox Series Bluetooth controllers. This is the macOS controller API. No custom
Bluetooth driver is installed.

`MeleeControllerConfig.h` selects that backend before controller startup and
provides the mapping used by the Input settings screen. SDL supplies device
names and hotplug events. Dolphin's controller layer converts each sample to
`GCPadStatus`, which the native game reads through its GameCube services.

## Use an Xbox controller

1. Pair the controller in System Settings > Bluetooth and turn it on.
2. Open Melee > Settings > Input.
3. Select the controller's `SDL/` entry for a player. Use Refresh connected
   controllers if the list was open when the controller connected.
4. Resume the game.

The selected device and player port are saved. The runtime updates input
references when a device disconnects or reconnects.

| Xbox control | Melee input |
| --- | --- |
| A | Attack and confirm |
| B | Special and cancel |
| X or Y | Jump |
| RB | Grab |
| Menu | Start and pause |
| Left stick | Movement |
| Right stick | C-stick |
| D-pad | Movement |
| LT and RT | Analog shield, then digital shield at 90 percent travel |

Both sticks have a 10 percent dead zone. Triggers have no dead zone, so light
pressure remains available for light shields. The last 10 percent of trigger
travel produces the GameCube trigger's digital press and full analog value.
Xbox triggers do not have the separate physical click found on a GameCube pad.

The keyboard mapping remains available on player 1 when that player's selected
controller is connected. Select Keyboard & Mouse to play without a controller.

## Test without physical hardware

Set `MELEE_INPUT_TEST=1` for a normal native runtime launch. For the pinned
runtime workspace, use:

```sh
MELEE_FRONTEND=1 MELEE_INPUT_TEST=1 ./scripts/run_macos.sh
```

The build driver must first apply `../patches/apple-input.patch` to the pinned
`melee-macos-recomp` wrapper and copy `MeleeControllerConfig.h` and
`MeleeInputTest.inc` beside its generated `MeleeFrontend.inc`.

The test starts after controller initialization and exits before game boot.
It creates writable controllers with Apple's public
`GCController.controllerWithExtendedGamepad` API. It sends process-local
connect and disconnect notifications to SDL's real GameController backend.
It writes button, stick and trigger values to the Apple profiles, then checks
the resulting packets from the runtime's `Pad::GetStatus` function.

The checks cover:

- Face buttons, grab, start, button release and simultaneous buttons.
- Each direction of both sticks, diagonal input, dead zones and both sticks
  in use at once.
- Independent analog triggers, the digital shield threshold and release.
- D-pad movement and two controllers assigned to separate ports.
- Disconnect while controls are held, reconnect with the saved mapping and
  continued input on the other player's controller.

The test changes controller mappings in memory only. It exits with status 0
and a `MELEE_INPUT_TEST PASS` line when all checks pass. A failure returns
status 1 and names the failed check. Test controllers exist only in that
process. They do not appear in macOS Bluetooth settings or control other apps.

This tests the Apple API, SDL backend, runtime mapping and hotplug callbacks.
It does not test physical Bluetooth pairing, radio latency, battery behavior
or hardware rumble. A paired Xbox controller is still needed for those checks.

## Verified result

The native ARM64 runtime passed all 103 checks on an Apple Silicon Mac on
2026-09-08. The test exercised the runtime built with these input includes and
the pinned wrapper patch. Physical Bluetooth and rumble remain untested.

## Source

The mapping is adapted from `macos/MeleeFrontend.inc` in
[McDandle/melee-macos-recomp](https://github.com/McDandle/melee-macos-recomp)
at commit `39e30dec9fa7d90fba960ca9189b573a7938e3df`.
Keep that project's GPL-3.0-or-later license and credits with the native runtime.
SDL's Apple backend is `src/joystick/apple/SDL_mfijoystick.m`. The runtime's
mapping and packet code is in Dolphin's `InputCommon/ControllerInterface/SDL`,
`InputCommon/ControllerEmu/ControlGroup/MixedTriggers.cpp` and
`Core/HW/GCPadEmu.cpp`.
