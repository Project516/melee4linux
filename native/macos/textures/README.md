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
shimmer on distant objects. The PNG loader in this runtime reads only one
level, so production packs should use DDS files with all mip levels. The
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
