// Generates the PWA PNG icons (Cheenu the bird) without any image dependency.
// Usage: node scripts/gen-icons.mjs  → writes public/icons/icon-{192,512}.png and maskable-512.png
import { deflateSync } from 'node:zlib';
import { mkdirSync, writeFileSync } from 'node:fs';

const crcTable = new Uint32Array(256).map((_, n) => {
  let c = n;
  for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
  return c >>> 0;
});
const crc32 = (buf) => {
  let c = 0xffffffff;
  for (const b of buf) c = crcTable[(c ^ b) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
};
const chunk = (type, data) => {
  const len = Buffer.alloc(4);
  len.writeUInt32BE(data.length);
  const td = Buffer.concat([Buffer.from(type), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(td));
  return Buffer.concat([len, td, crc]);
};

function png(size, pad) {
  const raw = Buffer.alloc(size * (size * 4 + 1));
  const s = (v) => v * (size - 2 * pad) + pad; // map unit coords into padded box
  const r = (v) => v * (size - 2 * pad);
  const shapes = [
    { kind: 'circle', cx: s(0.5), cy: s(0.56), r: r(0.34), col: [250, 204, 21] }, // body
    { kind: 'circle', cx: s(0.62), cy: s(0.36), r: r(0.2), col: [250, 204, 21] }, // head
    { kind: 'circle', cx: s(0.67), cy: s(0.33), r: r(0.045), col: [17, 24, 39] }, // eye
    { kind: 'tri', p: [[s(0.8), s(0.34)], [s(0.95), s(0.4)], [s(0.8), s(0.45)]], col: [249, 115, 22] }, // beak
    { kind: 'circle', cx: s(0.42), cy: s(0.6), r: r(0.16), col: [234, 179, 8] }, // wing
  ];
  const inTri = (x, y, [[x1, y1], [x2, y2], [x3, y3]]) => {
    const d = (ax, ay, bx, by, cx, cy) => (ax - cx) * (by - cy) - (bx - cx) * (ay - cy);
    const d1 = d(x, y, x1, y1, x2, y2), d2 = d(x, y, x2, y2, x3, y3), d3 = d(x, y, x3, y3, x1, y1);
    return !((d1 < 0 || d2 < 0 || d3 < 0) && (d1 > 0 || d2 > 0 || d3 > 0));
  };
  for (let y = 0; y < size; y++) {
    raw[y * (size * 4 + 1)] = 0;
    for (let x = 0; x < size; x++) {
      let col = [15, 118, 110];
      for (const sh of shapes) {
        const hit = sh.kind === 'circle' ? (x - sh.cx) ** 2 + (y - sh.cy) ** 2 <= sh.r ** 2 : inTri(x, y, sh.p);
        if (hit) col = sh.col;
      }
      const o = y * (size * 4 + 1) + 1 + x * 4;
      raw[o] = col[0]; raw[o + 1] = col[1]; raw[o + 2] = col[2]; raw[o + 3] = 255;
    }
  }
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(size, 0); ihdr.writeUInt32BE(size, 4);
  ihdr[8] = 8; ihdr[9] = 6; ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0;
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw, { level: 9 })), chunk('IEND', Buffer.alloc(0)),
  ]);
}

mkdirSync('public/icons', { recursive: true });
writeFileSync('public/icons/icon-192.png', png(192, 12));
writeFileSync('public/icons/icon-512.png', png(512, 32));
writeFileSync('public/icons/maskable-512.png', png(512, 104));
writeFileSync('public/icons/apple-touch-icon.png', png(180, 12));
console.log('icons written');
