"""Patch WordStar 4.00 WS.EXE character tables from cp437 to cp1125 / cp866 (builds 020, 021).

Usage: python patchcp.py WS.EXE         (writes WSU.EXE = cp1125, WSR.EXE = cp866 next to it)
       python patchcp.py --check EXE CP  (run the EXE's own UPPER/LOWER code in Unicorn and compare with Python)

User Area (PATCH.LST address + 600h = file offset):
  LGLCHR 0E5Ch  256-bit table: letter within a word (word moves, ^T, hyphenation, spelling)
  CASTBL 0EA5h  count + (upper, lower) pairs for codes >= 80h; room for 16 pairs only, and the
                FFh redirect described in PATCH.LST is not implemented in the code. The table is
                therefore moved to EXTRA (0FB8h, 512 free bytes) and the four references to 0EA5h
                in UPPER (31D3h, 31DDh) and LOWER (320Bh, 3215h) are pointed there.
  MOVCHR 0E7Ch  already contains every code 80h-FEh: unchanged.
The original WS.EXE is not modified.
"""
import os
import sys

UA = 0x600                                      # file offset of user-area address 0
LGLCHR, CASTBL, EXTRA = 0xE5C, 0xEA5, 0xFB8
REFS = {0x31D3: b'\x2e\x80\x3e', 0x31DD: b'\xbe', 0x320B: b'\x2e\x80\x3e', 0x3215: b'\xbe'}  # opcode before the address
CP437_LGL = bytes.fromhex('ffffffe0ff00000000000000fff0000c')   # LGLCHR bytes for 80h-FFh
CP437_CAS = bytes.fromhex('0880878e848f86908292919994' '9a81a5a4')
OUT = {'cp1125': 'WSU.EXE', 'cp866': 'WSR.EXE'}


def pairs(cp):
    """(upper, lower) byte pairs for the letters 80h-FFh of a code page."""
    res = []
    for b in range(0x80, 0x100):
        ch = bytes([b]).decode(cp)
        if ch.isalpha() and ch.isupper():
            res.append((b, ch.lower().encode(cp)[0]))
    return res


def letters(cp):
    return [b for b in range(0x80, 0x100) if bytes([b]).decode(cp).isalpha()]


def patch(src, cp):
    d = bytearray(open(src, 'rb').read())
    assert d[UA + 0x11B8:UA + 0x11BB] == b'\x01\x13\x57', 'not a WS 4.00 user area (UDATE)'
    assert d[UA + LGLCHR + 16:UA + LGLCHR + 32] == CP437_LGL, 'LGLCHR is not the cp437 default'
    assert d[UA + CASTBL:UA + CASTBL + len(CP437_CAS)] == CP437_CAS, 'CASTBL is not the cp437 default'
    assert d[UA + EXTRA:UA + EXTRA + 0x200] == bytes(0x200), 'EXTRA is in use'
    for a, op in REFS.items():
        assert d[UA + a:UA + a + len(op) + 2] == op + CASTBL.to_bytes(2, 'little'), hex(a)
    lgl = bytearray(16)
    for b in letters(cp):
        lgl[(b - 0x80) >> 3] |= 0x80 >> (b & 7)
    d[UA + LGLCHR + 16:UA + LGLCHR + 32] = lgl
    p = pairs(cp)
    d[UA + EXTRA:UA + EXTRA + 1 + 2 * len(p)] = bytes([len(p)]) + b''.join(bytes(x) for x in p)
    for a, op in REFS.items():
        d[UA + a + len(op):UA + a + len(op) + 2] = EXTRA.to_bytes(2, 'little')
    return bytes(d), len(p)


def check(exe, cp):
    """Call UPPER (31C8h) and LOWER (31FBh) of the patched EXE for every byte; compare with the code page."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_16
    from unicorn.x86_const import UC_X86_REG_AX, UC_X86_REG_CS, UC_X86_REG_SS, UC_X86_REG_SP
    img = open(exe, 'rb').read()[UA:]
    up = {l: u for u, l in pairs(cp)}
    low = {u: l for u, l in pairs(cp)}
    mu = Uc(UC_ARCH_X86, UC_MODE_16)
    mu.mem_map(0x10000, 0x40000)
    mu.mem_write(0x10000, img)
    bad = []
    for fn, want in ((0x31C8, lambda c: c ^ 0x20 if 0x61 <= c <= 0x7A else up.get(c, c)),
                     (0x31FB, lambda c: c ^ 0x20 if 0x41 <= c <= 0x5A else low.get(c, c))):
        for c in range(256):
            mu.reg_write(UC_X86_REG_CS, 0x1000); mu.reg_write(UC_X86_REG_SS, 0x4000)
            mu.reg_write(UC_X86_REG_SP, 0xFFFE); mu.mem_write(0x4FFFE, b'\xf0\xff')   # return to CS:FFF0
            mu.reg_write(UC_X86_REG_AX, c)
            mu.emu_start(0x10000 + fn, 0x10000 + 0xFFF0)
            got = mu.reg_read(UC_X86_REG_AX) & 0xFF
            if got != want(c):
                bad.append((hex(fn), hex(c), hex(got), hex(want(c))))
    lgl = img[LGLCHR + 16:LGLCHR + 32]
    word = [b for b in range(0x80, 0x100) if lgl[(b - 0x80) >> 3] & (0x80 >> (b & 7))]
    assert word == letters(cp), 'LGLCHR'
    assert not bad, bad[:10]
    return len(up)


def main(args):
    if args[:1] == ['--check']:
        print(args[1], args[2], 'UPPER/LOWER for 256 codes and LGLCHR OK,', check(args[1], args[2]), 'pairs')
        return
    src = args[0]
    for cp, name in OUT.items():
        data, n = patch(src, cp)
        dst = os.path.join(os.path.dirname(os.path.abspath(src)), name)
        open(dst, 'wb').write(data)
        print('%s: %s, %d case pairs in EXTRA, LGLCHR %d letters' % (name, cp, n, len(letters(cp))))


if __name__ == '__main__':
    main(sys.argv[1:])
