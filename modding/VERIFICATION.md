# Creator-kit verification

The creator kit was checked on Linux x86_64 with the pinned upstream revision.
These are recorded checks, not claims of arbitrary new-slot or cross-platform
runtime validation:

1. Bootstrapped a fresh clone from the pinned upstream commit using a local Git
   mirror, with independently initialized pinned upstream submodules. Applied
   the public source diff and recovered ten PNGs plus native export donors from
   a clean extraction and the verified v1.0.0 installation.
2. Reused the exact pinned downloaded compiler/tool binaries, **not compiled
   game objects**, to perform a fresh build. The resulting executable matched
   the released DOL byte-for-byte:
   `eb4cb7e50cbc6e33c10bc9e779b2537d7fc3876d6c3f03576538913158fec76d`.
3. Staged from recovered local inputs. The creator workspace suite ran **37
   tests: 36 passed, one historical Blender-intermediate test skipped**.
4. Changed the displayed captain name to `MY CLUB` and repacked the generic
   256×64 banner. Generated a standalone custom patch package; its installer
   reconstructed **all 1,427 files byte-for-byte** against the custom stage.
5. Exported a synthetic one-triangle intermediate through `export_model.py`
   against the real native Daisy donor. Verified bind/texture contracts and
   influence budgets. This checks the encoding pipeline, not player appearance
   or animations. The new Blender selection-export helper was syntax-checked,
   not live-tested in Blender.
6. The public root suite has **12 passing tests**, including installer checks,
   Unicode display-name replacement, source/overlay checksums and local
   documentation/media links.

The original complete game/Palace fix was user-confirmed in Dolphin. The
synthetic creator edits above were not separately playtested. New models and
additional roster slots must be tested in-game by their authors. Recovered
quantized art can re-encode differently from the original paint pipeline.
Windows/macOS creator builds remain untested.
