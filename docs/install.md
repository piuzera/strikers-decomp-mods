# Installation & FAQ

[← Project home](../README.md) · [Windows](windows.md) · [Linux](linux.md) · [macOS](macos.md)

## Requirements

- Your own unmodified **USA Rev 0 / G4QE01** copy of Super Mario Strikers.
- **Python 3.10+**, a current [Dolphin](https://dolphin-emu.org/) desktop release,
  and about **1 GiB free** for the installed game and temporary files.
- The [v1.0.0 release ZIP](https://github.com/piuzera/strikers-decomp-mods/releases/latest).

Playing does not require a compiler, Blender or Python packages.

## Install and launch

1. Add your game dump to Dolphin. Right-click it → **Properties → Filesystem** →
   right-click the disc root → **Extract Entire Disc** into `clean-game`.
   That folder must contain `sys/main.dol` and `files/` directly.
2. Extract the release ZIP and open a terminal there. Install into a new folder
   **outside** the clean extraction:

   ```sh
   python3 install.py install --source "/path/to/clean-game" --output "/path/to/game"
   ```

3. Launch through the memory-aware launcher:

   ```sh
   python3 install.py run --game "/path/to/game" --dolphin "/path/to/dolphin-emu"
   ```

On Windows use `py -3` instead of `python3`. Quote paths containing spaces.
The output's parent folder must exist; an existing output is never overwritten.
The installer validates inputs, leaves the extraction untouched, and verifies
every installed file. To verify later:

```sh
python3 install.py verify --game "/path/to/game"
```

## Controls, saves and memory

The launcher creates `game-dolphin-user` beside your installed game. Configure
Controllers on the first launch; later runs preserve that profile's controls
and saves. Your normal Dolphin profile is not imported or modified.

Use the launcher for every session: the mod requires **48 MiB MEM1**, rather than
the retail 24 MiB. Booting it from an ordinary Dolphin profile can fail to load.
The release does not force-unlock trophies. Palmeiras, Human and The Palace do
not require the former development unlock flag; retail progression otherwise applies.

## Compatibility

**Supported version:** unmodified North American USA Rev 0. Original
`sys/main.dol` SHA-1: `376d699c99b6b0949abe1b4ceccefdef7828d2b5`.
Other regions, revisions and already-modded inputs are rejected. Extract ISO/RVZ
with Dolphin first; this installer does not patch disc images directly.

**Original hardware:** the current combined build cannot run within GameCube's
24 MiB main RAM requirement. Wii/Wii U through Nintendont is unsupported and
untested; extra Wii memory does not automatically provide Dolphin's contiguous
48 MiB MEM1 layout. A hardware port would require separate engineering work.
None is planned.

**Desktop platforms:** clean installation is tested on Linux. Windows/macOS
instructions are included, but those platforms have not been independently
tested for this release.

**Verification:** the final combined gameplay, replays, optimized Human and
Palace fix were user-confirmed in Dolphin. The release installer reconstructed
all 1,427 game files from clean inputs. Removing the unlock flag was checked
in source/artifacts, not re-playtested with a blank save after packaging.
See [release notes](../RELEASE_NOTES.md).

**ISO rebuilding / other mods:** the supported output is an extracted game
booted via `sys/main.dol`. ISO rebuilding and combinations with other patches
are not provided or tested. Share patch packages, not installed game folders.

**I want to edit the game:** the release installer's `verify`/`run` intentionally
check the published hashes. Use the [creator workflow](../modding/README.md)
for custom builds instead of weakening those checks.
