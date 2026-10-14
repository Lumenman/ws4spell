"""Build a Cyrillic dictionary (UK.DCT / RU.DCT) for the patched WordStar 4 WSSPELL.OVR.

  python cyrdct.py dict_corp_vis.txt.bz2 UK.DCT          VESUM (brown-uk/dict_uk), with tags
  python cyrdct.py opcorpora RU.DCT --cp cp866           OpenCorpora via pymorphy3-dicts-ru
  python cyrdct.py words.txt RU.DCT --cp cp866           plain UTF-8 list, one word per line

Format: the file is a sequence of 512-byte blocks, no header. Words are lowercase,
in the OEM code page, sorted by bytes. Each entry is
    prefix  (1 byte: bits 0-6 letters shared with the previous word of the block,
             bit 7 = accepted but never offered as a suggestion)
    suffix  (the remaining bytes)
    00h
The first entry of a block has prefix 0 (+ bit 7), so a block's first word reads
directly. FFh in place of a prefix (or the end of the block) ends the block.
Lookup: binary search over the blocks' first words, then a linear scan of one block.

VESUM: forms tagged :bad are left out (as wsspell/vesum.py); a form is offered as a
suggestion only if one of its readings has none of NOSUGG and is not a vocative,
and it is longer than two letters.
OpenCorpora (python -m pip install --user pymorphy3 pymorphy3-dicts-ru): readings
tagged Erro are left out; Abbr, Arch, Slng, Dist, Infr are not suggested; a form with
ё also gets its е spelling, accepted but not suggested.
"""
import argparse
import bz2

BLOCK = 512
NOSUGG = {'abbr', 'rare', 'arch', 'slang', 'alt', 'short', 'vulg', 'obsc', 'v_kly'}
NOSUGG_OC = {'Abbr', 'Arch', 'Slng', 'Dist', 'Infr'}


def build(words):
    """words: sorted list of (bytes, nosugg)."""
    blocks, cur, prev = [], bytearray(), b''
    for w, ns in words:
        p = 0
        if cur:
            while p < min(len(w), len(prev)) and w[p] == prev[p]:
                p += 1
        e = bytes([p | ns << 7]) + w[p:] + b'\0'
        if len(cur) + len(e) > BLOCK:
            blocks.append(bytes(cur.ljust(BLOCK, b'\xff')))
            cur = bytearray()
            e = bytes([ns << 7]) + w + b'\0'
        cur += e
        prev = w
    if cur:
        blocks.append(bytes(cur.ljust(BLOCK, b'\xff')))
    return b''.join(blocks)


def block_words(blk):
    """(word, nosugg) of one block."""
    pos, prev = 0, b''
    while pos < BLOCK and blk[pos] != 0xFF:
        p, end = blk[pos], blk.index(0, pos + 1)
        prev = prev[:p & 0x7F] + blk[pos + 1:end]
        yield prev, p >> 7
        pos = end + 1


def lookup(dct, w):
    """Reference for the overlay code: None if absent, else the nosugg flag."""
    lo, hi = 0, len(dct) // BLOCK
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if next(block_words(dct[mid * BLOCK:(mid + 1) * BLOCK]))[0] <= w:
            lo = mid
        else:
            hi = mid
    return next((ns for x, ns in block_words(dct[lo * BLOCK:(lo + 1) * BLOCK]) if x == w), None)


def norm(w):
    return w.replace('’', "'").replace('ʼ', "'").lower()


def readings(path):
    """(form, suggestible) pairs from VESUM (.bz2), OpenCorpora or a plain word list."""
    if path == 'opcorpora':
        import pymorphy3
        for w, tag, *_ in pymorphy3.MorphAnalyzer().dictionary.iter_known_words():
            g = tag.grammemes
            if 'Erro' not in g and not any(c.isdigit() for c in w):
                yield w, not (g & NOSUGG_OC)
                if 'ё' in w:
                    yield w.replace('ё', 'е'), False
    elif path.endswith('.bz2'):
        for line in bz2.open(path, 'rt', encoding='utf-8'):
            p = line.split('#')[0].split()
            if len(p) > 1 and ':bad' not in p[1]:
                yield p[0], not (NOSUGG & set(p[1].split(':')))
    else:
        for line in open(path, encoding='utf-8'):
            if line.strip():
                yield line.strip(), True


def load(path, cp):
    sugg = {}
    for w, ok in readings(path):
        try:
            b = norm(w).encode(cp)
        except UnicodeEncodeError:
            continue
        if 1 < len(b) < 64 and not (set(b) & {0, 0xFF}) and max(b) >= 0x80:
            sugg[b] = sugg.get(b, False) or (ok and len(b) > 2)
    return sorted((b, int(not ok)) for b, ok in sugg.items())


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('words')
    ap.add_argument('out')
    ap.add_argument('--cp', default='cp1125')
    a = ap.parse_args()
    ws = load(a.words, a.cp)
    dct = build(ws)
    open(a.out, 'wb').write(dct)
    assert all(lookup(dct, w) == ns for w, ns in ws[::997])
    assert lookup(dct, 'ьььь'.encode(a.cp)) is None
    print(f'{a.out}: {len(ws)} words ({sum(ns for _, ns in ws)} not suggested), '
          f'{len(dct) // BLOCK} blocks, {len(dct)} bytes')
