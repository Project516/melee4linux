# Texture pass on 2026-09-08

The `native/texture-upscale` branch is based on `master` after the macOS port
merged. It keeps the 120 FPS work and adds a full static texture pass.

The source and tools are in
[melee4mac](https://github.com/t3dotgg/melee4mac/tree/native/texture-upscale).
The generated artwork is in the private
[melee4mac-textures repository](https://github.com/t3dotgg/melee4mac-textures).
The source fork stays public. Generated PNG archives use Git LFS. No game image,
original archive, game executable, save, or model checkpoint is uploaded.

## Result

| Assets | Output |
| --- | --- |
| 7,742 color texture variants | RealESRGAN_x4plus at 4x width and height |
| 5,093 masks, glyphs, effects, and small textures | Channel-preserving filtering at 4x |
| 75 ending stills | 2240 × 1664 RGB images and 225 full-resolution YUV planes |
| Every replacement | Complete mip chain, original alpha rules, lossless RGBA8 DDS |

There are 12,835 regular texture variants and 13,060 loadable replacements
including the ending planes. The generated PNGs total about 2.23 GB. The
loadable DDS pack is about 14.28 GB. DDS files are built locally from the
smaller private PNG download.

The app loads textures as needed on background workers. It keeps the CPU
pixel cache within 512 MiB, plus current worker allocations. The texture
cache now releases decoded pixels when it evicts an asset. The pack enables
16x anisotropy and retains per-texture filtering choices. Full-resolution
chroma makes the ending stills sharper without changing their YUV shader.

## Method choice

Comparisons covered nearest, bicubic, Lanczos, the compact RealESRGAN general
models, the anime model, and the full RealESRGAN_x4plus model. Six FAL Clarity
trials used two creativity settings on Fox's eye, fur, and Battlefield metal.

The full RealESRGAN model gave the best balance of sharper edges and useful
material detail. Clarity invented crosswise marks in fur and fuzzy eyelashes.
The anime model removed too much fine texture. Image-generation results were
kept as comparisons and excluded from the pack. The FAL trial reserved
$1.50 within the approved $10 limit. Its ledger contains each prompt, seed,
request ID, and model price.

Intensity textures and effects need different treatment. AI widened lightning
branches and added grain to smoke. Very small inputs also produced invented
structures. The pipeline therefore filters these channels directly and
keeps color AI away from inputs with an edge of 16 pixels or less. Character
portraits and other color animation tables still use RealESRGAN.

## Coverage

The inventory parsed all 894 DAT and USD files, including their nested HSD
archives. It covers images, linked palettes, animation tables, particle
banks, 4,733 glyph references, the banner, and executable texture data.
There are 56,034 source references and 427 original mip levels.

The pass inspected every disc file. The 28 MTH movies remain video assets
outside the texture pack. The manifest reports 16 unusual animation tracks
with conservative palette combinations and one invalid palette pointer in
the original Kirby Samus effect bank. Counts describe extracted variants,
including variants that may not appear during ordinary play.

Visual review found 600 unused Pokemon Stadium TV palette combinations. A
fix to terminal animation-key handling removed them. The corrected pack
contains no obsolete files from those candidates.

## Validation

All 12,835 regular outputs passed checks for dimensions, file hashes, base
PNG versus DDS pixels, complete mip chains, alpha, and equal data channels.
All 75 ending PNGs and 225 ending DDS planes passed equivalent checks.
Review covered 108 sampled texture pairs and the 24 largest measured changes.

An independent check linked Dolphin's actual decoder objects. It compared
57 base textures across all 10 formats and seven mip levels. Every decoded
RGBA byte and replacement name matched the extractor.

The native app loaded the replacement pack in a Mario versus Peach match
on Yoshi's Island. GPU upload records confirmed the larger dimensions and
mip counts. A warm 25-second sample at 4x internal resolution measured
119.99 rendered FPS and about 60 simulation updates per second. Disabling
the pack returned to the original textures and also measured 119.99 FPS.
Some runs on the 60 Hz display were limited to 60 presentations per second
and slowed the experimental 120 FPS simulation. The app now selects 60 FPS
when macOS reports a display below 119 Hz, with or without vertical sync.
120 Hz displays retain the 120 FPS mode. The final 60 Hz display test checks
normal game speed rather than treating an unsupported refresh rate as a target.
The rebuilt self-contained app measured 59.99 rendered FPS and about 60
simulation updates per second on this display with the pack enabled.

The ending test used an isolated RAM-only debug route into Mario's Classic
ending. The app uploaded all three planes at 2240 × 1664 and displayed the
expected image. Tests used an M5 Max, macOS 26.5.2, and a 4K 60 Hz monitor.
This verifies rendering throughput, not 120 complete visible refreshes on
that monitor. Every stage and costume has asset coverage, but complete
gameplay through every combination has not been tested.

The matching GameCube executable still has SHA-1
`08e0bf20134dfcb260699671004527b2d6bb1a45`. Native packaging and signature
verification pass. The checks include 46 native tests, 39 extraction tests,
23 upscaler and audit tests, and three timing tests. Source and style checks
pass. The private asset repository passes Git LFS integrity checks.

Use the [texture build guide](../tools/texture_upscale/README.md) to repeat
the complete extraction, model run, DDS conversion, and audit with one command.
