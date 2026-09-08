// SPDX-License-Identifier: GPL-3.0-or-later
// Mapping adapted from McDandle/melee-macos-recomp. See README.md for
// provenance.
#pragma once

#include <string>

#include "Common/IniFile.h"
#include <SDL3/SDL.h>

namespace MeleeInput {
    // Keep Xbox Bluetooth input on Apple's GameController framework. SDL still
    // handles other controller types and supplies one common mapping to the
    // game.
    inline void ConfigureAppleBackend()
    {
        SDL_SetHint(SDL_HINT_JOYSTICK_MFI, "1");
        SDL_SetHint(SDL_HINT_JOYSTICK_HIDAPI_XBOX_ONE, "0");
    }

    // Shared by the settings screen and the controller test. Names come from
    // Dolphin's SDLGamepad backend, which maps face buttons by their
    // positions.
    inline void ConfigureController(Common::IniFile::Section* section,
                                    const std::string& device, int port)
    {
        section->Set("Device", device);
        const bool keyboard = device.starts_with("Quartz/");
        const char* keys[][3] = {
            { "Buttons/A", "J", "`Button A`" },
            { "Buttons/B", "K", "`Button B`" },
            { "Buttons/X", "Space", "`Button X`" },
            { "Buttons/Y", "U", "`Button Y`" },
            { "Buttons/Z", "O", "`Shoulder R`" },
            { "Buttons/Start", "Return", "Start" },
            { "Main Stick/Up", "W", "`Left Y+` | `Pad N`" },
            { "Main Stick/Down", "S", "`Left Y-` | `Pad S`" },
            { "Main Stick/Left", "A", "`Left X-` | `Pad W`" },
            { "Main Stick/Right", "D", "`Left X+` | `Pad E`" },
            { "C-Stick/Up", "Up", "`Right Y+`" },
            { "C-Stick/Down", "Down", "`Right Y-`" },
            { "C-Stick/Left", "Left", "`Right X-`" },
            { "C-Stick/Right", "Right", "`Right X+`" },
            { "Triggers/L", "Q", "`Trigger L`" },
            { "Triggers/R", "E", "`Trigger R`" },
            { "Triggers/L-Analog", "Q", "`Trigger L`" },
            { "Triggers/R-Analog", "E", "`Trigger R`" },
            { "D-Pad/Up", "T", "" },
            { "D-Pad/Down", "G", "" },
            { "D-Pad/Left", "F", "" },
            { "D-Pad/Right", "H", "" },
            { "Rumble/Motor", "", "`Motor L` | `Motor R`" },
        };
        for (const auto& key : keys) {
            std::string expression = key[keyboard ? 1 : 2];
            if (!keyboard && port == 0 && *key[1]) {
                expression += (expression.empty() ? "" : " | ") +
                              std::string("`Quartz/0/Keyboard & Mouse:") +
                              key[1] + "`";
            }
            section->Set(key[0], expression);
        }
        section->Set("Main Stick/Dead Zone", 10.0);
        section->Set("C-Stick/Dead Zone", 10.0);
        // Xbox triggers have no separate click. Keep their full analog travel
        // and turn the last 10 percent into the GameCube trigger's digital
        // press.
        section->Set("Triggers/Dead Zone", 0.0);
        section->Set("Triggers/Threshold", 90.0);
    }
} // namespace MeleeInput
