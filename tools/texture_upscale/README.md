# Texture upscaling

This branch extracts textures from Melee USA v1.02, restores color detail with
local RealESRGAN, and builds replacement textures for the native Mac app.
It also restores the 75 ending stills with full-resolution YUV color planes.
The original disc and matching executable stay unchanged.

The generated artwork is stored separately in the private
[melee4mac-textures repository](https://github.com/t3dotgg/melee4mac-textures).
Only generated PNGs and their records belong there. The source repository
contains the extraction, conversion, and validation tools. The full DDS pack
is rebuilt locally from the smaller PNG files stored in ZIP archives.

## Build the whole pack

First build the native app using `native/macos/build.py`. It extracts the
local disc into `build/native/recomp/private/GALE01r2`.

```sh
python3 -m venv build/texture-upscale/venv
build/texture-upscale/venv/bin/python -m pip install -r tools/texture_upscale/requirements.txt
build/texture-upscale/venv/bin/python -m tools.texture_upscale.build_pack \
  --disc build/native/recomp/private/GALE01r2
```

The complete command downloads verified model weights, extracts every texture,
processes regular textures and ending stills, and runs the full output audit.
The individual steps are also available:

```sh
build/texture-upscale/venv/bin/python tools/texture_upscale/download_models.py --models esrgan
build/texture-upscale/venv/bin/python -m tools.texture_upscale.extract \
  --files build/native/recomp/private/GALE01r2/files \
  --dol build/native/recomp/private/GALE01r2/sys/main.dol \
  --output build/texture-upscale/extracted
build/texture-upscale/venv/bin/python tools/texture_upscale/pipeline.py \
  --manifest build/texture-upscale/extracted/manifest.json \
  --models build/texture-upscale/models --output build/texture-upscale/pack
build/texture-upscale/venv/bin/python tools/texture_upscale/upscale_stills.py \
  --disc-files build/native/recomp/private/GALE01r2/files \
  --models build/texture-upscale/models --output build/texture-upscale/pack
build/texture-upscale/venv/bin/python tools/texture_upscale/quality_report.py \
  --manifest build/texture-upscale/extracted/manifest.json \
  --pack build/texture-upscale/pack --output build/texture-upscale/quality
```

The regular texture pass resumes from per-texture records. It verifies file
hashes before reusing an output. Failed files remain visible in `summary.json`.
`--prune` moves obsolete generated candidates into `unused-candidates` if a
later extraction removes unused palette combinations.

The output has 4x width and height. A 128 × 128 texture becomes 512 × 512.
Color assets use RealESRGAN_x4plus. Fonts, intensity channels, particles,
effect banks, and textures with an edge of 16 pixels or less use independent
channel filtering. That keeps masks intact and avoids inventing structures
from very small inputs. Color animation tables, including character portraits
and blinking eyes, use the same fixed model for every frame.

The upscaler pads repeat and mirrored textures with their correct sampler
context. It restores hidden RGB near transparent edges and scales alpha
separately. AI does not generate alpha. DDS mipmaps use linear-light,
alpha-weighted color filtering. Data textures keep channel relationships
through all mip levels. The pack uses lossless RGBA8 DDS for broad Metal
support. No image model runs during gameplay.

## Load the pack

For local comparisons with an existing build:

```sh
MELEE_TEXTURE_PACK="$PWD/build/texture-upscale/pack/Textures" \
  native/macos/run.sh "build/native/Melee for Mac.app"
```

To make a self-contained app:

```sh
python native/macos/build.py --iso '/path/to/Melee.iso' \
  --texture-pack build/texture-upscale/pack/Textures \
  --output 'build/native/Melee Upscaled.app'
```

Settings, Textures turns replacements on or off on the next launch. The app
uses 60 FPS on detected displays below 119 Hz so display limits cannot slow
the game. Displays at 120 Hz or above retain 120 FPS rendering.
`MELEE_TEXTURES=0` disables them for a baseline comparison. Optional
`MELEE_TEXTURE_LOG=/absolute/path/uploads.tsv` records replacements that
actually reached the GPU, including their dimensions and mip levels.

The private generated PNG repository can recreate the loadable pack without
running AI again:

```sh
git lfs pull
python /path/to/melee4mac/tools/texture_upscale/restore_pack.py \
  --assets . --output /path/to/melee4mac/build/texture-pack
```

## Coverage and checks

Extraction reads relocation-backed HSD images, linked palettes, texture
animation tables, particle banks, SIS and executable fonts, TPL containers,
the banner, and supported ending stills. Each file has a coverage record.
Unsupported animation tracks retain conservative palette candidates and
report a warning. The 28 MTH movies remain video assets and are outside this
texture replacement pack.

The quality report checks every generated texture, including dimensions,
checksums, base PNG versus DDS pixels, full mip chains, alpha, and equal data
channels. Contact sheets cover characters, stages, menu art, HUD, effects,
items, trophies, fonts, and large color changes. A clean report does not
replace visual review in the game.

See [model sources and comparisons](MODELS.md) and the
[runtime integration notes](../../native/macos/textures/README.md).

## FAL comparison

The separate `compare_fal.py` tool runs small, budgeted Clarity samples. It
requires explicit API authorization and reads `FAL_KEY` from an ignored
`.env` file or the environment. It records the prompt, seed, request ID,
model price, output, and reserved cost. It does not retry failed submissions.

The tested Clarity settings were 4x scale, creativity 0.15 and 0.35,
resemblance 1.0, guidance 4, 18 steps, and seed 20260908. Both added detail
that did not belong in the texture, such as crosswise marks in fur and fuzzy
eyelashes. The pack uses local RealESRGAN instead. Six comparison requests
reserved $1.50 within the approved $10 cap. This is the tool's cost reserve,
not an account billing statement.
