// One-time generator: renders an 8-frame film-grain loop as PNGs using
// @remotion/noise. Run once with:  node scripts/gen_grain.mjs
// Options: --w <px> --h <px> --dir <subdir of public/>
//   default: 960x540 tiles into public/grain/          (16:9)
//   portrait: node scripts/gen_grain.mjs --w 540 --h 960 --dir grain-portrait
// Tiles are cycled per frame by FilmGrain (mix-blend-mode: overlay).
// Pre-rendering the loop keeps the actual video render fast — no per-pixel
// noise is computed at render time.
import {noise3D} from '@remotion/noise';
import {writeFileSync, mkdirSync} from 'fs';
import {deflateSync} from 'zlib';

const cliArgs = process.argv.slice(2);
const cliGet = (key, fallback) => {
  const i = cliArgs.indexOf(key);
  return i >= 0 && i + 1 < cliArgs.length ? cliArgs[i + 1] : fallback;
};
const W = parseInt(cliGet('--w', '960'), 10);
const H = parseInt(cliGet('--h', '540'), 10);
const DIR = cliGet('--dir', 'grain');
const FRAMES = 8, AMPLITUDE = 30;
mkdirSync(new URL(`../public/${DIR}`, import.meta.url), {recursive: true});

// --- minimal PNG writer (RGBA, 8-bit, no interlace) ---
const crcTable = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();
function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) c = crcTable[(c ^ buf[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}
function chunk(type, data) {
  const len = Buffer.alloc(4); len.writeUInt32BE(data.length);
  const body = Buffer.concat([Buffer.from(type, 'ascii'), data]);
  const crc = Buffer.alloc(4); crc.writeUInt32BE(crc32(body));
  return Buffer.concat([len, body, crc]);
}
function writePng(path, w, h, gray) {
  const rows = [];
  for (let y = 0; y < h; y++) {
    const row = Buffer.alloc(1 + w * 4);
    row[0] = 0;
    for (let x = 0; x < w; x++) {
      const v = gray[y * w + x];
      row[1 + x * 4] = v;
      row[1 + x * 4 + 1] = v;
      row[1 + x * 4 + 2] = v;
      row[1 + x * 4 + 3] = 255;
    }
    rows.push(row);
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8; ihdr[9] = 6;
  writeFileSync(path, Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', deflateSync(Buffer.concat(rows))),
    chunk('IEND', Buffer.alloc(0)),
  ]));
}

for (let f = 0; f < FRAMES; f++) {
  console.log(`grain frame ${f + 1}/${FRAMES}...`);
  const gray = new Uint8Array(W * H);
  const seed = 1337 + f * 7919;
  for (let y = 0; y < H; y++) {
    for (let x = 0; x < W; x++) {
      const n = noise3D(seed, (x / W) * 6, (y / H) * 6, 0.5);
      gray[y * W + x] = Math.max(0, Math.min(255, Math.round(128 + n * AMPLITUDE)));
    }
  }
  writePng(new URL(`../public/${DIR}/grain-${f}.png`, import.meta.url), W, H, gray);
}
console.log(`done: ${W}x${H} -> public/${DIR}/`);
