"""Why Cyrillic words in PERSONAL.DCT are ignored on load, and the fix.

  python personal_cyr.py WSDIR       (WSDIR holds the original WordStar 4.0 spelling files)

The PERSONAL.DCT reader (overlay 39DCh) returns every byte as `and ax, 7Fh`
(file 3A58h: 25 7F 00) -- the WordStar-document habit of stripping the soft
high bit. A cp866/cp1125 letter loses bit 7 and becomes ASCII junk, so the
tokenizer at 38A4h splits the word. Patch: byte at file 3A59h 7Fh -> FFh
(cyrovl.py includes it).
"""
import sys

import emu4

WORDS = ['мова', 'слово', 'їжак', 'ґанок']          # Ukrainian, cp1125
ASCII_WORD = 'zzyzx'                                # in neither MAIN nor INTERNAL


def run(wsdir, patched):
    o = emu4.Ovl(wsdir, trace_io=False)
    if patched:
        o.mu.mem_write(emu4.IMG + 0x3A59, b'\xff')
    text = 'WordStar\r\n' + ASCII_WORD + '\r\n' + ''.join(w + '\r\n' for w in WORDS)
    o.files[7] = text.encode('cp1125') + b'\x1a'
    emu4.open_dicts(o)
    return {w: emu4.check(o, w, 'cp1125') for w in [ASCII_WORD] + WORDS + ['мовa', 'хата']}


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    stock, fixed = run(sys.argv[1], False), run(sys.argv[1], True)
    for w in stock:
        print(f'{w:8} stock={stock[w]}  patched={fixed[w]}')
    assert stock[ASCII_WORD] == 1 and fixed[ASCII_WORD] == 1
    assert all(stock[w] != 1 for w in WORDS), 'stock should miss Cyrillic'
    assert all(fixed[w] == 1 for w in WORDS), 'patch should find Cyrillic'
    assert fixed['хата'] != 1 and fixed['мовa'] != 1     # absent; Latin a
    print('OK')
