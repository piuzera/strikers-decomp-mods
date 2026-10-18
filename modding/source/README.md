# Pinned source diff

Base: [yannicksuter/smstrikers-decomp](https://github.com/yannicksuter/smstrikers-decomp)
at **`d1f357ffeb1d8e89311edebf9a4b304b05ece7bb`**.

`upstream.json` records the base URL/commit, patch SHA-256 and every overlay
file's SHA-256. `create_workspace.py` verifies them before applying the patch.
The diff contains the combined mod's C++/header changes, not a full source tree
or any retail/build artifacts. It includes the field/camera, team/sidekick,
memory/loading, UI, AI, physics, snapshot/replay and event changes required to
rebuild the accepted executable.

If applying manually, start at that exact commit, initialize upstream submodules,
then use `git apply --check` followed by `git apply` on `combined-mod.patch`.
Copy `../overlay/` onto the clone while preserving its relative paths. This
alone does not supply game inputs, native exports or art; the bootstrap restores
those from the user's verified installation.

The checked Linux x86_64 toolchain reproduced release `sys/main.dol` SHA-256:
`eb4cb7e50cbc6e33c10bc9e779b2537d7fc3876d6c3f03576538913158fec76d`.
The restored UI inputs are quantized native decodes, so restaged UI bundles are
not claimed byte-identical to the original high-resolution art pipeline.

Licensing remains mixed/game-derived; see [NOTICE](../NOTICE.md).
