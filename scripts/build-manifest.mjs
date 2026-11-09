// Regenerates characters.json from the folders in this repo.
// Run after adding/renaming a character or pose:  node scripts/build-manifest.mjs
//
// Folder name = character id. Files must be named NN-pose-name.png.
// The app shows the COVER_POSE image as the character's thumbnail and on Home.
import { readdirSync, statSync, writeFileSync, readFileSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const COVER_POSE = 'celebrating';

// Optional friendly names; anything missing falls back to the folder name.
const namesFile = join(root, 'names.json');
const names = existsSync(namesFile) ? JSON.parse(readFileSync(namesFile, 'utf8')) : {};

const characters = readdirSync(root)
  .filter((d) => !d.startsWith('.') && d !== 'scripts' && statSync(join(root, d)).isDirectory())
  .sort()
  .map((id) => {
    const poses = readdirSync(join(root, id))
      .filter((f) => /^\d+-.+\.png$/i.test(f))
      .sort()
      .map((file) => ({ id: file.replace(/^\d+-/, '').replace(/\.png$/i, ''), file: `${id}/${file}` }));
    if (poses.length === 0) return null;
    const cover = poses.find((p) => p.id === COVER_POSE) ?? poses[0];
    // Changes whenever any pose image changes, so the app knows to re-download.
    const hash = createHash('sha1');
    for (const pose of poses) hash.update(pose.id).update(readFileSync(join(root, pose.file)));
    const rev = hash.digest('hex').slice(0, 10);
    return { id, name: names[id] ?? id, cover: cover.id, rev, poses };
  })
  .filter(Boolean);

writeFileSync(join(root, 'characters.json'), JSON.stringify({ version: 1, characters }, null, 2) + '\n');
console.log(`Wrote ${characters.length} characters to characters.json`);
