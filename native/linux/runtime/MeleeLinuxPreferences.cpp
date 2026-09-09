// SPDX-License-Identifier: GPL-3.0-or-later
// Linux replacement for the Mac frontend's MeleeApplyMediaPreferences. The
// launcher passes saved settings through the environment. The runtime calls
// this after its defaults are installed and before game, audio, and video boot.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string_view>

#include "Common/Config/Config.h"
#include "Common/FileUtil.h"
#include "Core/Config/GraphicsSettings.h"
#include "Core/Config/MainSettings.h"
#include "Core/Config/StaticRecompSettings.h"
#include "Core/NetPlay/NetPlayProto.h"
#include "VideoCommon/MeleeTexturePack.h"
#include "VideoCommon/VideoConfig.h"

namespace
{
bool EnvEnabled(const char* name, bool default_value)
{
  const char* value = std::getenv(name);
  if (value == nullptr || *value == '\0')
    return default_value;
  return std::strcmp(value, "0") != 0;
}

double EnvNumber(const char* name)
{
  const char* value = std::getenv(name);
  return value == nullptr ? 0.0 : std::strtod(value, nullptr);
}
}  // namespace

extern "C" void MeleeApplyMediaPreferences()
{
  const char* explicit_pack = std::getenv("MELEE_TEXTURE_PACK");
  if (explicit_pack != nullptr)
  {
    // AppRun sets MELEE_TEXTURE_PACK when the AppImage carries a pack. An
    // invalid explicit path disables replacements instead of guessing.
    const auto texture_pack = MeleeTextures::FindPackRoot(explicit_pack, "");
    const bool enabled = EnvEnabled("MELEE_TEXTURES", true) && texture_pack.has_value();
    if (texture_pack)
      File::SetUserPath(D_HIRESTEXTURES_IDX, texture_pack->string());
    Config::SetCurrent(Config::GFX_HIRES_TEXTURES, enabled);
    // Load only requested textures using Dolphin's background asset workers.
    Config::SetCurrent(Config::GFX_CACHE_HIRES_TEXTURES, false);
    if (enabled)
    {
      Config::SetCurrent(Config::GFX_ENHANCE_MAX_ANISOTROPY, AnisotropicFilteringMode::Force16x);
      Config::SetCurrent(Config::GFX_ENHANCE_FORCE_TEXTURE_FILTERING, TextureFilteringMode::Default);
    }
    std::fprintf(stderr, "[melee-textures] %s, pack=%s\n", enabled ? "enabled" : "disabled",
                 texture_pack ? texture_pack->string().c_str() : "none");
  }

  // Netplay keeps the peers' shared timing and disc settings.
  if (std::getenv("MELEE_APP_BUNDLE") == nullptr || NetPlay::IsNetPlayRunning())
    return;

  Config::SetCurrent(Config::MAIN_FAST_DISC_SPEED, EnvEnabled("MELEE_FAST_LOADING", true));

  // Normalize the requested rate so the video interface patch reads 60 or 120.
  const char* requested = std::getenv("MELEE_RENDER_FPS");
  const bool wants_60 = requested != nullptr && std::string_view(requested) == "60";
  setenv("MELEE_RENDER_FPS", wants_60 ? "60" : "120", 1);
  // The compositor can limit presentation even with vertical sync off. The
  // launcher reports the primary display's rate; a zero keeps the request.
  const double display_hz = EnvNumber("MELEE_DISPLAY_HZ");
  if (display_hz > 0 && display_hz < 119)
  {
    setenv("MELEE_RENDER_FPS", "60", 1);
    std::fprintf(stderr, "[melee-video] Using 60 FPS on a %.2f Hz display to keep normal game speed.\n",
                 display_hz);
  }
  const bool low_latency = EnvEnabled("MELEE_LOW_LATENCY", true);
  // The render config reads this name on every backend.
  setenv("MELEE_METAL_LOW_LATENCY", low_latency ? "1" : "0", 0);
  const bool high_refresh = std::string_view(std::getenv("MELEE_RENDER_FPS")) == "120";
  Config::SetCurrent(Config::GFX_HACK_IMMEDIATE_XFB, high_refresh || low_latency);
  Config::SetCurrent(Config::GFX_HACK_CAP_IMMEDIATE_XFB, false);
  Config::SetCurrent(Config::MAIN_VI_OVERCLOCK_ENABLE, high_refresh);
  Config::SetCurrent(Config::MAIN_VI_OVERCLOCK, high_refresh ? 2.0f : 1.0f);
  Config::SetCurrent(Config::MAIN_RUSH_FRAME_PRESENTATION, true);
  Config::SetCurrent(Config::MAIN_PRECISION_FRAME_TIMING, true);
  // Melee's verified scheduler idle loop. The runtime skips it instead of spinning.
  Config::SetCurrent(Config::MAIN_STATICRECOMP_IDLE_PC, 0x8034B164u);
  if (const char* vsync = std::getenv("MELEE_VSYNC"); vsync != nullptr && *vsync != '\0')
    Config::SetCurrent(Config::GFX_VSYNC, std::strcmp(vsync, "0") != 0);
  std::fprintf(stderr, "[melee-video] %s FPS, %s input delay, %s loading\n",
               high_refresh ? "120" : "60", low_latency ? "lower" : "original",
               Config::Get(Config::MAIN_FAST_DISC_SPEED) ? "faster" : "original disc");
}
