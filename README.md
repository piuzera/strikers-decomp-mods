# Strikers decomp mods

A completed, spare-time proof of concept for **Super Mario Strikers**: 11-a-side
football, a larger Palace, an independent Palmeiras captain and a Human sidekick.

**Completed / as-is.** This was a fun project made in my spare time. The final
combined build and Palace polish were confirmed working in Dolphin. No further
updates, support or hardware port are planned. Forks and experiments are welcome.
The repository remains unarchived; issue tracking is disabled.

## Download and install

Download and extract the ZIP from [Releases](https://github.com/piuzera/strikers-decomp-mods/releases/latest).
The release contains **patches**, an installer and documentation. Supply your own
unmodified **USA Rev 0 / G4QE01** game. No game download is provided.

You need **Python 3.10+**, a current [Dolphin](https://dolphin-emu.org/) desktop
release and about **1 GiB of free space** for the installed game and temporary
files. No compiler, Blender, Python packages or model-generation tools are needed.

1. Add your game dump to Dolphin's game list. Right-click it → **Properties** →
   **Filesystem** → right-click the disc root → **Extract Entire Disc**.
   Choose a new folder, such as `clean-game`. The result must contain
   `sys/main.dol` and `files/` directly under that folder.
2. Open a terminal in the extracted release folder. Install into a **new folder
   outside the clean extraction**:

   ```sh
   python3 install.py install --source "/path/to/clean-game" --output "/path/to/game"
   ```

   On Windows, use `py -3` in place of `python3`. All paths with spaces must be quoted.
3. Launch with the required **48 MiB MEM1** override:

   ```sh
   python3 install.py run --game "/path/to/game" --dolphin "/path/to/dolphin-emu"
   ```

   The launcher uses a separate `game-dolphin-user` profile beside the installed
   game. Configure your controller in Dolphin on the first launch. Later launches
   preserve that profile's controls and saves. Your normal Dolphin profile is not
   imported. Avoid booting the mod through a default 24 MiB profile.

Platform instructions: **[Windows](docs/windows.md)** · **[Linux](docs/linux.md)** ·
**[macOS](docs/macos.md)**.

The installer checks the clean extraction and patch hashes before installation,
leaves your input untouched and verifies every installed file. It refuses to
overwrite an existing output. You can verify again with:

```sh
python3 install.py verify --game "/path/to/game"
```

## The mods

These features ship as **one combined package**, not independently installable mods.

### 11-a-side

Start a match normally. Each team has one captain, nine sidekicks and one
goalkeeper: 22 players total. Expanded formations, gameplay camera and replay
paths are included. Characters use lightweight blob shadows.

### Enlarged Palace

Select **The Palace**. Its pitch is twice the original length and width, with
matching field boundaries, goal placement and camera tracking. The surrounding
stadium has corrected goal-area terrain, connected stands and enlarged visibility
bounds. Other stadiums retain their original dimensions.

### Palmeiras captain

Choose **Palmeiras** in the captain grid. It is a separate tenth team; the retail
captains remain selectable. The green-kit human uses Daisy-compatible gameplay
and animations with Luigi audio. Custom crest, selection, loading and HUD artwork
are included.

### Human sidekick

Choose **Human** in the centered bottom sidekick slot. It is a fifth choice and
can be used independently of the captain. Select Palmeiras + Human for ten human
outfielders. Human wears the same fixed green kit for every captain.

The release does **not** force-unlock trophies or edit save progression. The
custom captain/sidekick and Palace selection do not need the development unlock
override. Existing retail progression rules otherwise apply.

## Compatibility and FAQ

**Which game version?** Only the unmodified North American USA Rev 0 release,
`G4QE01`. Its original `sys/main.dol` SHA-1 is
`376d699c99b6b0949abe1b4ceccefdef7828d2b5`. European/Japanese releases and
already-modded extractions are rejected. ISO/RVZ dumps are extracted using Dolphin;
the installer operates on extracted files, not directly on disc images.

**Does it work on GameCube or Nintendont?** This release targets Dolphin and
requires **48 MiB MEM1**. Original GameCube hardware has 24 MiB main RAM and is not
supported by this build. Wii/Wii U through Nintendont is unsupported and untested:
extra Wii memory does not automatically provide Dolphin's expanded MEM1 layout.
A hardware version would require separate memory/porting work. None is planned.

**Does the installer work on every desktop OS?** It uses only Python's standard
library and includes Windows, Linux and macOS instructions. End-to-end installation
is tested on Linux. Windows and macOS installation and gameplay have not been
independently tested for this release. Dolphin itself must run on your computer.

**What has been tested?** The author confirmed the combined gameplay, replays,
optimized Human model and final Palace correction in Dolphin. Host/artifact tests
passed in development. The public patch installer is checked by reconstructing the
entire game folder from a clean extraction and comparing its output hashes.
This is a proof of concept, not exhaustive validation of every mode or Dolphin
version. The release removes the development unlock flag; menu availability has
been checked in source, not re-playtested with a blank save after packaging.

**Can I build an ISO, use other patches or distribute the installed game?** The
supported output is an extracted game booted through `sys/main.dol` in Dolphin.
ISO rebuilding and combinations with other mods are not provided or tested.
Distribute this patch package, not your source extraction or installed game.

## Credits and license

- [piuzera](https://github.com/piuzera): spare-time mod project and release.
- [Super Mario Strikers decompilation](https://github.com/yannicksuter/smstrikers-decomp)
  and its contributors: the source-reconstruction foundation that made the mod possible.
- Nintendo / Next Level Games: original game.
- Dolphin contributors: emulator.
- The custom Human was generated from approved reference artwork using Meshy v6
  through fal.ai, then optimized and fitted locally. Blender sources and private
  generation inputs are not part of this release.

The original installer, tests and documentation are **MIT licensed**; see
[LICENSE](LICENSE). Patches and the resulting game contain or transform
third-party/game-derived material, which is **not relicensed under MIT**.
Game/club names and marks belong to their respective owners. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). This is an unofficial fan project,
not affiliated with or endorsed by Nintendo, Next Level Games or Palmeiras.
