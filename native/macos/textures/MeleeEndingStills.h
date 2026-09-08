// SPDX-License-Identifier: GPL-3.0-or-later
#pragma once

#include <cstdint>
#include <optional>
#include <span>

namespace MeleeTextures {
    struct EndingPlane {
        char channel;
        std::uint32_t source_address;
        std::uint32_t source_size;
    };

    // lb_01F8.c owns this descriptor at 0x804335B8 in Melee USA v1.02.
    // Match all dimensions and the live plane address. Movies use another
    // descriptor and cannot match these addresses.
    inline std::optional<EndingPlane>
    MatchEndingPlane(std::span<const unsigned char> descriptor,
                     std::uint32_t texture_address, std::uint32_t width,
                     std::uint32_t height)
    {
        if (descriptor.size() < 0xA0) {
            return std::nullopt;
        }
        const auto read32 = [&](std::size_t offset) {
            return (std::uint32_t{ descriptor[offset] } << 24) |
                   (std::uint32_t{ descriptor[offset + 1] } << 16) |
                   (std::uint32_t{ descriptor[offset + 2] } << 8) |
                   std::uint32_t{ descriptor[offset + 3] };
        };
        // The ending stills are 560 by 416. Other uses remain unchanged.
        if (read32(0x6C) != ((560u << 16) | 416u)) {
            return std::nullopt;
        }
        const std::uint32_t source = read32(0x94);
        const std::uint32_t size = read32(0x98);
        if (source < 0x80000000 || source >= 0x81800000 || size < 4 ||
            size > 4 * 1024 * 1024 || size > 0x81800000 - source)
        {
            return std::nullopt;
        }
        for (unsigned int plane = 0; plane < 3; ++plane) {
            const auto address = read32(0x20 + plane * 0x24);
            const bool dimensions_match = plane == 0
                                              ? width == 560 && height == 416
                                              : width == 280 && height == 208;
            if (dimensions_match && address >= 0x80000000 &&
                address < 0x81800000 &&
                (address & 0x01FFFFFF) == texture_address)
            {
                return EndingPlane{ "yuv"[plane], source, size };
            }
        }
        return std::nullopt;
    }
}
