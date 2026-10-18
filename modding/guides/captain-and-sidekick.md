# 2 · Customize the example, then grow the roster

[Creator kit](../README.md) · [Artwork →](artwork-and-ui.md)

## First mod: change a displayed name

After bootstrap/build/stage, run from the public repository:

```sh
python3 modding/creator.py --workspace "/path/to/strikers-work" name --key PALMEIRAS --text "MY CLUB"
python3 modding/creator.py --workspace "/path/to/strikers-work" name --key HUMAN --text "MY SIDEKICK"
```

These edit the staged localization strings. Internal lookup keys, model IDs and
the existing roster slots are deliberately unchanged. Localized text does not
replace lettering baked into PNGs; update your art separately. Launch with the
creator command and inspect selection, HUD and pre-match screens.

Restaging resets these direct edits. For a lasting fork, change the display
value appended by `add_localization()` in `tools/palmeiras_team.py` and/or
`tools/human_sidekick.py`, keeping the lookup key stable. Then stage again.

## Another independent captain is a code + assets feature

Use [`templates/captain/slot-plan.json`](../templates/captain/slot-plan.json) as
your design record. It is not consumed by a magic slot generator. The current
example is team ID 9 (`TEAM_PALMEIRAS`), not a replacement for retail Daisy.
Do not assume changing a label creates ID 10.

| Contract | Existing example to follow in WORK |
| --- | --- |
| Team enum/count and identity | `include/Game/Team.h`, `include/Game/CharacterClass.h`, `src/Game/FE/feHelpFuncs.cpp` |
| Motion vs voice vs public name | `feHelpFuncs.cpp`: keep the Daisy motion family separate from Luigi audio and the public identity |
| Model/cache ownership | `include/Game/CharacterTemplate.h`, `src/Game/CharacterTemplate.cpp`; separate IDs must survive Daisy-vs-new-team matches |
| Selection/navigation | `src/Game/FE/feCaptainGridComponent.cpp`, `feCaptainComponent.cpp`, relevant `src/Game/SH/` captain/setup screens |
| FE layout/resources | `tools/palmeiras_team.py`: `Fen`, `ICON_NAMES`, `resource_aliases`, localization and native resource aliases |
| HUD, winner and async portraits | `src/Game/FE/Overlay/`, `src/Game/FE/feAsyncImage.cpp`; add native bundle entries, not just one selector icon |
| Audio and cutscenes | `src/Game/Audio/AudioLoader.cpp`, `CharacterAudio.cpp`, `AudioStream.cpp`, `src/Game/NisPlayer.cpp` |

Search the workspace for `TEAM_PALMEIRAS`, `palmeiras`, team counts and fixed
arrays. Treat that as a dependency map, not a global search-and-replace. Keep
the existing example when adding an entry, choose collision-free IDs/hashes,
grow arrays and navigation together, and add equivalent assets to every used
menu/cup/loading/winner path. Rebuild C++ and stage after changes.

## Another independent sidekick

Use [`templates/sidekick/slot-plan.json`](../templates/sidekick/slot-plan.json).
Human is sidekick ID 4 / character class 23 in this example. Follow:

- `include/Game/DB/BasicGameInfo.h` for sidekick IDs/count, plus
  `include/Game/CharacterClass.h` and all class-count consumers.
- `src/Game/FE/feSidekickGridComponent.cpp`: grid data, selectable count and navigation.
- `src/Game/CharacterTemplate.cpp`: a distinct model/cache identity and class routing.
- `src/Game/FE/feHelpFuncs.cpp`: family/audio conversions.
- `tools/human_sidekick.py`: `HumanFen`, portrait, localization and all-captain
  resource aliases. Pairings include retail captains and Palmeiras.

Do not reinterpret “human sidekick” as “Daisy captain”: classification, team
counts, NIS mapping and audio ownership are different even when the animation
family is shared. Test a full nine-sidekick team, mixed opponents, captain
choices, a goal/save/replay and returning to selection. Do not change global
player counts just to add a roster choice.

The kit preserves the working example and provides the files to extend it;
arbitrary slot injection is not automated or runtime-validated by this guide.
