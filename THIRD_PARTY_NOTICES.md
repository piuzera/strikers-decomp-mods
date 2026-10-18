# Third-party material and rights

The MIT license in this repository applies to the original Python installer,
tests and documentation authored for this release, to the extent the author
controls those rights. It does not grant rights in the game, third-party code,
club marks, reference artwork or other third-party material.

The later creator kit includes existing contribution files under
`modding/overlay/` and a focused source diff under `modding/source/`.
Those are not covered by a blanket MIT relicensing: applicable prior CC0
dedications and upstream/game-derived rights remain. See
[modding/NOTICE.md](modding/NOTICE.md) for that boundary. Screenshots and the demo
are gameplay media, not an MIT asset pack.

## Game and decompilation

Super Mario Strikers / Mario Smash Football is a Nintendo / Next Level Games
title. This unofficial patch set was produced using the independent
[smstrikers-decomp](https://github.com/yannicksuter/smstrikers-decomp) project.
That project is a source reconstruction, not an official source release, and
has mixed licensing and game-derived material. Its contributors' notices and
third-party rights remain applicable; this release does not relicense the
decompilation or the original/reconstructed game under MIT.

This repository supplies binary differences, not a game image, complete game
executable, SDK or extracted retail assets. Installation requires the user's
own unmodified USA Rev 0 extraction. A patch is not a blanket license to use or
redistribute the resulting game. Do not upload original or patched game files.

## Embedded third-party code

The original game/decompilation includes Open Dynamics Engine 0.5, with its
historical BSD-style license option. Its notice is preserved in
[licenses/ODE-BSD.txt](licenses/ODE-BSD.txt). The applicable ODE notice must
accompany redistribution of covered material. This does not grant rights in
independent game-developer modifications.

The reconstruction also identifies eCos-derived math routines with GPLv2-or-later
terms and file-level linking exceptions, and Sun fdlibm notices. Those routines
are not installer code or newly authored MIT material. Consult the upstream
[source tree](https://github.com/yannicksuter/smstrikers-decomp)
and relevant file headers for their terms. The creator source diff contains
reconstructed game/runtime/SDK context around modified code; it is not
represented as MIT-licensed material. No compiler binaries, full SDK
distribution or complete upstream source tree is included.

## Artwork and marks

Palmeiras names, crest and marks belong to their respective owners and are not
MIT-licensed by this project. The crest source used during development was
<https://upload.wikimedia.org/wikipedia/commons/1/10/Palmeiras_logo.svg>.
The Human model was generated from approved reference artwork through
fal.ai's Meshy v6 image-to-3D service, then optimized and fitted to the game's
native animation family. No CC0 or blanket MIT claim is made for the model,
reference artwork or game-derived model/resource structures. Private source
artwork, Blender files and generation records are omitted.

## Patch implementation

Patch files use the BSDIFF40 format. The standard-library decoder in `install.py`
is original code for this release. The private packaging process uses bsdiff4;
its library and native binaries are not distributed or required by the installer.
Using the BSDIFF40 format does not change the rights in patch content.

No affiliation with or endorsement by Nintendo, Next Level Games, Palmeiras,
the decompilation contributors, Dolphin, fal.ai or Meshy is implied.
