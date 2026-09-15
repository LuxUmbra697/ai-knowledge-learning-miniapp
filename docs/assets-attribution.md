# Asset Sources

## Original Study Companions

Pink academy and apricot academy character sheets were generated for this project with OpenAI's built-in ImageGen on 2026-09-11. They are original illustrated characters, not photographs or real application screenshots. No reference-project character artwork was used. Selected frames are distributed as project artwork under the repository license to the extent rights in generated output permit; uniqueness and copyright eligibility are not guaranteed.

Files: `frontend/src/assets/companion-pink-{0,1,2}.png` and `companion-orange-{0,1,2}.png`. Each atlas contains reading/thinking, waving, and celebration poses. `frontend/scripts/build-assets.mjs` extracts evenly spaced frames and compresses PNGs. Combined six-frame size: approximately 144 KiB at initial export, measured from actual files.

Generation prompt: original adult anime study mentor; transparent three-column sprite sheet; identical outfit and scale within each sheet; full-body reading/thinking, waving, celebration poses; pink hair/cardigan or apricot hair/vest; no text, logos or third-party franchise references. Runtime animation is implemented separately from this artwork and can be disabled.

## Library Garden

`frontend/src/assets/library-garden.jpg` was generated with built-in ImageGen on 2026-09-15 for this
project, then resized without cropping to 1280x427 JPEG (120801 bytes). It is original decorative
artwork, not a screenshot, and uses no reference-project artwork or existing film characters.
Distribution follows the repository license to the extent rights in generated output permit;
copyright eligibility and exclusivity are not guaranteed.

Prompt: original compact 3:1 school-library panorama open to a garden, notebook and pencil in the
foreground, pale-blue window frames, leaf-green canopy and clouds, a small pink-haired student
reading on the right; hand-painted 2D animated-film background, irregular ink lines, matte gouache
and watercolor, gentle daylight, green/blue/white with restrained coral; no text, logos, watermark,
existing characters or UI mockup. Generated art is never placed in the screenshots directory.

## Academy Courtyard And Notebook Shelf

Generated with built-in ImageGen on 2026-09-15, using original scene descriptions and no reference
project assets or existing film characters. These are decorative images, not runtime screenshots.
Distribution follows the repository license to the extent rights in generated output permit;
copyright eligibility and exclusivity are not guaranteed.

| Asset | Export | Placement |
| --- | --- | --- |
| `frontend/src/assets/academy-gate.jpg` | 1280x853, 208061 bytes | Full-width login background; centered aspect-fill crop on portrait phones |
| `frontend/src/assets/notebook-shelf.jpg` | 1200x400, 53283 bytes | Knowledge-library band, aspect-fit without cropping; 3:1 mobile, at most 200px tall on desktop |

Courtyard prompt: original 3:2 school courtyard, central gate and path, pale sky above, white school
building, leafy tree at left and pink flowers at edges; no people, lettering or logos; matte gouache
and watercolor with irregular ink, green/blue/white and restrained coral. Keep central architecture
legible in a portrait crop, with open sky for a heading.

Shelf prompt: original 3:1 study-notebook panorama, pastel blue/white/coral books at right, pressed
leaf page and small plant at left, pencil cup, mostly plain pale green/white center; hand-painted
matte gouache, objects entirely within the shallow band; no characters, text, logos, glow or UI.

Both selected outputs were resized without cropping and JPEG-compressed with the pinned `sharp`
dependency (quality 78 and 80). UI uses local Taro `Image` assets rather than remote media or
miniapp-incompatible local CSS URLs. Actual runtime captures are stored separately under
`docs/screenshots/h5/`; no weapp runtime screenshot is claimed from these assets.

## Interface Icons

[Lucide](https://lucide.dev/license), ISC license. PNGs are generated from `lucide-static` SVGs for the shared Taro interface. The package version is pinned by `frontend/package-lock.json`. Original SVG geometry is retained; raster export allows a consistent miniapp `Image` implementation.

## Fonts

System fonts only. The application does not distribute or download proprietary font files.

## Existing Assets

The original repository's four tab PNGs are retained in source history. Their original authorship has not been newly attributed. The redesigned navigation uses Lucide instead. Original repository license and author notices remain intact.
