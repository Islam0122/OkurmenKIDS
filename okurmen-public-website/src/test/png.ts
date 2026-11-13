/** Minimal PNG reader for tests (8-bit RGB/RGBA, non-interlaced): enough to check favicon transparency. */
import { inflateSync } from 'node:zlib'

export function PNG(buf: Buffer) {
  if (buf.subarray(1, 4).toString() !== 'PNG') throw new Error('not a PNG')
  const width = buf.readUInt32BE(16)
  const height = buf.readUInt32BE(20)
  const colorType = buf[25]
  if (buf[24] !== 8 || buf[28] !== 0 || (colorType !== 2 && colorType !== 6)) throw new Error('unsupported PNG')
  const channels = colorType === 6 ? 4 : 3
  const chunks: Buffer[] = []
  for (let at = 8; at < buf.length;) {
    const length = buf.readUInt32BE(at)
    const type = buf.subarray(at + 4, at + 8).toString()
    if (type === 'IDAT') chunks.push(buf.subarray(at + 8, at + 8 + length))
    at += 12 + length
  }
  const raw = inflateSync(Buffer.concat(chunks))
  const stride = width * channels
  const out = Buffer.alloc(height * stride)
  for (let y = 0; y < height; y++) {
    const filter = raw[y * (stride + 1)]
    for (let x = 0; x < stride; x++) {
      const v = raw[y * (stride + 1) + 1 + x]
      const left = x >= channels ? out[y * stride + x - channels] : 0
      const up = y ? out[(y - 1) * stride + x] : 0
      const ul = y && x >= channels ? out[(y - 1) * stride + x - channels] : 0
      const p = left + up - ul
      const pa = Math.abs(p - left), pb = Math.abs(p - up), pc = Math.abs(p - ul)
      const paeth = pa <= pb && pa <= pc ? left : pb <= pc ? up : ul
      out[y * stride + x] = (v + [0, left, up, (left + up) >> 1, paeth][filter]) & 0xff
    }
  }
  return {
    width,
    height,
    channels,
    pixel: (x: number, y: number) => {
      const i = y * stride + x * channels
      return channels === 4 ? [out[i], out[i + 1], out[i + 2], out[i + 3]] : [out[i], out[i + 1], out[i + 2], 255]
    },
  }
}
