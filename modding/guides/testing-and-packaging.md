# 6 · Test and share patches

[Creator kit](../README.md)

## Test the change you made

Run the included checks from WORK:

```sh
python3 -B -m unittest discover -s tools -p 'test_*.py'
```

Some optional historical-intermediate checks skip; inspect the skip messages.
Host C++ memory harnesses require `c++`. These tests do not emulate the whole
game or establish hardware/performance compatibility.

For a new slot/model, inspect selection on both sides, new-vs-retail and
new-vs-new pairings, sidekick combinations, HUD/loading/winner presentation,
real animations, goal/save/replay, and returning to menus. For stadium changes,
inspect both goals and entrances, upper stands during camera movement, boundaries
and ball collisions. Record what you actually tested.

## Package the current stage

Stage/rebuild **before** direct creator edits. Direct name/badge changes affect
the current stage and are lost when staging again; package after applying them.
Close Dolphin before replacing a stage.

From the public repo, with [uv](https://docs.astral.sh/uv/) installed:

```sh
uv run --with bsdiff4==1.2.6 python modding/creator.py --workspace "/path/to/strikers-work" package --release "my-club-v0.1" --output "/path/to/my-club-package"
```

Alternatively install that pinned dependency in your own virtual environment.
`bsdiff4` is only for **generating** patches; consumers use standard Python.
Choose a new package folder outside WORK. The tool compares the staged `sys/`
and `files/` against clean retail files, creates and round-trip-verifies BSDIFF40
patches, inventories outputs and copies the dependency-free installer/notices.
It does not copy debug logs, Blender data or complete game files.

For additional native files (another roster slot), create
`WORK/package-donors.json` mapping each new target to an existing clean retail
donor. Existing Palmeiras/Human mappings are supplied automatically. Example:

```json
{
  "files/art/characters/MyClub/MyClub.glg": "files/art/characters/Daisy/Daisy.glg",
  "files/art/characters/MyClub/MyClub_blend.glg": "files/art/characters/Daisy/Daisy_blend.glg",
  "files/art/characters/MyClub/MyClub.glt": "files/art/characters/Daisy/Daisy.glt"
}
```

Deleting retail files is not supported by this installer format. If packaging
fails, inspect its partial output and retry with a new folder. The generated
README is deliberately minimal: add your mod description, credits, license
boundaries and honest testing notes before sharing.

## Verify what another person receives

From your generated package:

```sh
python3 install.py install --source "/path/to/clean-game" --output "/path/to/fresh-custom-game"
python3 install.py verify --game "/path/to/fresh-custom-game"
python3 install.py run --game "/path/to/fresh-custom-game" --dolphin "/path/to/dolphin-emu"
```

Archive only that package and publish a SHA-256 checksum. Keep your source fork,
authored art and corresponding licensing/credits available as appropriate.
Do not upload your source game, installed game, SDK/compiler binaries, saves or
private credentials. Calling a binary difference a patch does not relicense
Nintendo/club/third-party content. No claim of original-hardware support follows
from a successful Dolphin build.
