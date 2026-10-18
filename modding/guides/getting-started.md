# 1 · Set up an editable workspace

[Creator kit](../README.md) · [Next: roster edits →](captain-and-sidekick.md)

## Prerequisites

Install Python **3.11+**, Git, Ninja and ImageMagick 7 (`magick`). A host C++
compiler is needed for the optional native-memory regression harnesses.
Use a supported upstream compiler-wrapper environment; the tested creator host
is Linux x86_64. Windows/macOS builds follow upstream's platform requirements
and are not independently tested here.

Clone/download **this repository's current main**, not just the older v1.0.0
playable ZIP. Install v1.0.0 with the normal installer first. You need:

- `CLEAN`: the unmodified USA Rev 0 extraction.
- `GAME`: the installed and hash-verified v1.0.0 game.
- `WORK`: a new development folder, outside both game folders and this public
  repository. Its parent must exist.

From this public repository, run (substitute real absolute paths):

```sh
python3 modding/create_workspace.py --clean "/path/to/clean-game" --installed "/path/to/game" --workspace "/path/to/strikers-work"
```

The bootstrap verifies both game inputs, clones upstream at
`d1f357ffeb1d8e89311edebf9a4b304b05ece7bb`, initializes its submodules, checks and
applies the source diff, and installs the creator overlay. It copies clean
`sys/` and `files/` into `WORK/orig/G4QE01/`. It also reconstructs:

- `WORK/build/palmeiras/human-meshy-image-v1-export/Daisy{,_blend}.glg` and
  `Daisy.glt`: verified native export donors recovered from your installed mod.
- Ten editable PNGs under `WORK/mods/palmeiras/assets/work/native-reference/`.

These PNGs are decoded from the game's quantized native textures, not recovered
original paint masters. Re-encoding can change palette/mip details. This is an
editable starting point, not a promise that all UI bundles rebuild byte-identically.
The source patch/build should reproduce the published executable.

No `.blend`, original 2K texture or paid generation request is needed. Nothing
is fetched from a model generator. Bootstrap never copies your saves/controls.
A failed new workspace is retained for diagnosis; retry with a fresh folder.

## Build once

In `WORK`, first let upstream generate/download its pinned build tools:

```sh
python3 configure.py --version G4QE01 --non-matching --map --build-dir build/combined
ninja build/combined/G4QE01/main.dol
python3 tools/combined_mod.py stage
```

Tool downloads happen through upstream's build system and require network
access. See its `README.md` / `docs/getting_started.md` for wrapper/compiler
prerequisites. No compiler/SDK binaries are hosted in this kit. Repeat these
configure/Ninja commands for later C++ rebuilds; use only the stage command when
editing artwork or formations. The historical `combined_mod.py build/prepare`
shortcuts expect a separate shared `build/tools` cache, so they are not the
fresh-workspace build route documented here.

The boot target is `WORK/build/combined/disc/sys/main.dol`. Staging always starts
from clean retail files; earlier stages are archived under `build/combined/archive`.
Close Dolphin before restaging. Do not stage an already enlarged Palace again.

## Test and launch

```sh
# Run from WORK; some tests intentionally skip if their optional inputs are absent.
python3 -B -m unittest discover -s tools -p 'test_*.py'
```

From the **public repository**, launch your custom stage with:

```sh
python3 modding/creator.py --workspace "/path/to/strikers-work" run --dolphin "/path/to/dolphin-emu"
```

This creates/uses the workspace's own Dolphin profile and enforces 48 MiB MEM1.
The release `install.py run` checks v1.0.0 hashes and will correctly reject a
custom build; use this creator launcher instead.
