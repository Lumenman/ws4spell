"""Assemble 16-bit Intel-syntax code with GNU as (binutils, any x86 target) into a flat binary.

Symbols outside the code are written as `base + (ADDR - ORG)`, so every jump stays
PC-relative inside one section and no linker is needed.
"""
import os
import subprocess
import tempfile


def assemble(src, org=0):
    pre = '.code16\n.arch i8086,jumps\n.intel_syntax noprefix\nbase:\n.set ORG, %#x\n' % org
    with tempfile.TemporaryDirectory() as d:
        s, o, b = (os.path.join(d, n) for n in ('a.s', 'a.o', 'a.bin'))
        open(s, 'w').write(pre + src + '\n')
        subprocess.run(['as', '-o', o, s], check=True)
        subprocess.run(['objcopy', '-O', 'binary', '-j', '.text', o, b], check=True)
        return open(b, 'rb').read()
