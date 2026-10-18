# 3 · Artwork without broken native resources

[Creator kit](../README.md) · [Models →](custom-models.md)

## A small, working badge edit

From the public repository, rasterize the original generic template:

```sh
magick modding/templates/artwork/banner.svg "/path/to/banner.png"
python3 modding/creator.py --workspace "/path/to/strikers-work" badge --png "/path/to/banner.png"
```

This repacks the staged permanent badge and async captain banner resources in
four bundles. It does not rebuild C++ or call a generator. Check the nameplate
and selection/loading transitions using the creator launcher.

For persistent edits, save the PNG over the workspace's recovered
`native-reference/captain_icons_PALMEIRAS_256x64.png`; subsequent stages use it.
Or change `ART` paths in `tools/palmeiras_team.py` to your own named inputs.

## Full input map

All paths below are relative to `WORK/mods/palmeiras/assets/work/native-reference/`:

| PNG | Dimensions | Purpose |
| --- | --- | --- |
| `grid_captain_PALMEIRAS_128x128.png` | 128×128 | Captain grid crest |
| `captain_icons_PALMEIRAS_256x64.png` | 256×64 | Header/nameplate and async banner |
| `loadingscreen_PALMEIRAS_l_256x256.png` | 256×256 | Main loading/winner art |
| `loadingscreen_PALMEIRAS_l_bg_256x256.png` | 256×256 | Outline/background variant |
| `loadingscreen_PALMEIRAS_l_white_256x256.png` | 256×256 | White variant |
| `loadingscreen_PALMEIRAS_r_256x256.png` | 256×256 | Right-side main art |
| `cup_loadingscreen_PALMEIRAS_l_256x256.png` | 256×256 | Cup/supercup main art |
| `grid_sidekick_Human_128x128.png` | 128×128 | Human selector |
| `cup_sidekick_HUMAN_PALMEIRAS_l_256x256.png` | 256×256 | Human loading art |
| `cup_sidekick_HUMAN_PALMEIRAS_l_bg_128x128.png` | 128×128 | Human background |

After editing, run `python3 tools/combined_mod.py stage` **inside WORK**.
Captain missing right-side masks reuse their left versions rather than mirror
lettering. Human right variants are mirrored. Inspect the derived screens.
The green Human kit remains fixed regardless of captain choice.

## Preserve the native contract

PNG dimensions and padding matter. A full-bleed logo can look much larger than
a character portrait on the same canvas. Start with recovered PNGs or the
generic transparent [templates](../templates/artwork/README.md).

Native `.fen`, `.res`, `.dmn`, `.glt` are not paint files. The provided staging
tools re-encode art to RGB5A3 or each CI8 template's exact dimensions, palette,
mip count, tile swizzle and allocation size. Async texture replacement cannot
silently grow an allocation or change its format. Do not paste PNG bytes into
native bundles, change compressed payload sizes in place or reuse another
resource's hash accidentally.

FEN is a relocated object graph, not a flat list of pictures. Cloned image,
resource, instance and animation objects require valid ownership and pointer
tables. The `Fen`/`HumanFen` helpers preserve these relationships and Bezier
sentinels. New roster entries need their own corresponding resource aliases;
painting a crest is not enough to create a selectable slot.
