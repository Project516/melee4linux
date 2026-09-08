// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <algorithm>
#include <cstddef>
#include <filesystem>
#include <optional>
#include <string_view>

namespace MeleeTextures {
    // An explicit path takes priority, including when it is invalid. A typo
    // must not silently select a different pack during a comparison.
    inline std::optional<std::filesystem::path>
    FindPackRoot(std::string_view explicit_root, std::string_view bundle_root)
    {
        std::filesystem::path root;
        if (!explicit_root.empty()) {
            root = explicit_root;
        } else if (!bundle_root.empty()) {
            root = std::filesystem::path(bundle_root) / "Contents" /
                   "Resources" / "Textures";
        } else {
            return std::nullopt;
        }
        std::error_code error;
        if (!std::filesystem::is_directory(root / "GALE01", error)) {
            return std::nullopt;
        }
        return root;
    }

    // CPU pixels share physical memory with Metal textures on Apple Silicon.
    inline std::size_t CacheBudget(std::size_t physical_memory)
    {
        return std::min(physical_memory / 8, std::size_t{ 512 } * 1024 * 1024);
    }
}
