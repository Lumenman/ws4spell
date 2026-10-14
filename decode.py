"""Standalone decoder for the WordStar 4.0 MAIN.DCT record bitstream (CorrectStar 3.0).

  python decode.py WSDIR > words.txt      every stored form, one per line (60337 for the
                                          shipped US dictionary); WSDIR holds MAIN.DCT and
                                          INTERNAL.DCT

Verified record by record against the engine running under emulation. See WS4DCT_FORMAT.md, 6.

Record stream (per 512-byte sector, self-contained; prefix state resets at
sector start). Units are big-endian 16-bit words unless noted.

Record:
  w0 = u16be
  if w0 & 0x8000:                     # suffix form
      e  = A[((w0 & 0x7FE0) >> 5) - 1]  (u16le from INTERNAL table A)
      fl5     = (e >> 10) & 0x3F
      prefix  = (e >> 6) & 0xF
      flags32 = (e & 0x3F) << 10
      cont    = w0 & 1
      n_new   = (w0 >> 1) & 0xF
      b4      = 0
  else:                               # literal form
      fl5     = (w0 >> 9) & 0x3F
      b4      = w0 & 7
      flags32 = (w0 & 0x1F8) << 7
      w1 = u16be
      n_new   = (w1 >> 11) & 0x1F
      prefix  = (w1 >> 6) & 0x1F
      cont    = w1 & 1
  rem = n_new % 3
  codes = []
  if rem == 1:
      if literal: codes.append((w1 >> 1) & 0x1F)   # packed in header
      else:
          b = u8; codes.append((b >> 3) & 0x1F)
          flags32 |= (b & 6) << 7; cont = b & 1; d = 8
  elif rem == 2:
      w2 = u16be
      codes.append((w2 >> 11) & 0x1F); codes.append((w2 >> 6) & 0x1F)
      flags32 |= (w2 & 0x3E) << 4; d = 0xB; cont = w2 & 1
  while len(codes) < n_new:           # groups of 3
      b0 = u8
      if b0 & 0x80:  w = TRI[(b0 & 0x7F) - 1]     # trigram table (u16le)
      else:          w = (b0 << 8) | u8
      codes += [(w >> 10) & 0x1F, (w >> 5) & 0x1F, w & 0x1F]
  # flags trailer (only if cont == 0); d starts 6, 8 or 0xB per above
  if cont == 0:
      w3 = u16le at cursor (bytes b0,b1)
      ax = w3 & 0xFE
      ax <<= (8 - d) if d <= 8 else (d - 8)
      flags32 |= ax (into low word per asm)
      d += 7
      if w3 & 1: cursor += 1          # only one byte consumed
      else:
          cursor += 2
          ax = ((w3 >> 8) & 0xFF) & 0xFE   # second byte
          ax >>= (d - 8)
          flags32 |= ax
  f32 = (flags32 & 0xFFFF) << 16
"""
import os
import sys

MAIN = INT = b''
A = TRI = []
TRI_BASE = 0x7FE // 2   # word index of trigram table inside A


def load(wsdir):
    """Read MAIN.DCT and INTERNAL.DCT (suffix and trigram tables) from wsdir."""
    global MAIN, INT, A, TRI
    MAIN = open(os.path.join(wsdir, 'MAIN.DCT'), 'rb').read()
    INT = open(os.path.join(wsdir, 'INTERNAL.DCT'), 'rb').read()
    A = [int.from_bytes(INT[0x200 + 2 * i:0x202 + 2 * i], 'little') for i in range(0x480)]
    TRI = A[TRI_BASE:TRI_BASE + 129]


C2C = {0: '`', 27: "'", 28: '-', 29: '.', 30: '/'}
def code2ch(c):
    if c in C2C:
        return C2C[c]
    if 1 <= c <= 26:
        return chr(0x60 + c)
    return '?'

def decode_sector(secno, limit=None):
    """Decode all records in sector secno. Returns list of dicts."""
    buf = MAIN[secno * 512:(secno + 1) * 512]
    pos = 0
    prev = []
    out = []
    while pos + 2 <= 512:
        start = pos
        w0 = (buf[pos] << 8) | buf[pos + 1]
        pos += 2
        if w0 == 0xFFFF:
            break
        d = 6
        flags32 = 0
        if w0 & 0x8000:
            idx = ((w0 & 0x7FE0) >> 5) - 1
            if not (0 <= idx < len(A)):
                break
            e = A[idx]
            fl5 = (e >> 10) & 0x3F
            prefix = (e >> 6) & 0xF
            flags32 |= (e & 0x3F) << 10
            cont = w0 & 1
            n_new = (w0 >> 1) & 0xF
            b4 = 0
            literal = False
        else:
            fl5 = (w0 >> 9) & 0x3F
            b4 = w0 & 7
            flags32 |= (w0 & 0x1F8) << 7
            w1 = (buf[pos] << 8) | buf[pos + 1]
            pos += 2
            n_new = (w1 >> 11) & 0x1F
            prefix = (w1 >> 6) & 0x1F
            cont = w1 & 1
            literal = True
        rem = n_new % 3
        codes = []
        if rem == 1:
            if literal:
                codes.append((w1 >> 1) & 0x1F)
            else:
                b = buf[pos]; pos += 1
                codes.append((b >> 3) & 0x1F)
                flags32 |= (b & 6) << 7
                cont = b & 1
                d = 8
        elif rem == 2:
            w2 = (buf[pos] << 8) | buf[pos + 1]
            pos += 2
            codes.append((w2 >> 11) & 0x1F)
            codes.append((w2 >> 6) & 0x1F)
            flags32 |= (w2 & 0x3E) << 4
            d = 0xB
            cont = w2 & 1
        while len(codes) < n_new:
            b0 = buf[pos]
            if b0 & 0x80:
                t = (b0 & 0x7F) - 1
                if not (0 <= t < len(TRI)):
                    break
                w = TRI[t]
                pos += 1
            else:
                w = (b0 << 8) | buf[pos + 1]
                pos += 2
            codes += [(w >> 10) & 0x1F, (w >> 5) & 0x1F, w & 0x1F]
        if cont == 0 and pos + 2 <= 512:
            w3 = buf[pos] | (buf[pos + 1] << 8)   # little-endian load
            ax = w3 & 0xFE
            if d <= 8:
                ax <<= (8 - d)
            else:
                ax <<= (d - 8)
            flags32 |= ax
            d += 7
            if w3 & 1:
                pos += 1
            else:
                pos += 2
                ax = ((w3 >> 8) & 0xFE)
                ax >>= (d - 8)
                flags32 |= ax
        # asm: [bp+0]=0, [bp+2]=si -> f32 = si<<16 where si = accumulated low
        f32 = (flags32 & 0xFFFF) << 16
        codes = codes[:n_new]
        word_codes = prev[:prefix] + codes
        prev = word_codes
        word = ''.join(code2ch(c) for c in word_codes)
        if fl5 & 0x15:
            if fl5 & 3 == 1:
                word += 's'
            elif fl5 & 0x0C == 4:
                word += "'s"
            elif fl5 & 0x30 == 0x10:
                word += 'ing'
        out.append(dict(start=start, end=pos, w0=w0, len=len(word_codes),
                        word=word, codes=word_codes, fl5=fl5, f32=f32,
                        b4=b4, prefix=prefix, nnew=n_new))
        if limit and len(out) >= limit:
            break
    return out

if __name__ == '__main__':
    load(sys.argv[1])
    for sec in range(1, len(MAIN) // 512):
        for r in decode_sector(sec):
            print(r['word'])
