# Creator kit · make your own Strikers mod

[← Project home](../README.md)

This is the editable example behind the release: a focused source patch,
native asset tools, generic templates and a repeatable clean-input packaging
workflow. Start by changing the existing Palmeiras/Human example; graduate to
adding independent roster entries once its identity/resource contracts are clear.

| Start here | What you will do |
| --- | --- |
| [1 · Workspace](guides/getting-started.md) | Clone the pinned decomp, apply our changes and recover editable local inputs. |
| [2 · Captain & sidekick](guides/captain-and-sidekick.md) | Rename the example; map everything required for another slot. |
| [3 · Artwork & UI](guides/artwork-and-ui.md) | Paint portraits, banners and loading art without breaking native allocations. |
| [4 · Custom models](guides/custom-models.md) | Export your own Daisy-bound mesh with the native intermediate format. |
| [5 · Stadium & formations](guides/stadium-and-formations.md) | Change dimensions, transforms and all ten formation positions. |
| [6 · Test & package](guides/testing-and-packaging.md) | Verify the result and distribute patches against clean retail inputs. |

## What is included

- `source/`: source diff and exact upstream commit/checksums—**not the full decomp**.
- `overlay/`: the actual example staging/export/UI tools and formation data,
  copied into your local upstream workspace by the bootstrap.
- `templates/`: generic roster planning files, artwork canvases, model schema and
  stadium planning data. Planning JSONs document contracts; they do not magically
  create new C++ roster slots.
- `create_workspace.py`: restores an editable workspace from your clean game and
  installed v1.0.0, including 10 local PNGs and native model-export donors.
- `creator.py`: working display-name/badge edits, custom launch and patch packaging.
- `export_model.py`, `blender_export.py`: intermediate-to-native and Blender-to-intermediate helpers.

**Playing:** Python 3.10+, Dolphin. **Creating:** Python 3.11+, Git, Ninja,
ImageMagick 7 (`magick`) and upstream's pinned toolchain. Packaging additionally
uses `bsdiff4==1.2.6`; Blender is optional for mesh authoring.

Build/staging is tested on Linux; see the [recorded verification](VERIFICATION.md).
Windows/macOS creator builds depend on upstream
toolchain support and are not independently tested here. See
[licensing/scope](NOTICE.md). The project is completed and the kit is offered
as-is, with no updates/support planned.
