"""Emulate WordStar 4 WSSPELL.OVR (CorrectStar 3.0) with real dictionary files (Unicorn).

  python emu4.py WSDIR      smoke test: load the dictionaries, check a few words

The overlay is a raw image (ORG 0). Entry points: 80h=init (copies 16 bytes
DS:SI -> data[5Fh]), 83h=dispatch (BL=function), 86h=retf stub.
Data segment = CS + 3C9h. All parameters live at fixed offsets in the data area:
  [0]=fn [1]=wordlen [2..]=word [4Ch]=INTERNAL handle [4Eh]=PERSONAL handle
  [50h]=MAIN handle [55h]=status.
"""
import os
import sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn.x86_const import *

SEG = 0x3000
IMG = SEG * 16
DATA = SEG + 0x3C9          # data segment
DIMG = DATA * 16            # linear of data offset 0
RETSEG, RETOFF = 0xF000, 0xFFF0

FILES = {5: 'MAIN.DCT', 6: 'INTERNAL.DCT', 7: 'PERSONAL.DCT'}     # DOS handle -> file


class Ovl:
    def __init__(s, wsdir, trace_io=True, img=None):
        s.img = img or open(os.path.join(wsdir, 'WSSPELL.OVR'), 'rb').read()
        s.mu = mu = Uc(UC_ARCH_X86, UC_MODE_16)
        mu.mem_map(0, 0x100000)
        mu.mem_write(IMG, s.img)
        # far return landing pad
        mu.mem_write(RETSEG * 16 + RETOFF, b'\xf4')  # hlt, caught by hook
        s.files = {h: open(os.path.join(wsdir, p), 'rb').read() for h, p in FILES.items()}
        s.pos = {h: 0 for h in FILES}
        s.trace_io = trace_io
        s.trace = False
        s.hooks = {}
        s.ring = []
        s.wild = False
        mu.hook_add(UC_HOOK_INTR, s.intr)
        mu.hook_add(UC_HOOK_CODE, s.code)
        mu.reg_write(UC_X86_REG_SS, 0x7000)
        mu.reg_write(UC_X86_REG_SP, 0xFFFE)

    # ---- helpers ----
    def rb(s, off):
        return s.mu.mem_read(DIMG + off, 1)[0]

    def wb(s, off, v):
        s.mu.mem_write(DIMG + off, bytes([v & 0xFF]))

    def rw(s, off):
        return int.from_bytes(s.mu.mem_read(DIMG + off, 2), 'little')

    def ww(s, off, v):
        s.mu.mem_write(DIMG + off, (v & 0xFFFF).to_bytes(2, 'little'))

    def wmem(s, off, b):
        s.mu.mem_write(DIMG + off, bytes(b))

    def rmem(s, off, n):
        return bytes(s.mu.mem_read(DIMG + off, n))

    # ---- DOS ----
    def intr(s, mu, n, _):
        if n != 0x21:
            raise RuntimeError('int %x' % n)
        ah = mu.reg_read(UC_X86_REG_AH)
        bx = mu.reg_read(UC_X86_REG_BX)
        if ah == 0x3F:  # read
            cx = mu.reg_read(UC_X86_REG_CX)
            dx = mu.reg_read(UC_X86_REG_DX)
            ds = mu.reg_read(UC_X86_REG_DS)
            data = s.files.get(bx, b'')[s.pos[bx]:s.pos[bx] + cx]
            mu.mem_write(ds * 16 + dx, data)
            s.pos[bx] += len(data)
            mu.reg_write(UC_X86_REG_AX, len(data))
            if s.trace_io:
                print(f'  READ  h={bx} off={s.pos[bx]-len(data):#x} want={cx:#x} got={len(data):#x} -> {ds:#x}:{dx:#x}')
        elif ah == 0x42:  # seek
            al = mu.reg_read(UC_X86_REG_AL)
            off = (mu.reg_read(UC_X86_REG_CX) << 16) | mu.reg_read(UC_X86_REG_DX)
            base = [0, s.pos[bx], len(s.files.get(bx, b''))][al]
            s.pos[bx] = (base + off) & 0xFFFFFFFF
            mu.reg_write(UC_X86_REG_AX, s.pos[bx] & 0xFFFF)
            mu.reg_write(UC_X86_REG_DX, s.pos[bx] >> 16)
            if s.trace_io:
                print(f'  SEEK  h={bx} mode={al} -> {s.pos[bx]:#x}')
        elif ah == 0x40:  # write
            cx = mu.reg_read(UC_X86_REG_CX)
            dx = mu.reg_read(UC_X86_REG_DX)
            ds = mu.reg_read(UC_X86_REG_DS)
            data = bytes(mu.mem_read(ds * 16 + dx, cx))
            if s.trace_io:
                print(f'  WRITE h={bx} off={s.pos[bx]:#x} len={cx:#x}: {data[:64]!r}')
            s.pos[bx] += cx
            mu.reg_write(UC_X86_REG_AX, cx)
        elif ah == 0x3D:  # open: names from s.dosfs (upper-case name -> bytes)
            ds, dx = mu.reg_read(UC_X86_REG_DS), mu.reg_read(UC_X86_REG_DX)
            name = bytes(mu.mem_read(ds * 16 + dx, 80)).split(b'\0')[0].decode('ascii').upper()
            data = getattr(s, 'dosfs', {}).get(name)
            if data is None:
                mu.reg_write(UC_X86_REG_AX, 2)
                mu.reg_write(UC_X86_REG_EFLAGS, mu.reg_read(UC_X86_REG_EFLAGS) | 1)
                return
            h = max(s.files) + 1
            s.files[h], s.pos[h] = data, 0
            s.opened = getattr(s, 'opened', 0) + 1
            mu.reg_write(UC_X86_REG_AX, h)
        elif ah == 0x3E:
            if bx in s.files and bx > 7:
                del s.files[bx]
                s.opened -= 1
            if s.trace_io:
                print(f'  CLOSE h={bx}')
        else:
            raise RuntimeError('int 21h ah=%02x' % ah)
        mu.reg_write(UC_X86_REG_EFLAGS, mu.reg_read(UC_X86_REG_EFLAGS) & ~1)

    def code(s, mu, addr, size, _):
        if addr == RETSEG * 16 + RETOFF:
            mu.emu_stop()
            return
        if not (IMG <= addr < IMG + len(s.img) or 0x70200 <= addr < 0x70300):
            val = [a for a in s.ring if IMG + 0x80 <= a < IMG + 0x3C90]
            print('WILD JUMP to %05x; last in-code: %s' % (addr, ' '.join('%05x' % (a - IMG) for a in val[-12:])))
            mu.emu_stop()
            s.wild = True
            return
        s.ring.append(addr)
        if len(s.ring) > 20000:
            s.ring.pop(0)
        if addr >= IMG and addr < IMG + len(s.img):
            off = addr - IMG
            if off in s.hooks:
                s.hooks[off](s)

    def farcall(s, ip, **regs):
        mu = s.mu
        # push far return on current stack
        ss, sp = mu.reg_read(UC_X86_REG_SS), mu.reg_read(UC_X86_REG_SP)
        sp -= 2; mu.mem_write(ss * 16 + sp, RETSEG.to_bytes(2, 'little'))
        sp -= 2; mu.mem_write(ss * 16 + sp, RETOFF.to_bytes(2, 'little'))
        mu.reg_write(UC_X86_REG_SP, sp)
        for r, v in regs.items():
            mu.reg_write(r, v)
        mu.reg_write(UC_X86_REG_CS, SEG)
        try:
            mu.emu_start(IMG + ip, RETSEG * 16 + RETOFF + 1, count=200_000_000)
        except Exception as e:
            print('CRASH', e)
            print('ring from slide:', ' '.join('%05x' % a for a in s.ring[-200000:-199990]) if len(s.ring)>199990 else '')
            print('last addrs:', ' '.join('%05x' % a for a in s.ring[-30:]))
            val = [a for a in s.ring if IMG + 0x80 <= a < IMG + 0x3C90]
            print('last in-code:', ' '.join('%05x' % (a - IMG) for a in val[-25:]))
            if val:
                i = s.ring.index(val[-1])
                print('after last in-code:', ' '.join('%05x' % a for a in s.ring[i:i+12]))
            raise
        if mu.reg_read(UC_X86_REG_IP) != RETOFF or mu.reg_read(UC_X86_REG_CS) != RETSEG:
            val = [a for a in s.ring if IMG + 0x80 <= a < IMG + 0x3C90]
            print('last in-code:', ' '.join('%05x' % (a - IMG) for a in val[-25:]))
            if val:
                i = s.ring.index(val[-1])
                print('after last in-code:', ' '.join('%05x' % a for a in s.ring[i:i+12]))
            print('ring from slide:', ' '.join('%05x' % a for a in s.ring[-200000:-199990]) if len(s.ring)>199990 else '')
            print('last addrs:', ' '.join('%05x' % a for a in s.ring[-20:]))
            raise RuntimeError('did not return: cs:ip=%04x:%04x' % (mu.reg_read(UC_X86_REG_CS), mu.reg_read(UC_X86_REG_IP)))

    def init(s):
        # WS.EXE callbacks as a cp1125/cp866-patched WS.EXE provides them (AL in/out):
        # toupper, tolower (Latin, 80h-9Fh <-> A0h-AFh/E0h-EFh, F0h-F9h pairs) and the
        # letter test (ZF=0: a-z, A-Z, >= 80h); poll: ZF=1 (no abort)
        s.mu.mem_write(0x70230, bytes.fromhex('33 c0 cb'))
        s.mu.mem_write(0x70240, bytes.fromhex(
            '3c 80 73 0a 0c 20 3c 61 72 07 3c 7a 77 03 0c 01 cb 31 c0 cb'))
        s.mu.mem_write(0x70280, bytes.fromhex(
            '3c 41 72 24 3c 5a 76 1e 3c 80 72 1c 3c 8f 76 16 3c 90 72 14 3c 9f 76 0c'
            '3c f0 72 0c 3c f9 77 08 0c 01 eb 04 04 30 04 20 cb'))
        s.mu.mem_write(0x702c0, bytes.fromhex(
            '3c 61 72 24 3c 7a 76 1e 3c a0 72 1c 3c af 76 16 3c e0 72 14 3c ef 76 0c'
            '3c f0 72 0c 3c f9 77 08 24 fe eb 04 2c 30 2c 20 cb'))
        # 16-byte block at 0x7000:0 -> copied to data[5Fh]: far poll, toupper, tolower, class
        blk = b''.join(o.to_bytes(2, 'little') + (0x7010).to_bytes(2, 'little')
                       for o in (0x130, 0x1c0, 0x180, 0x140))
        s.mu.mem_write(0x70000, blk)
        s.mu.reg_write(UC_X86_REG_AX, 0x7000)
        s.mu.reg_write(UC_X86_REG_DS, 0x7000)
        s.mu.reg_write(UC_X86_REG_SI, 0)
        s.farcall(0x80)

    def fn(s, n):
        s.mu.reg_write(UC_X86_REG_BX, n)  # BL = function
        s.farcall(0x83)
        return s.rb(0x55)


def open_dicts(o):
    """Initialise the engine as WS.EXE does: handles, INTERNAL, MAIN, PERSONAL."""
    o.init()
    o.ww(0x4c, 6)   # INTERNAL.DCT
    o.ww(0x50, 5)   # MAIN.DCT
    o.ww(0x4e, 7)   # PERSONAL.DCT
    o.fn(28)        # load INTERNAL tables
    o.fn(22)        # select MAIN
    o.fn(13)        # load PERSONAL into the session cache


def check(o, word, cp='cp437'):
    """fn 2: 1 = found, 0 = not found."""
    b = word.encode(cp)
    o.wb(1, len(b))
    o.wmem(2, b + b'\0')
    return o.fn(2)


def suggestions(o, word, cp='cp437', most=20):
    """fn 2, then fn 5 / fn 6 until 'e' (65h)."""
    check(o, word, cp)
    out, st = [], o.fn(5)
    while st == 0x64 and len(out) < most:
        out.append(o.rmem(0x26, o.rb(0x25)).decode(cp))
        st = o.fn(6)
    return out


if __name__ == '__main__':
    o = Ovl(sys.argv[1], trace_io=False)
    open_dicts(o)
    res = {w: check(o, w) for w in ('the', 'zqwx', 'wordstar', 'dictionary')}
    print(res, suggestions(o, 'teh'))
    assert res == {'the': 1, 'zqwx': 0, 'wordstar': 1, 'dictionary': 1}
    assert 'the' in suggestions(o, 'teh')
    print('OK')
