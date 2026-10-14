"""Patch WordStar 4 WSSPELL.OVR to check Cyrillic words against a cyrdct.py dictionary.

  python cyrovl.py WSSPELL.OVR OUT.OVR [--dict UK.DCT] [--cp cp1125] [--letters uk]
  python cyrovl.py WSSPELL.OVR OUT.OVR --dict RU.DCT --cp cp866 --letters ru

Changes to the original (CorrectStar 3.0, 23520 bytes, SHA-256 below):
  3A59h  7Fh -> FFh      PERSONAL.DCT reader keeps bit 7 (Cyrillic words load)
  37BCh  jmp check       the word check, after the PERSONAL cache and INTERNAL
                         miss and before the MAIN lookup / 21-letter limit:
                         a word with any byte >= 80h is looked up in the
                         dictionary file; found -> 37B4h (return 1), else 3858h
                         (return 2). ASCII words take the original path.
  09E0h  jmp sugg        the suggestion generator: for a Cyrillic word, fill the
                         engine's suggestion string (1B49h, space-separated) with
                         dictionary words one edit away (transposition, deletion,
                         substitution, insertion; at most MAXS, no duplicates).
                         The engine's own pop (0AAFh) and case fix (357Fh) then
                         hand them out as usual.
  011Bh  heap start      1F50h -> past the appended code and buffers
  5BE0h  appended code + data (file offset = CS offset; DS = CS + 3C9h)
The dictionary is opened per check / per suggestion batch and closed again (no
state survives overlay swapping). The file name is used as is, relative to the
current directory unless it contains a path.
"""
import argparse
import hashlib
import re

from gas16 import assemble

SHA = '7c9ce0a1f5ead66c00850f1e0c52a61d999c13a9bed68ef5f8bb91c1f2a48299'
ORG = 0x5BE0            # original file size: appended code starts here
DSEG = 0x3C90           # file offset of the data segment
CHECK = 0x37BC
SUGG = 0x9E0
MAXS = 8                # suggestions per word
MAXW = 40               # longest word that gets suggestions
UK = "абвгґдеєжзиіїйклмнопрстуфхцчшщьюя'"
RU = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'

SRC = r'''
.set J_SHORT, base + 0x37ca - ORG
.set J_LONG,  base + 0x37c2 - ORG
.set J_FOUND, base + 0x37b4 - ORG
.set J_NOTF,  base + 0x3858 - ORG
.set J_9E6,   base + 0x09e6 - ORG
.set TOLOWER, base + 0x059d - ORG        # AL -> AL through the WS.EXE callback
.set SBUF,    0x1b49                     # engine suggestion string
.set SATTR,   0x1eff                     # engine per-suggestion case bytes
.set STRAT,   0x1b3d                     # engine strategy counter (6 = exhausted)

    .byte 0xe9; .word check - . - 2     # ORG+0: entry from 37BCh
    .byte 0xe9; .word sugg - . - 2      # ORG+3: entry from 09E0h

# ---- word check ------------------------------------------------------------
check:                          # replaces: cmp word [bp+36h],15h / jle 37CAh
    mov cx, [bp+0x36]
    lea si, [bp+6]
    xor bl, bl
    jcxz 2f
1:  lodsb
    or bl, al
    loop 1b
    test bl, 0x80
    jnz 3f
2:  cmp word ptr [bp+0x36], 0x15
    jle J_SHORT
    jmp J_LONG
3:  push ds
    pop es
    lea ax, [bp+6]
    mov @qptr, ax
    mov ax, [bp+0x36]
    mov @qlen, ax
    call dopen
    jc 4f
    call find
    push ax
    call dclose
    pop ax
    or al, al
    jz 4f
    jmp J_FOUND
4:  jmp J_NOTF

# ---- suggestion generator ----------------------------------------------------
sugg:                           # replaces: push bp / sub sp,6 / mov bp,sp
    mov bx, sp
    mov si, [bx+2]              # parameter block
    lea di, [si+2]
    xor dl, dl
    xor cx, cx
1:  mov al, [di]
    or al, al
    jz 2f
    or dl, al
    inc di
    inc cx
    jmp 1b
2:  test dl, 0x80
    jnz 3f
    push bp
    sub sp, 6
    mov bp, sp
    jmp J_9E6
3:  push ds
    pop es
    mov @pp, si
    mov @n, cx
    mov byte ptr [SBUF], 0
    mov word ptr [si+0x4a], SBUF
    mov word ptr [si+0x48], 0
    mov word ptr [STRAT], 6
    mov @optr, SBUF
    mov @ocnt, 0
    mov di, SATTR
    mov cx, MAXS
    xor al, al
    rep stosb
    cmp @n, MAXW
    ja 6f
    add si, 2                   # lowercase copy of the word
    mov di, &wl
    mov cx, @n
4:  lodsb
    push cx
    push si
    push di
    call TOLOWER
    pop di
    pop si
    pop cx
    stosb
    loop 4b
    push ds
    pop es
    mov @qptr, &cb
    call dopen
    jc 6f
    call gen
    call dclose
    mov di, @optr
    mov byte ptr [di], 0
6:  mov si, @pp
    cmp byte ptr [SBUF], 0
    je 7f
    xor ax, ax
    ret
7:  mov byte ptr [si+0x26], 0
    mov ax, 1
    ret

gen:
    mov @i, 0                   # transpositions
1:  mov ax, @i
    inc ax
    cmp ax, @n
    jae 3f
    call cpw
    mov bx, @i
    mov al, byte ptr [bx + &cb]
    mov ah, byte ptr [bx + &cb + 1]
    cmp al, ah
    je 2f
    mov byte ptr [bx + &cb], ah
    mov byte ptr [bx + &cb + 1], al
    call try
    jc 9f
2:  inc @i
    jmp 1b
# per position i = 1, 2, ..., n, then 0 (a wrong first letter is the rarest typo):
# deletion at i, substitutions at i, insertions before i
3:  mov ax, @n
    inc ax
    mov @np, ax
    mov @k, 1
4:  call posk
    jc 9f
    mov ax, @i
    cmp ax, @n
    jae 6f                      # i = n: only an insertion at the end
    mov si, &wl                 # deletion
    mov di, &cb
    mov cx, @i
    rep movsb
    inc si
    mov cx, @n
    sub cx, @i
    dec cx
    rep movsb
    mov ax, @n
    dec ax
    mov @qlen, ax
    call try
    jc 9f
    mov @ci, &alpha             # substitutions
52: mov si, @ci
    mov al, [si]
    or al, al
    jz 6f
    inc @ci
    mov bx, @i
    cmp al, byte ptr [bx + &wl]
    je 52b
    push ax
    call cpw
    pop ax
    mov bx, @i
    mov byte ptr [bx + &cb], al
    call try
    jc 9f
    jmp 52b
6:  mov @ci, &alpha             # insertions
62: mov si, @ci
    mov al, [si]
    or al, al
    jz 63f
    inc @ci
    mov si, &wl
    mov di, &cb
    mov cx, @i
    rep movsb
    stosb
    mov cx, @n
    sub cx, @i
    rep movsb
    mov ax, @n
    inc ax
    mov @qlen, ax
    call try
    jc 9f
    jmp 62b
63: inc @k
    jmp 4b
9:  ret

posk:                           # i = k < np ? k : 0 (k = np); CF when k > np
    mov ax, @k
    cmp ax, @np
    ja 2f
    jb 1f
    xor ax, ax
1:  mov @i, ax
    clc
    ret
2:  stc
    ret

cpw:                            # cb = wl, qlen = n
    mov si, &wl
    mov di, &cb
    mov cx, @n
    rep movsb
    mov ax, @n
    mov @qlen, ax
    ret

try:                            # cb/qlen in the dictionary, suggestible and new -> append; CF = full
    call find
    or al, al
    jz 8f
    cmp @nosug, 0
    jne 8f
    mov di, SBUF
1:  cmp di, @optr               # duplicate check against the entries so far
    jae 5f
    mov si, &cb
    mov cx, @qlen
2:  cmp di, @optr
    je 3f
    mov al, [di]
    cmp al, ' '
    je 3f
    jcxz 4f
    cmp al, [si]
    jne 4f
    inc di
    inc si
    dec cx
    jmp 2b
3:  jcxz 8f
4:  cmp di, @optr
    jae 5f
    mov al, [di]
    inc di
    cmp al, ' '
    jne 4b
    jmp 1b
5:  mov di, @optr
    cmp @ocnt, 0
    je 6f
    mov al, ' '
    stosb
6:  mov si, &cb
    mov cx, @qlen
    rep movsb
    mov @optr, di
    inc @ocnt
    cmp @ocnt, MAXS
    jae 9f
8:  clc
    ret
9:  stc
    ret

# ---- dictionary --------------------------------------------------------------
dopen:                          # CF on error
    mov dx, &fname
    mov ax, 0x3d00
    int 0x21
    jc 1f
    mov @hnd, ax
    mov bx, ax
    mov ax, 0x4202
    xor cx, cx
    xor dx, dx
    int 0x21
    jc 2f
    mov cl, 9
    shr ax, cl
    mov cl, 7
    shl dx, cl
    or ax, dx
    mov @nblk, ax
    mov @curblk, 0xffff
    clc
1:  ret
2:  call dclose
    stc
    ret

dclose:
    mov bx, @hnd
    mov ah, 0x3e
    int 0x21
    ret

find:                           # AL = 1 if qptr/qlen is in the dictionary
    mov @lo, 0
    mov ax, @nblk
    mov @hi, ax
    or ax, ax
    jz 8f
1:  mov ax, @hi                 # last block whose first word <= query
    sub ax, @lo
    cmp ax, 1
    jbe 3f
    shr ax, 1
    add ax, @lo
    mov @mid, ax
    call rdblk
    jc 8f
    mov di, &buf + 1
    call cmpw
    mov bx, @mid
    cmp al, 2
    je 2f
    mov @lo, bx
    jmp 1b
2:  mov @hi, bx
    jmp 1b
3:  mov ax, @lo
    call rdblk
    jc 8f
    mov si, &buf
4:  cmp si, &buf + 512
    jae 8f
    lodsb                       # prefix length + nosugg bit
    cmp al, 0xff
    je 8f
    mov ah, al
    and ah, 0x80
    mov byte ptr [&nosug], ah
    and al, 0x7f
    xor ah, ah
    mov di, &cur
    add di, ax
5:  lodsb                       # suffix, with its 00h
    stosb
    or al, al
    jnz 5b
    push si
    mov di, &cur
    call cmpw
    pop si
    or al, al
    jz 9f
    cmp al, 2
    jne 4b
8:  xor al, al
    ret
9:  mov al, 1
    ret

# DI = 00h-terminated entry vs query qptr/qlen: AL = 0 equal, 1 entry <, 2 entry >
cmpw:
    mov si, @qptr
    mov cx, @qlen
1:  mov al, [di]
    or al, al
    jz 2f
    jcxz 4f
    cmp al, [si]
    ja 4f
    jb 3f
    inc di
    inc si
    dec cx
    jmp 1b
2:  jcxz 5f
3:  mov al, 1
    ret
4:  mov al, 2
    ret
5:  xor al, al
    ret

rdblk:                          # AX = block -> buf (cached), CF on error
    cmp ax, @curblk
    je 1f
    push ax
    mov dx, ax
    mov cl, 9
    shl dx, cl
    mov cl, 7
    shr ax, cl
    mov cx, ax
    mov bx, @hnd
    mov ax, 0x4200
    int 0x21
    jc 2f
    mov ah, 0x3f
    mov bx, @hnd
    mov cx, 512
    mov dx, &buf
    int 0x21
    jc 2f
    cmp ax, 512
    jne 2f
    pop ax
    mov @curblk, ax
1:  clc
    ret
2:  pop ax
    mov @curblk, 0xffff
    stc
    ret

# ---- data --------------------------------------------------------------------
hnd:    .word 0
nblk:   .word 0
curblk: .word 0
lo:     .word 0
hi:     .word 0
mid:    .word 0
qptr:   .word 0
qlen:   .word 0
pp:     .word 0
n:      .word 0
i:      .word 0
ci:     .word 0
k:      .word 0
np:     .word 0
nosug:  .word 0
optr:   .word 0
ocnt:   .word 0
fname:  .byte FNAME
        .space 64 - (. - fname)
alpha:  .byte ALPHA
        .space 64 - (. - alpha)
wl:     .space 64
cb:     .space 64
cur:    .space 64
buf:    .space 512
'''


def patch(img, off, old, new):
    assert img[off:off + len(old)] == old, hex(off)
    img[off:off + len(new)] = new


def jmp(frm, to):
    return b'\xe9' + ((to - (frm + 3)) & 0xFFFF).to_bytes(2, 'little')


def build(src_ovl, dict_name='UK.DCT', cp='cp1125', letters=UK):
    img = bytearray(src_ovl)
    assert hashlib.sha256(img).hexdigest() == SHA, 'not the original WSSPELL.OVR'
    name, alpha = dict_name.encode('ascii'), letters.encode(cp)
    assert len(name) < 64 and len(alpha) < 64
    d = r'(\1 - base + ORG - %#x)' % DSEG                    # DS offset of a label
    src = re.sub(r'&(\w+)', d, SRC)                            # &x = offset
    src = re.sub(r'@(\w+)', 'word ptr [%s]' % d, src)          # @x = word variable
    src = (src.replace('MAXS', str(MAXS)).replace('MAXW', str(MAXW))
           .replace('FNAME', ','.join(map(str, name + b'\0')))
           .replace('ALPHA', ','.join(map(str, alpha + b'\0'))))
    code = assemble(src, ORG)
    assert code[0] == code[3] == 0xE9                          # near jumps at +0, +3
    patch(img, 0x3A58, b'\x25\x7f\x00', b'\x25\xff\x00')
    patch(img, CHECK, bytes.fromhex('837e36157e08'), jmp(CHECK, ORG) + b'\x90' * 3)
    patch(img, SUGG, bytes.fromhex('5583ec068bec'), jmp(SUGG, ORG + 3) + b'\x90' * 3)
    patch(img, 0x11A, b'\xbb\x50\x1f', b'\xbb' + (ORG + len(code) - DSEG).to_bytes(2, 'little'))
    return bytes(img + code)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('ovl')
    ap.add_argument('out')
    ap.add_argument('--dict', default='UK.DCT')
    ap.add_argument('--cp', default='cp1125')
    ap.add_argument('--letters', default='uk', help='suggestion alphabet: uk, ru or the letters themselves')
    a = ap.parse_args()
    out = build(open(a.ovl, 'rb').read(), a.dict, a.cp, {'uk': UK, 'ru': RU}.get(a.letters, a.letters))
    open(a.out, 'wb').write(out)
    print(f'{a.out}: {len(out)} bytes, dictionary {a.dict}')
