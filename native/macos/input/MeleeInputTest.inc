// SPDX-License-Identifier: GPL-3.0-or-later
// Included by the AppKit frontend. Run after InitControllers and before boot.
#include "Core/HW/GCPadEmu.h"
#include "InputCommon/ControlReference/ControlReference.h"
#include "InputCommon/GCPadStatus.h"
#include "InputCommon/InputConfig.h"
#import <GameController/GameController.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <stdexcept>

namespace MeleeInput
{
class ControllerTest
{
public:
  void Run()
  {
    Check("controller interface initialized", g_controller_interface.IsInit());
    Check("GameCube pads initialized", Pad::IsInitialized());
    ControlReference::SetInputGate(true);
    g_melee_menu_open = false;

    GCController *controller = [GCController controllerWithExtendedGamepad];
    Check("Apple software controller has an extended profile",
          controller.isSnapshot && controller.extendedGamepad);
    const std::string device = Connect(controller);
    std::printf("Apple GameController -> %s -> GameCube port 4\n", device.c_str());
    ConfigurePad(device, 3);
    WaitFor("connected pad", [&] { return Read().isConnected; });
    CheckNeutral("connected pad starts neutral");

    GCExtendedGamepad *profile = controller.extendedGamepad;
    struct ButtonCase
    {
      const char *name;
      GCControllerButtonInput *button;
      u16 expected;
    };
    const ButtonCase buttons[] = {
        {"A attack", profile.buttonA, PAD_BUTTON_A},
        {"B special", profile.buttonB, PAD_BUTTON_B},
        {"X jump", profile.buttonX, PAD_BUTTON_X},
        {"Y jump", profile.buttonY, PAD_BUTTON_Y},
        {"RB grab", profile.rightShoulder, PAD_TRIGGER_Z},
        {"Menu start", profile.buttonMenu, PAD_BUTTON_START},
    };
    for (const auto &button : buttons)
    {
      [button.button setValue:1.0f];
      const auto status = Read();
      Check(button.name, status.button == button.expected);
      if (button.expected == PAD_BUTTON_A)
        Check("A analog byte", status.analogA == 255 && status.analogB == 0);
      if (button.expected == PAD_BUTTON_B)
        Check("B analog byte", status.analogB == 255 && status.analogA == 0);
      [button.button setValue:0.0f];
      CheckNeutral("button release clears input");
    }
    [profile.buttonA setValue:1.0f];
    [profile.buttonY setValue:1.0f];
    Check("simultaneous buttons", Read().button == (PAD_BUTTON_A | PAD_BUTTON_Y));
    [profile.buttonA setValue:0.0f];
    [profile.buttonY setValue:0.0f];

    for (int stick = 0; stick < 2; ++stick)
    {
      GCControllerDirectionPad *input =
          stick == 0 ? profile.leftThumbstick : profile.rightThumbstick;
      for (int axis = 0; axis < 2; ++axis)
      {
        for (int sign : {-1, 1})
        {
          [input setValueForXAxis:axis == 0 ? sign : 0 yAxis:axis == 1 ? sign : 0];
          const auto status = Read();
          const int x = stick == 0 ? status.stickX : status.substickX;
          const int y = stick == 0 ? status.stickY : status.substickY;
          const int value = axis == 0 ? x : y;
          Check("stick direction", sign < 0 ? value < 60 : value > 196);
          Check("other stick axis stays centered", (axis == 0 ? y : x) == 128);
          Check("other stick stays centered",
                stick == 0 ? status.substickX == 128 && status.substickY == 128
                           : status.stickX == 128 && status.stickY == 128);
        }
      }
      [input setValueForXAxis:0.05f yAxis:-0.05f];
      CheckNeutral("stick dead zone removes small drift");
      [input setValueForXAxis:0.5f yAxis:0.5f];
      const auto diagonal = Read();
      Check("diagonal stick input", stick == 0
                                        ? diagonal.stickX > 140 && diagonal.stickY > 140
                                        : diagonal.substickX > 140 && diagonal.substickY > 140);
      [input setValueForXAxis:0.0f yAxis:0.0f];
      CheckNeutral("stick release centers input");
    }
    [profile.leftThumbstick setValueForXAxis:1.0f yAxis:0.0f];
    [profile.rightThumbstick setValueForXAxis:0.0f yAxis:-1.0f];
    auto status = Read();
    Check("both sticks operate at once", status.stickX > 196 && status.stickY == 128 &&
                                             status.substickX == 128 && status.substickY < 60);
    [profile.leftThumbstick setValueForXAxis:0.0f yAxis:0.0f];
    [profile.rightThumbstick setValueForXAxis:0.0f yAxis:0.0f];

    for (int trigger = 0; trigger < 2; ++trigger)
    {
      GCControllerButtonInput *input = trigger == 0 ? profile.leftTrigger : profile.rightTrigger;
      const u16 mask = trigger == 0 ? PAD_TRIGGER_L : PAD_TRIGGER_R;
      for (float pressure : {0.1f, 0.5f, 0.89f, 0.91f, 1.0f})
      {
        [input setValue:pressure];
        const auto pad = Read();
        const int analog = trigger == 0 ? pad.triggerLeft : pad.triggerRight;
        const bool digital = pressure >= 0.9f;
        Check("digital shield threshold", pad.button == (digital ? mask : 0));
        Check("analog shield pressure",
              digital ? analog == 255 : std::abs(analog - static_cast<int>(255 * pressure)) <= 1);
        Check("other trigger stays released",
              trigger == 0 ? pad.triggerRight == 0 : pad.triggerLeft == 0);
      }
      [input setValue:0.0f];
      CheckNeutral("trigger release clears analog and digital input");
    }
    [profile.leftTrigger setValue:0.5f];
    [profile.rightTrigger setValue:1.0f];
    status = Read();
    Check("both triggers operate at once", status.triggerLeft >= 126 && status.triggerLeft <= 128 &&
                                               status.triggerRight == 255 &&
                                               status.button == PAD_TRIGGER_R);
    [profile.leftTrigger setValue:0.0f];
    [profile.rightTrigger setValue:0.0f];

    for (int axis = 0; axis < 2; ++axis)
    {
      for (int sign : {-1, 1})
      {
        [profile.dpad setValueForXAxis:axis == 0 ? sign : 0 yAxis:axis == 1 ? sign : 0];
        const auto pad = Read();
        const int value = axis == 0 ? pad.stickX : pad.stickY;
        Check("D-pad movement", sign < 0 ? value < 60 : value > 196);
      }
    }
    [profile.dpad setValueForXAxis:0.0f yAxis:0.0f];

    GCController *second = [GCController controllerWithExtendedGamepad];
    const std::string second_device = Connect(second);
    Check("two controllers have different device names", second_device != device);
    ConfigurePad(second_device, 2);
    [second.extendedGamepad.buttonB setValue:1.0f];
    Check("second controller uses its assigned port", Read(2).button == PAD_BUTTON_B);
    CheckNeutral("second controller does not send input to the first port");
    [profile.buttonA setValue:1.0f];
    [profile.leftTrigger setValue:1.0f];
    [profile.leftThumbstick setValueForXAxis:1.0f yAxis:0.0f];
    Disconnect(controller);
    WaitFor("disconnect clears the connected flag", [&] { return !Read().isConnected; });
    CheckNeutral("disconnect clears held controls");
    Check("other controller remains active after disconnect", Read(2).button == PAD_BUTTON_B);

    controller = [GCController controllerWithExtendedGamepad];
    const std::string reconnected_device = Connect(controller);
    Check("reconnect keeps the stored device name", reconnected_device == device);
    WaitFor("reconnect restores the saved port without reloading config",
            [&] { return Read().isConnected; });
    CheckNeutral("reconnect starts neutral");
    [controller.extendedGamepad.buttonX setValue:1.0f];
    Check("reconnected controller works", Read().button == PAD_BUTTON_X);
    Check("reconnect does not replace another player's input", Read(2).button == PAD_BUTTON_B);
    Disconnect(controller);
    Disconnect(second);
    WaitFor("both test controllers disconnect",
            [&] { return !Read().isConnected && !Read(2).isConnected; });
    std::printf("MELEE_INPUT_TEST PASS: %d checks through Apple GameController, SDL and GCPad\n",
                checks);
    std::puts("Software controllers only. Physical Bluetooth pairing and rumble were not tested.");
  }

private:
  int checks = 0;

  void Check(const char *name, bool pass)
  {
    if (!pass)
      throw std::runtime_error(name);
    ++checks;
  }

  GCPadStatus Read(int port = 3)
  {
    g_controller_interface.UpdateInput();
    return Pad::GetStatus(port);
  }

  void CheckNeutral(const char *name)
  {
    const auto pad = Read();
    Check(name, pad.button == 0 && pad.triggerLeft == 0 && pad.triggerRight == 0 &&
                    pad.analogA == 0 && pad.analogB == 0 && pad.stickX == 128 &&
                    pad.stickY == 128 && pad.substickX == 128 && pad.substickY == 128);
  }

  void WaitFor(const char *name, const std::function<bool()> &ready)
  {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (!ready())
    {
      if (std::chrono::steady_clock::now() >= deadline)
        throw std::runtime_error(name);
      [[NSRunLoop currentRunLoop] runUntilDate:[NSDate dateWithTimeIntervalSinceNow:0.005]];
    }
    ++checks;
  }

  std::string Connect(GCController *controller)
  {
    const auto before = g_controller_interface.GetAllDeviceStrings();
    [[NSNotificationCenter defaultCenter] postNotificationName:GCControllerDidConnectNotification
                                                        object:controller];
    std::string connected;
    WaitFor("Apple controller appears in the SDL runtime backend",
            [&]
            {
              for (const auto &device : g_controller_interface.GetAllDeviceStrings())
              {
                if (device.starts_with("SDL/") &&
                    std::find(before.begin(), before.end(), device) == before.end())
                {
                  connected = device;
                  return true;
                }
              }
              return false;
            });
    return connected;
  }

  static void Disconnect(GCController *controller)
  {
    [[NSNotificationCenter defaultCenter] postNotificationName:GCControllerDidDisconnectNotification
                                                        object:controller];
  }

  static void ConfigurePad(const std::string &device, int port)
  {
    Common::IniFile config;
    auto *section = config.GetOrCreateSection("GCPad" + std::to_string(port + 1));
    ConfigureController(section, device, port);
    auto *pad = Pad::GetConfig()->GetController(port);
    const auto lock = pad->GetStateLock();
    pad->LoadConfig(section);
    pad->UpdateReferences(g_controller_interface);
  }
};

// The test changes only in-memory mappings. Exit before boot or config saving.
inline void RunControllerTestIfRequested()
{
  const char *requested = std::getenv("MELEE_INPUT_TEST");
  if (!requested || std::string_view(requested) != "1")
    return;
  int status = EXIT_SUCCESS;
  @autoreleasepool
  {
    try
    {
      ControllerTest{}.Run();
    }
    catch (const std::exception &error)
    {
      std::fprintf(stderr, "MELEE_INPUT_TEST FAIL: %s\n", error.what());
      status = EXIT_FAILURE;
    }
  }
  std::fflush(nullptr);
  std::_Exit(status);
}
} // namespace MeleeInput
