# Native texture packs

The app reads replacements from `Contents/Resources/Textures/GALE01`. The
`MELEE_TEXTURE_PACK` environment variable selects a different root directory
that contains `GALE01`. An invalid explicit path disables replacements. It
does not fall back to the bundled pack. This makes comparisons repeatable.

Settings has a Textures tab. Its switch applies on the next launch.
`MELEE_TEXTURES=0` or `MELEE_TEXTURES=1` overrides that switch for a local test.

The native build uses Dolphin's existing texture hashes and background asset
workers. It loads textures when the game requests them. It does not preload
the whole pack. The CPU pixel cache uses at most 512 MiB or one eighth of
physical RAM, whichever is smaller. Two worker threads can temporarily exceed
this limit by their current assets. GPU textures and file buffers use
additional memory.

`texture-cache.patch` fixes an eviction bug in `TextureDataResource`. The
resource kept a shared pixel buffer after the asset cache reported it freed.
The patch drops that owner and resets the load state. The next draw can
request the asset again. Existing GPU cache entries can still use their
uploaded texture.

Packs use 16x anisotropic filtering. The original per-texture filtering rules
still protect textures that use point filtering. Full DDS mip chains reduce
shimmer on distant objects. PNG textures can use separate `_mip1.png`, `_mip2.png`, and later files.
Production packs use DDS to keep the complete chain in one file. The
legacy RGBA8 DDS masks are R `0x000000ff`, G `0x0000ff00`, B `0x00ff0000`,
and A `0xff000000`. This format preserves colors and alpha without block
compression. The runtime also supports BC7 DDS files.

For local verification, set `MELEE_TEXTURE_LOG` to a writable TSV path. Each
row records an actual GPU upload, with the texture name, width, height, and
mip count. Reloads can produce repeated rows. This capture is off by default.
It writes only to the requested path. The startup log also reports the number
of replacement names found.

Run the path and memory policy tests with:

```sh
python3 -m unittest native/macos/tests/test_texture_pack.py
```

The eviction test compiles the real patched Dolphin resource source with a
small fake asset store. It checks pixel ownership and the reload state:

```sh
MELEE_TEST_DOLPHIN_SOURCE=build/native/recomp/upstream/ModernGekko-Template/lib/ModernGekko/vendor/dolphin/Source/Core \
  python3 -m unittest native/macos/tests/test_texture_cache.py
```

The test failed on the original resource code because its pixel buffer stayed
alive after eviction. It passed with the patch. All five edited translation
units compiled with the native runtime's ARM64 flags. These checks do not
replace a full app build or visual tests with the finished asset pack.

## Ending stills

`ending-stills.patch` adds aliases for the 75 `GmRegend*.thp` ending pictures.
These files are JPEG stills. They use a different descriptor from the MTH
movies. The hook checks Melee USA v1.02, native mode, the exact 560 by 416
image dimensions, live YUV plane addresses, and valid guest memory ranges.
It changes no game memory or drawing code.

The alias contains XXH64 of the complete original compressed file and the
plane letter. For example, `tex1_still_<16 hex digits>_y.dds`. This avoids
hash differences between JPEG decoders. All three planes can use the full
upscaled image dimensions. The game keeps its YUV conversion shader.

After the 75 RGB stills are upscaled, build their planes with:

```sh
python tools/texture_upscale/still_planes.py \
  --disc-files build/disc/files --upscaled build/upscaled-stills \
  --output build/texture-pack/GALE01/ending-stills
```

The tool writes a manifest with each original filename and every output
hash. It replicates each intensity into all RGBA channels. The alpha channel
is required for the game's green calculation. Plane mipmaps use data-channel
averaging. The conversion keeps full chroma resolution. Its RGB round-trip
error in the focused color test is at most four channel values, with mean
error below 1.5. This test does not measure the game's TEV rounding.

The optional hook compiles with the native runtime's ARM64 flags. Descriptor
checks cover wrong dimensions, reused addresses, short descriptors, and
out-of-range source data. An actual ending screen still needs visual testing
in the built app before claiming coverage in gameplay.

## Display pacing

The native app uses 60 FPS when macOS reports a display below 119 Hz, even
with vertical sync off. The one Hz tolerance includes common 119.88 Hz modes.
On this Mac's 60 Hz display, the compositor sometimes limited a requested
120 FPS session to 60 presentations per second. The experimental game loop
then ran only 30 simulation updates per second. Low GPU times showed that
texture throughput was not the limit in that capture.

The display limit keeps the game at normal speed on these displays. Displays
at 120 Hz or above can use 120 FPS. A refresh value of zero means macOS did
not report a fixed rate, so the requested rate remains in effect. The app
uses the main display's rate at launch. Moving it to another display does not
change that rate until the next launch.
