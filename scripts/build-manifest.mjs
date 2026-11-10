// Regenerates characters.json from the folders in this repo.
// Run after adding/renaming a character or pose:  node scripts/build-manifest.mjs
//
// Folder name = the character's name shown in the app (e.g. "Aiven"). The id is the
// lowercased folder name. Files must be named NN-pose-name.png.
// The app shows the COVER_POSE image as the character's thumbnail and on Home.
import { readdirSync, statSync, writeFileSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const COVER_POSE = 'celebrating';
// Everyone else is paid. A paid character's Google Play product (and RevenueCat entitlement)
// is `character_<id>`; create it in Play Console before pushing a new paid character.
const FREE_CHARACTERS = new Set(['orwin', 'shaina']);

const characters = readdirSync(root)
  .filter((d) => !d.startsWith('.') && d !== 'scripts' && d !== 'new-need-to-excract' && statSync(join(root, d)).isDirectory())
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
    const characterId = id.toLowerCase();
    const productId = FREE_CHARACTERS.has(characterId) ? undefined : `character_${characterId}`;
    return { id: characterId, name: id, cover: cover.id, rev, ...(productId && { productId }), poses };
  })
  .filter(Boolean);

writeFileSync(join(root, 'characters.json'), JSON.stringify({ version: 1, characters }, null, 2) + '\n');
console.log(`Wrote ${characters.length} characters to characters.json`);
