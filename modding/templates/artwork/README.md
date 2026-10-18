# Generic art canvases

These two SVGs are original MIT examples, not Palmeiras/game artwork.
Keep transparent padding; selection art should not fill every pixel.

```sh
magick banner.svg banner.png
magick portrait.svg portrait.png
```

`banner.png`: 256×64 captain HUD/async banner. `portrait.png`: 128×128
captain or sidekick grid icon. For loading art, make a 256×256 transparent PNG;
Human's background variant is 128×128. The complete input map is in the
[artwork guide](../../guides/artwork-and-ui.md).
