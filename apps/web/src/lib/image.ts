/** Slate photo preparation: downscale (≤1600 px long side) and compress to roughly 150–300 KB JPEG. */

export const SLATE_MAX_SIDE = 1600;
export const TARGET_MAX_BYTES = 300 * 1024;

/** Target size preserving aspect ratio so that the long side is ≤ `maxSide` (never upscales). */
export function fitWithin(
  width: number,
  height: number,
  maxSide = SLATE_MAX_SIDE,
): { width: number; height: number; scale: number } {
  if (width <= 0 || height <= 0) return { width: 0, height: 0, scale: 0 };
  const long = Math.max(width, height);
  const scale = long > maxSide ? maxSide / long : 1;
  return { width: Math.max(1, Math.round(width * scale)), height: Math.max(1, Math.round(height * scale)), scale };
}

/**
 * Next JPEG quality to try given the last attempt's size, or null to accept the last attempt.
 * Steps down by 0.1 (not below 0.45) while the image is larger than `maxBytes`.
 */
export function nextQuality(lastBytes: number, lastQuality: number, maxBytes = TARGET_MAX_BYTES): number | null {
  if (lastBytes <= maxBytes) return null;
  const q = Math.round((lastQuality - 0.1) * 100) / 100;
  return q < 0.45 ? null : q;
}

/** If even the lowest quality is too large, scale both sides by this factor (bytes ∝ pixel count). */
export function shrinkFactor(bytes: number, maxBytes = TARGET_MAX_BYTES): number {
  if (bytes <= maxBytes) return 1;
  return Math.max(0.5, Math.sqrt(maxBytes / bytes) * 0.95);
}

function canvasToBlob(canvas: HTMLCanvasElement, type: string, quality: number): Promise<Blob> {
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('encode failed'))), type, quality),
  );
}

interface Decoded {
  source: CanvasImageSource;
  width: number;
  height: number;
  close: () => void;
}

async function decode(file: Blob): Promise<Decoded> {
  if (typeof createImageBitmap === 'function') {
    try {
      const bmp = await createImageBitmap(file, { imageOrientation: 'from-image' });
      return { source: bmp, width: bmp.width, height: bmp.height, close: () => bmp.close() };
    } catch {
      /* fall back to <img> */
    }
  }
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.src = url;
  await img.decode();
  return { source: img, width: img.naturalWidth, height: img.naturalHeight, close: () => URL.revokeObjectURL(url) };
}

export interface PreparedImage {
  blob: Blob;
  mime: string;
  width: number;
  height: number;
}

export async function prepareSlatePhoto(file: Blob): Promise<PreparedImage> {
  const img = await decode(file);
  try {
    let { width, height } = fitWithin(img.width, img.height);
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('no canvas');
    for (let round = 0; ; round++) {
      canvas.width = width;
      canvas.height = height;
      ctx.imageSmoothingQuality = 'high';
      ctx.drawImage(img.source, 0, 0, width, height);
      let q = 0.82;
      let blob = await canvasToBlob(canvas, 'image/jpeg', q);
      for (let next = nextQuality(blob.size, q); next !== null; next = nextQuality(blob.size, q)) {
        q = next;
        blob = await canvasToBlob(canvas, 'image/jpeg', q);
      }
      const f = shrinkFactor(blob.size);
      if (f === 1 || round >= 2) {
        canvas.width = 0; // release the bitmap early on 2 GB phones
        return { blob, mime: 'image/jpeg', width, height };
      }
      width = Math.round(width * f);
      height = Math.round(height * f);
    }
  } finally {
    img.close();
  }
}
