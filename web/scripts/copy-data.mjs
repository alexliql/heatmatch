// Copies the committed data assets into public/ so the static export serves
// them. A copy (not a symlink) because `next build` on CI runners and Vercel
// does not reliably follow symlinks out of the project root.
import { cp, mkdir, readdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const src = join(root, "..", "data");
const dest = join(root, "public", "data");

await mkdir(dest, { recursive: true });
const entries = await readdir(src, { withFileTypes: true });
const assets = entries.filter((e) => e.isFile() && /\.(geojson|json)$/.test(e.name));
for (const a of assets) {
  await cp(join(src, a.name), join(dest, a.name));
}
console.log(`copy-data: ${assets.length} file(s) -> public/data`);
