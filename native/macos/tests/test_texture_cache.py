"""Exercise the real Dolphin resource state machine with a small fake asset store."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


DOLPHIN_SOURCE = os.environ.get("MELEE_TEST_DOLPHIN_SOURCE")


@unittest.skipUnless(DOLPHIN_SOURCE and shutil.which("c++"), "Set MELEE_TEST_DOLPHIN_SOURCE to patched Dolphin Source/Core")
class TextureCacheTests(unittest.TestCase):
    def test_eviction_releases_pixels_and_next_use_reloads(self):
        source = Path(DOLPHIN_SOURCE)
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            stubs = {
                "Common/WorkQueueThread.h": "namespace Common { class AsyncWorkThreadSP; }",
                "Common/Logging/Log.h": "#define ERROR_LOG_FMT(...) ((void)0)",
                "VideoCommon/Assets/CustomAssetLibrary.h": r'''
#include <string>
namespace VideoCommon {
class CustomAssetLibrary { public: using AssetID = std::string; };
}
''',
                "VideoCommon/Assets/CustomTextureData.h": r'''
#include <vector>
namespace VideoCommon {
struct CustomTextureData { std::vector<unsigned char> pixels; };
}
''',
                "VideoCommon/Assets/TextureAsset.h": r'''
#include <chrono>
#include <memory>
#include "VideoCommon/Assets/CustomTextureData.h"
namespace VideoCommon {
class CustomAsset { public: using TimeType = std::chrono::steady_clock::time_point; };
class TextureAsset : public CustomAsset {
public:
    std::shared_ptr<CustomTextureData> data;
    TimeType time;
    TimeType GetLastLoadedTime() const { return time; }
    auto GetData() const { return data; }
};
}
''',
                "VideoCommon/Assets/CustomAssetCache.h": r'''
#include "VideoCommon/Assets/TextureAsset.h"
namespace VideoCommon {
class CustomAssetCache {
public:
    TextureAsset texture;
    int pending = 0;
    template<class T, class... Args> T* CreateAsset(Args&&...) { return &texture; }
    void MarkAssetActive(TextureAsset*) {}
    void MarkAssetPending(TextureAsset*) { ++pending; }
};
}
''',
            }
            for relative, content in stubs.items():
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("#pragma once\n" + content)
            for relative in (
                "VideoCommon/Assets/AssetListener.h",
                "VideoCommon/Resources/Resource.h",
                "VideoCommon/Resources/Resource.cpp",
                "VideoCommon/Resources/TextureDataResource.h",
                "VideoCommon/Resources/TextureDataResource.cpp",
            ):
                target = directory / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / relative, target)
            test = directory / "cache.cpp"
            test.write_text(r'''
#include <cassert>
#include "VideoCommon/Resources/TextureDataResource.h"
#include "VideoCommon/Assets/CustomAssetCache.h"

int main()
{
    using namespace VideoCommon;
    CustomAssetCache cache;
    Resource::ResourceContext context{};
    context.primary_asset_id = "test";
    context.asset_cache = &cache;
    TextureDataResource resource(context);
    AssetListener& listener = resource;

    resource.Process();
    assert(cache.pending == 1);
    assert(!resource.GetData());

    cache.texture.data = std::make_shared<CustomTextureData>();
    cache.texture.data->pixels.resize(1024 * 1024);
    cache.texture.time = std::chrono::steady_clock::now();
    listener.NotifyAssetLoadSuccess();
    resource.Process();
    assert(resource.GetData() == cache.texture.data);
    std::weak_ptr<CustomTextureData> previous = cache.texture.data;

    // The cache notifies owners before it drops its own pixel buffer.
    listener.AssetUnloaded();
    cache.texture.data.reset();
    assert(previous.expired());
    assert(!resource.GetData());

    // An evicted texture must become pending again on its next draw.
    resource.Process();
    assert(cache.pending == 2);
    cache.texture.data = std::make_shared<CustomTextureData>();
    cache.texture.time = std::chrono::steady_clock::now();
    listener.NotifyAssetLoadSuccess();
    resource.Process();
    assert(resource.GetData() == cache.texture.data);
    assert(resource.GetLoadTime() == cache.texture.time);
}
''')
            executable = directory / "cache"
            subprocess.run(
                ["c++", "-std=c++20", "-I", str(directory), str(test),
                    str(directory / "VideoCommon/Resources/Resource.cpp"),
                    str(directory / "VideoCommon/Resources/TextureDataResource.cpp"),
                    "-o", str(executable)],
                check=True,
            )
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
