# Local super-resolution models

The pipeline runs Real-ESRGAN locally with PyTorch. It sends no game textures to
an API. Downloaded weights stay under ignored `build/` paths. SHA-256 checks run
before PyTorch opens a checkpoint. Checkpoints use `weights_only=True`.

## Sources

The official [Real-ESRGAN repository](https://github.com/xinntao/Real-ESRGAN)
publishes the weights and their inference code under BSD-3-Clause. The RRDB
architecture comes from BasicSR under Apache-2.0. Their license text is in
[MODEL_LICENSES.txt](MODEL_LICENSES.txt).

The compact network was adapted from
[`srvgg_arch.py` at a4abfb2](https://github.com/xinntao/Real-ESRGAN/blob/a4abfb2979a7bbff3f69f58f58ae324608821e27/realesrgan/archs/srvgg_arch.py).
The large network was adapted from
[`rrdbnet_arch.py` at 8d56e3a](https://github.com/XPixelGroup/BasicSR/blob/8d56e3a045f9fb3e1d8872f92ee4a4f07f886b0a/basicsr/archs/rrdbnet_arch.py).
The local code removes training setup and BasicSR's registry. It keeps the
checkpoint parameter names and inference operations.

| Method | Official checkpoint | Release | Purpose |
| --- | --- | --- | --- |
| `general` | `realesr-general-x4v3.pth` | [v0.2.5.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0) | Compact general image model with noise removal |
| `general-clean` | `realesr-general-wdn-x4v3.pth` | [v0.2.5.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0) | Compact general image model with weak noise removal |
| `anime` | `realesr-animevideov3.pth` | [v0.2.5.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0) | Compact anime video model |
| `esrgan` | `RealESRGAN_x4plus.pth` | [v0.1.0](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.1.0) | Large general image model |

All four networks produce 4x dimensions. A requested 2x result uses a Lanczos
reduction after inference. `lanczos`, `bicubic`, and `nearest` are named filters,
not AI models. `channels` uses bicubic filtering separately on all four channels
and preserves data values, including RGB values under zero alpha. Use it for
intensity and packed mask textures. The pinned hashes are in
[download_models.py](download_models.py).

## Run

```sh
python3 -m venv build/texture-upscale/venv
build/texture-upscale/venv/bin/python -m pip install -r tools/texture_upscale/requirements.txt
build/texture-upscale/venv/bin/python tools/texture_upscale/download_models.py --models general general-clean anime esrgan
build/texture-upscale/venv/bin/python tools/texture_upscale/upscale.py build/input.png build/output.png --method general --scale 4
build/texture-upscale/venv/bin/python -m unittest tools.tests.test_upscale -v
```

Keep one `Upscaler` instance for a batch to reuse the loaded networks. MPS runs
on supported Macs. CPU is the fallback. `--device mps` fails if MPS is unavailable,
so a requested GPU run cannot silently become a CPU run.

## Texture safety

The tool fills transparent RGB from the nearest visible texel before filtering.
It scales alpha separately with bicubic filtering. AI never changes the opacity
mask. This prevents hidden transparent colors from producing colored borders.
Empty textures remain empty. `nearest` also uses nearest filtering for alpha.

Pass `--wrap-s` and `--wrap-t` only for axes that use repeat sampling. Both RGB
and alpha receive pixels from the other edge before filtering. Use `--mirror-s` or `--mirror-t` for mirrored repeat. The default
clamps each edge. The Python API accepts GameCube sampler values 0, 1, and 2
for clamp, repeat, and mirror. The compact networks use a border equal to their full
convolution radius, so their tiles have complete context. The large `esrgan`
model uses a 32-pixel border to limit memory. Its much larger receptive field
means tile boundaries can differ from an untiled run.

Use a fixed method for each animation sequence. Deterministic filters are the
safe choice for font atlases, packed masks, and small effects because a color
model can invent marks or change them between frames. A deterministic network
still can infer different detail on two different source frames.

## Measured comparison

On an Apple M5 Max, a 192x160 image scaled to 768x640 took these times after
model loading and one warmup run. These are offline asset generation times,
not game frame times.

| Method | Time |
| --- | ---: |
| Lanczos | 3.4 ms |
| Anime video | 10.2 ms |
| General | 11.4 ms |
| General with weak noise removal | 11.3 ms |
| RealESRGAN_x4plus | 146.5 ms |

The large model processed all 36 decoded Fox textures in 2.90 seconds with a
384-pixel tile. MPS driver allocation was about 1.13 GiB. No model is required
when the game loads the resulting texture pack.

A visual comparison used Fox fur, eye, jacket, zipper and logo, plus Battlefield
metal, water, and fire textures. The anime model gave clean large shapes but
removed fine fur and metal lines. The general model also removed material grain.
The model with weak noise removal retained the grain. The large model gave the
best balance of sharper edges and material detail in this sample.

Six further comparisons covered menu text, menu art, and effects. AI made thin
lightning branches wider and added grain to smoke. Deterministic channel
filtering kept those shapes. No tested model repaired all source defects in the
small menu lettering. Clean font or logo replacements need separate work.

Use the large model for color assets where generated detail helps. Use channel
filtering for intensity, mask, and lookup textures, and keep each animation
sequence on one method. The weak noise removal model is an option when the large
model removes desired material grain. Review the result in motion. These sample
comparisons do not prove visual quality for every game texture.
