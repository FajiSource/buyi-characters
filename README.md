# billumi-characters

Downloadable character packs for the Buyi Cart app. The app reads
`characters.json` from this repo, shows one thumbnail per character, and
downloads a character's poses to the device when the user taps it.

## Adding a character

1. Make a folder named after the character id (e.g. `lola-gray-senior/`).
2. Put the poses in it as `NN-pose-name.png` (e.g. `09-celebrating.png`).
   `celebrating` is used as the thumbnail; otherwise the first pose is.
3. Add a display name to `names.json`.
4. Run `node scripts/build-manifest.mjs` and commit `characters.json` with the images.

Don't rename or delete an existing character folder: users who already
downloaded it keep its id.
