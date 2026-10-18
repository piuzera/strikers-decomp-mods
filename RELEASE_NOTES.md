# v1.0.0 — completed proof of concept

Final combined release of the spare-time Strikers mod project:

- 11-a-side teams and expanded formations/replay paths.
- Twice-length/width Palace pitch, corrected goal-area terrain, connected stands
  and geometry visibility bounds.
- Independent Palmeiras captain and fifth selectable Human sidekick.
- Fixed green human kit, custom selection/loading/HUD resources and Luigi audio.
- Normal retail progression; the development all-trophies override is removed.

## Installation

Download `strikers-decomp-mods-v1.0.0.zip` and follow the included README.
`SHA256SUMS.txt` identifies the release archive. Supply your own unmodified
USA Rev 0 / G4QE01 extraction. The package contains 43 BSDIFF40 patches, not a
complete game. Python 3.10+ and Dolphin are required; no pip packages or compiler.

The included launcher applies Dolphin's **48 MiB MEM1** requirement and uses a
separate profile for controls and saves. GameCube hardware is incompatible with
the current memory requirement. Nintendont is unsupported and untested.

## Verification

- The author confirmed the final combined game and Palace correction in Dolphin.
- 83 development host/artifact tests passed after removing the unlock override.
- 9 synthetic public-installer tests passed, covering patch decoding, damaged
  inputs/patches, output verification, installation cleanup, path handling and
  launch memory settings without driving Dolphin.
- Every one of the 43 generated patches was round-trip checked against the
  accepted stage using the dependency-free public decoder.
- The release ZIP was extracted and installed on Linux from the clean retail
  extraction. All 1,427 output files matched the release inventory, including
  unchanged retail progression configuration. The source extraction was
  reverified after installation.
- Windows/macOS instructions are included; those platforms were not independently
  tested. The removal of the development unlock flag was source/artifact-checked,
  not re-playtested with a blank save after packaging.

## Project status and licensing

**Completed, as-is, no updates or support planned.** This was a fun spare-time
proof of concept. The repository remains unarchived and forks are welcome;
issue tracking is disabled. No hardware port is planned.

Original installer/tests/documentation: MIT. Game-derived patch content and
third-party marks are not relicensed under MIT. See `THIRD_PARTY_NOTICES.md`.
