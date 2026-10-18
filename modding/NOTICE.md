# Creator-kit licensing and scope

The new bootstrap, creator helpers, generic examples and guides are original MIT
contributions. Existing Python files under `overlay/tools/` retain the project's
existing CC0 dedication **where the contributor owns the rights**; they have not
been silently relicensed as MIT. See [CC0](https://creativecommons.org/publicdomain/zero/1.0/legalcode).
Native format knowledge, identifiers and game-derived material remain subject
to the applicable third-party rights.

`source/combined-mod.patch` is a focused diff against the exact upstream revision
in `source/upstream.json`. It modifies reconstructed game/SDK code and has mixed
provenance; it is **not a blanket MIT or CC0 source release**. It excludes the
full upstream tree, SDK/compiler binaries, extracted game files and private art.
The user's local clone retains upstream notices. ODE's BSD notice is included
at the repository root under `licenses/`; other upstream file-level terms remain.
See [third-party notices](../THIRD_PARTY_NOTICES.md).

The creator kit is a worked example, not an arbitrary-roster generator. Replacing
the example's display art is much simpler than adding another independent slot.
New identities require C++ and native resource changes described in the guides.
Recovered PNGs/native model exports are created on the user's machine from their
own installed game; they are not source artwork or a licensed asset pack.
Private Blender scenes, original high-resolution paint masters and generation
inputs are not included or needed for the beginner path.
