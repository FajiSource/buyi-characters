# billumi-characters

Downloadable character packs for the Buyi Cart app. The app reads
`characters.json` from this repo, shows one thumbnail per character, and
downloads a character's poses to the device when the user taps it.

## Adding a character

1. Make a folder named after the character id (e.g. `lola-gray-senior/`).
2. Put the poses in it as `NN-pose-name.png` (e.g. `09-celebrating.png`).
   `celebrating` is used as the thumbnail; otherwise the first pose is.
   Draw the character facing RIGHT; the app mirrors it so it faces left.
3. Add a display name to `names.json`.
4. Run `python scripts/normalize_poses.py` (needs Pillow). It puts every pose on the
   same 440×440 transparent canvas, same height, feet on the bottom edge, so all
   poses line up in the app.
5. Run `node scripts/build-manifest.mjs` and commit `characters.json` with the images.
   Each character gets a `rev` hash; when images change, the app re-downloads them.

Don't rename or delete an existing character folder: users who already
downloaded it keep its id.
