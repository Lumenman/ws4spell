# WS4DCT: the dictionary format of WordStar 4.0 CorrectStar

A research specification, 2026-10-14. Sources: the files `MAIN.DCT`, `INTERNAL.DCT`,
`PERSONAL.DCT` of WordStar 4.0 and the spelling overlay `WSSPELL.OVR`
(**CorrectStar ver 3.0**, spelling engine (c) 1981, 1987 Houghton Mifflin),
disassembled statically and executed under a Unicorn harness with the real
dictionary files; every structural statement below was confirmed against the
emulated engine unless marked otherwise. Companion project: [wsspell](https://github.com/Lumenman/wsspell), `SPLMN_FORMAT.md`
(the WordStar 7 dictionaries — a completely different, Microlytics, format).

## Status and scope

Recovered: the overlay call protocol, the dispatch table, both hash functions, the
full layout of `INTERNAL.DCT` (suffix/trigram table, sector catalog, perfect-hash
frequent-word table, the suggestion Bloom filter), the phonetic transform used for
indexing, the 5-bit letter coding, and the complete record bitstream of `MAIN.DCT`.
A standalone Python decoder (`decode.py`) reproduces the engine's own
record decoding bit-exactly (verified record-by-record against the emulator) and
decodes the whole shipped dictionary: **60337 stored forms in 541 sectors**; with
the flag-driven endings (-s, -'s, -ing) this matches the advertised "87,000 words".

Not recovered / not needed for reading: the internal scoring heuristics of the
suggestion generator (the strategy jump table in function `13E8h`), the exact
semantics of the per-word attribute bitmap `f32` and of the 3-bit field `b4`
(both structurally fixed, below), and what the original compiler meant by table A
entries beyond what the decoder reads. This is **not** an official Houghton
Mifflin / MicroPro specification.

Scope: `WSSPELL.OVR`, `MAIN.DCT`, `INTERNAL.DCT`, `PERSONAL.DCT` of WordStar 4.0.
WordStar 7 (`SPLMN*.DCT`) is a different system; see the companion document.

## 1. Numbers, addresses and conventions

The overlay is a **raw image with ORG 0** (no EXE header): load it into a segment
and it runs. The data area is at `CS+3C9h` (file offset `3C90h`). Numbers inside
dictionary files are little-endian unless stated otherwise; the record bitstream
of `MAIN.DCT` is the exception (its 16-bit units are big-endian, MSB first).
Characters are bytes of the OEM code page, not UTF-8.

All overlay addresses below are file offsets (= load offsets), hexadecimal.

## 2. The overlay call protocol (WSSPELL.OVR)

Entry points:

```text
80h    init: copies 16 bytes DS:SI -> data[5Fh..6Eh] (four far callbacks into
       WS.EXE), initialises the engine
83h    dispatch: BL = function number 0..30; jump table of 31 words at file 879h
86h    far-ret stub (unused)
```

The parameter block **is** the overlay's own data area, starting at offset 0:

```text
[00]    function number (echo of BL)
[01]    word length
[02..]  word bytes, NUL-terminated
[24]    result byte (flags about the word form)
[25]    result length (suggestion length)
[26..]  suggestion buffer, NUL-terminated
[4C]    DOS handle of INTERNAL.DCT
[4E]    DOS handle of PERSONAL.DCT
[50]    DOS handle of MAIN.DCT
[55]    status byte (return value)
```

Files are opened and closed by WS.EXE; the overlay receives **handles** and only
does `read`/`seek` (and `write` for PERSONAL.DCT additions). The four callbacks
copied at init (data offsets `5F`, `63`, `67`, `6B`, all far pointers into
WS.EXE) are: poll/abort check (`ZF=1` = continue), `toupper`, `tolower`, and the
character-class test. All case mapping of dictionary text therefore belongs to
WS.EXE, not to the overlay — which is exactly why the Cyrillic-aware WS.EXE patch
(`patchcp.py`) already fixes case handling everywhere the overlay asks for it.

### 2.1 Dispatch table (file 879h, 31 words)

| fn | addr | role |
|---:|-----:|------|
| 0  | 61C | session/init helper |
| 2  | 61F | **check word** — status 1 found, 0 not found; result flags in [24] |
| 3  | 6FC | **add word to PERSONAL.DCT** (appends `word CR LF`, inserts into session cache); status 9 = cache full |
| 4  | 62A | check variant (used with 2) |
| 5  | 67A | **next suggestion**: generates a batch (≤6) if needed, pops one; status `64h`='d' suggestion in [26..], len [25]; `65h`='e' no more |
| 6  | 7AE | pop suggestion without generating |
| 13 | 818 | **session start**: loads PERSONAL.DCT into the session hash cache |
| 14 | 870 | nop |
| 15 | 857 | close/flush PERSONAL |
| 17 | 7F1 | aux (0BA5) |
| 19 | 74E | suggestion post-processing (case, trailing period) |
| 20 | 6AD | suggestion post-processing (case, trailing period) |
| 22 | 80D | **select MAIN dictionary**: reads sector 0, checks bytes 64h='3', 67h/68h=' ' of the "ver 3.0" banner |
| 24 | 7FC | aux (0BBB) |
| 27 | 84D | select MAIN (variant of 22) |
| 28 | 823 | **load INTERNAL.DCT** tables into heap |
| 29 | 872 | aux (029F) |
| 30 | 877 | nop |
| 1,7..12,16,18,21,23,25,26 | 8C5 | unimplemented stub |

Lookup order for fn 2: session cache (PERSONAL words) → INTERNAL frequent-word
hash → MAIN dictionary. A hit anywhere short-circuits; the MAIN path is never
reached for words found earlier.

## 3. The hash function (overlay 1FB2h)

Byte-oriented; no alphabet tables, no 7-bit masking. For word bytes
`c[0..n-1]`:

```text
h1_0 = c[0]
h1_i = (h1_{i-1} * 256 + c[i]) mod 7FEDh (32749)      i = 1..n-1
h2   = c[0] XOR h1_1 XOR h1_2 XOR ... XOR h1_{n-1}    (XOR of all intermediates)
```

(The machine code computes `h1*256 mod 7FEDh` as `19*(h1>>7) + (h1&7Fh)*256`,
because `8000h*100h ≡ 19 (mod 7FEDh)`.) Used for INTERNAL.DCT tables, the
PERSONAL session cache, and the suggestion filter. Cyrillic bytes pass through
unchanged — the hash layer is **not** what blocks Cyrillic.

## 4. INTERNAL.DCT (25600 bytes)

```text
0000h .. 01FFh   text header; at 0190h: ASCII "02.01.00", "04096" (= number of
                 hash slots -> data [0A50h]), "0576" (= catalog entries -> [0A52h])
0200h .. 0AFFh   table A: 2304 bytes = 1152 LE16 (suffix table; last 129 words
                 from 09FEh are the trigram table, see 6.3)
0B00h .. 13FFh   table B: 576 LE32 — the sector catalog of MAIN.DCT (sorted)
1400h .. 43FFh   table C: 12288 bytes = 4096 LE16 slots + 4096 tag bytes
                 (frequent-word perfect hash)
4400h .. 63FFh   table D: 8192 bytes (suggestion filter)
```

fn 28 reads the header sector, then the four tables, and closes the file;
INTERNAL.DCT is memory-resident afterwards ("24K Ram Table").

### 4.1 Table C — frequent-word perfect hash (4096 slots, 100% full)

Slot word at `1400h + 2*idx`, tag byte at `3400h + idx`:

```text
slot = (h1 & 3FFFh) | flags<<14        flags: 8000h = accept unconditionally,
                                         4000h = matches a de-suffixed query
tag  = ((h2 >> 8) & 70h) | wordlen     (low 4 bits = length, so words >15 chars
                                        alias the h2 bits; consistent both ways)
bit 7 of tag: set when the query form had "'s" stripped
```

Probe sequence: `idx0 = h2 & 0FFFh`, `step = (h1 & 0FFh) + 3`, `idx = (idx +
step) mod 4096`, **at most 3 probes**; empty slot = `FFFFh`, deleted = `7FFFh`.
The shipped table has all 4096 slots occupied — a perfect hash placed offline by
the compiler (verified: "the", "and", "from", "would", … all hit on probe 0).

### 4.2 Table D — suggestion filter (8192 bytes)

A Bloom-like membership filter consulted by the suggestion generator before
confirming a candidate against MAIN: slot `h2 & 0FFFh` in the first half stores
`h1 & 0FFh`; on mismatch two more probes in the second half at
`(idx + (h1&0FFh) + 3) mod 1000h` and again `(idx + step*2...)`. 8158 of 8192
bytes are nonzero in the shipped file. Lookup correctness does not depend on D;
absent or stale D only changes suggestion quality.

### 4.3 Table A — suffix table (1152 LE16) and trigram table

Used by the MAIN record decoder (6.2). Entry `e` for suffix records:

```text
bits 10..15   fl5 — ending flags (same layout as literal records, 6.4)
bits  6..9    prefix-keep count for the decoded word
bits  0..5    attribute bits -> flags32 bits 10..15
```

The last 129 words (file 09FEh..0AFFh, `A[1023..1151]`) form the trigram table:
each word packs three 5-bit letter codes; a stream byte with bit7 set selects
entry `(byte & 7Fh) - 1`.

## 5. The phonetic index (overlay 27F3h + collation table)

MAIN.DCT is **not** alphabetically organised. It is indexed by a phonetic key:

1. the word is lowercased (WS.EXE callback);
2. function `27F3h` rewrites it by a long pipeline of context rules — a
   phonetic respelling. Observed rules include: soft `c`→`s` before e/i/y
   (`cent`→`sent`…), `qu`→`kw`, leading `wr`/`wh` reductions, `kn`→`n`,
   `gn`→`n`, `ps`→`s`, deduplication of double consonants, `z`→`s` except
   word-initially, vowels converted to **uppercase marker letters** whose choice
   depends on position and context (`a,e,i,o,u` → `E,I,O,W,Y,_` variants;
   trailing reduced vowels → `_`);
3. each character of the respelled form is mapped through the 128-byte
   collation table at data `0A54h` (in the overlay image): consonants keep
   order (b=2, d=4, f=6, …, z=1Ah), vowel markers get 1,5,9,0Fh,15h, `_`=1Fh,
   `'`=1Bh, `-`=1Ch, `.`=1Dh, `/`=1Eh, everything else = 0;
4. the first six codes pack MSB-first into the 30-bit key
   `k = c0<<25 | c1<<20 | … | c5`, zero-padded.

Examples (obtained by executing 27F3h under Unicorn, about 4 ms per word):

```text
zzzqqq -> zsq       key 35388000     knight -> nEt      key 1C5A0000
monkey -> mOnkY     key 1AF72C20     aardvark -> _rdvWrk key 3F225AB2
cat    -> kIt       key 169A0000     psychology -> sEkhlgY key 2655A187
```

The phonetic transform is pure computation (no I/O, no callbacks), so the
emulated routine can serve as the key oracle for any dictionary compiler.

## 6. MAIN.DCT (277504 bytes = 542 sectors)

```text
sector 0 (0000h..01FFh)   text header ("ver 3.0" banner; checked by fn 22/27)
sectors 1..541            record bitstream, 512 bytes each, self-contained
                          (prefix state resets at every sector load)
tail                      padding FFh
```

### 6.1 Routing: catalog B

`catalog[i]` (INTERNAL.DCT table B) is the phonetic key of the first record of
**sector i+1**; `catalog[0] = 0` covers sector 1; entries past the last sector
are `3FFFFFFFh` sentinels. The binary search (overlay 0EF7h, 32-bit signed
compares) returns the sector to scan; when the key exactly equals catalog
entries the scan extends over the following sectors sharing that key (duplicate
walk in 0EF7h; sector countdown in the scanner). Confirmed empirically:
481 of 541 entries equal the runtime key of the sector's first word exactly; the
remaining 60 differ only in the treatment of a **trailing `_`** (the compiler's
phonetic version dropped it, the runtime keeps it) — the entries remain valid
lower bounds and lookups route correctly.

The sector scan is **linear**: every record is decoded and compared as exact
letter codes plus ending-flag compatibility (overlay 1B91h). Word order inside a
sector is irrelevant to lookup correctness (it is phonetic-key-ish, but the
engine does not rely on it for fn 2; the byte-window skipping of the scanner is
used in suggestion mode only).

### 6.2 Record bitstream

Per sector: a sequence of big-endian 16-bit units, MSB consumed first; the LSB
of several units is a flag/continuation bit. Cursor is a byte offset into the
sector buffer. First unit `w0`:

**Suffix form** (`w0 & 8000h`): the word is a suffix-table expansion.

```text
e      = A[((w0 & 7FE0h) >> 5) - 1]       (table A entry, LE16)
fl5    = (e >> 10) & 3Fh                  ending flags
prefix = (e >> 6) & 0Fh                   letters kept from previous word
flags32 |= (e & 3Fh) << 10
cont   = w0 & 1
n_new  = (w0 >> 1) & 0Fh                  new letters in this record
b4     = 0
```

**Literal form** (`w0 & 8000h == 0`):

```text
fl5    = (w0 >> 9) & 3Fh
b4     = w0 & 7
flags32 |= (w0 & 1F8h) << 7
w1     = next unit
n_new  = (w1 >> 11) & 1Fh
prefix = (w1 >> 6) & 1Fh
cont   = w1 & 1
```

Letters then follow, `rem = n_new mod 3` first:

```text
rem = 1:  literal — the code is already in the header: (w1 >> 1) & 1Fh
          suffix  — one stream byte b: code (b >> 3) & 1Fh,
                    flags32 |= (b & 6) << 7, cont = b & 1, d = 8
rem = 2:  one unit w2: codes (w2 >> 11) & 1Fh, (w2 >> 6) & 1Fh,
                    flags32 |= (w2 & 3Eh) << 4, cont = w2 & 1, d = 0Bh
then while letters < n_new, three codes per step:
          byte b0 with bit7 set   -> trigram table T[(b0 & 7Fh) - 1] = 3 codes
          else b0 and next byte b1: w = (b0 << 8) | b1,
                    codes (w >> 10) & 1Fh, (w >> 5) & 1Fh, w & 1Fh
```

Flag trailer, only when the running `cont` bit is 0 (`d` is 6 initially, 8 or
0Bh above; `flags32` accumulates attribute bits):

```text
read two stream bytes as a little-endian word w3
flags32 |= (w3 & FEh) << (8 - d)   if d <= 8,  else << (d - 8)
d += 7
if w3 & 1:  only ONE byte was consumed (step back)
else:       flags32 |= (((w3 >> 8) & FEh) >> (d - 8))
```

Final: `f32 = (flags32 & FFFFh) << 16` (the engine stores it as the high word of
a 32-bit attribute field; semantics opaque, suggestion-side). The decoded word
is `prev_word[0 : prefix] + new_codes`; `prev_word` persists per sector.
Terminator: unit `FFFFh`, or cursor beyond 201h.

### 6.3 Letter codes

```text
1..26 = a..z      27 = '      28 = -      29 = .      30 = /
0 = padding (renders as backquote)     31 = unused (renders as 7Fh)
```

31 symbols maximum — the alphabet of the whole system is a 5-bit channel.

### 6.4 Ending flags `fl5` (applied at display/compare time)

```text
(fl5 & 03h) == 01h      append "s"
(fl5 & 0Ch) == 04h      append "'s"
(fl5 & 30h) == 10h      append "ing"
```

Query-side matching is mirrored: before keying, the engine strips `ing` / `'s` /
`s` from the query and requires `(record_fl5 & strip_flag) != 0`, or — for an
unstripped query — rejects records whose flags claim endings the query doesn't
have (the `~fl5 & … & 15h` test at 1BACh).

### 6.5 Decoded inventory (shipped US dictionary)

60337 records; word-length histogram peaks at 8 letters (9410); longest 20+.
Example sector 426 (the "z/s" phonetic bucket): zinced, zionism, zaniest,
zionist, zenith, zinnia, zapp(+ing), zipp(+ing), zippy, zapped, zipped,
zeppelin, zippines(+s), zipper, …, zwiebacks, 'ti(+s), a, as. `python decode.py WSDIR`
lists every stored form.

## 7. PERSONAL.DCT and the session cache

Plain text, one word per line, CRLF, read until EOF or ^Z; shipped file contains
just `WordStar`. A word is a run of characters the WS.EXE class callback accepts,
plus `.`, `-`, `'`; length 2..32. Bit 7 of every byte is stripped on read (see 8.5).
fn 13 loads it into the session hash cache: 1280 slots (u16 + tag byte each) at
data 0C24h/1624h, modulus 4FFh…0500h, same h1/h2 and slot layout as table C
(bits 14-15 of the slot carry source flags). fn 3 appends to the file and
inserts into the cache; status 9 when the cache is full. Practical ceiling is
about a thousand words — this is the "user dictionary limitation" visible from
WordStar itself.

## 8. Cyrillic: what exactly stands in the way

Tested both by emulation and by reading the code:

1. **The MAIN lookup rejects any byte > 7Fh.** Overlay 2365h (inside 21E9h):
   `cmp ax, 7Fh; jle ok; return 0` — a Cyrillic word never reaches the scanner.
   One-byte patches can remove this, but:
2. **The alphabet is 5-bit.** 31 codes for letters; Russian needs 33 (32 without
   ё). No flag bit anywhere buys a 6th bit: the packing (3 codes per 15 bits,
   trigram bytes, suffix table) is built around 5. Widening it means rewriting
   the decoder — a different overlay.
3. **The index is English phonetics.** Routing keys come from the 27F3h
   respelling of English orthography; a Russian MAIN.DCT would need a Russian
   respelling *and* a patched key computation.
4. **INTERNAL.DCT table C is byte-clean.** Cyrillic words hash and probe fine
   (verified in emulation: the INTERNAL probe of a cp866 word runs to the MAIN
   stage, which then rejects it at the 7Fh check). Capacity: 4096 slots, 3
   probes — a perfect-hash placement is required; realistically the ceiling for
   a hand-built Cyrillic INTERNAL is ~3-4 thousand words.
5. **PERSONAL.DCT is not byte-clean on load.** The file reader (39DCh) returns
   each byte `and ax, 7Fh` (file 3A58h: `25 7F 00`), so cp866/cp1125 letters lose
   bit 7 and the tokenizer (38A4h) splits the word. Words added during a session
   go straight into the cache and work until the next load. One-byte fix: file
   3A59h `7Fh` -> `FFh`; verified in emulation by `personal_cyr.py`
   (stock: Cyrillic missed, patched: found, absent words still rejected) and
   in DOSBox-X with the cp1125 WSU.EXE (^QL skips the PERSONAL words, stops
   at the first absent one).
   Session cache ~1280 words.

So within the stock engine the honest ceilings are: ~5 KB worth of Cyrillic
vocabulary split between INTERNAL (fast, compiled) and PERSONAL (user). That is
a personal dictionary, not a spelling dictionary.

### Options for a real Cyrillic dictionary

A. **Replacement WSSPELL.OVR with the same ABI.** The whole contract is §2:
   init at 80h, dispatch at 83h, the parameter block, four callbacks, dictionary
   reads through the handle at [50h]. A clean-room overlay can keep WS.EXE
   (including the Cyrillic patches of `patchcp.py`) untouched and implement its own
   dictionary — e.g. the same SPLMN-derived machinery already built for WS7, or
   a simple byte-hashed word list with its own suggestion pass. Overlay budget:
   the loader reserves the segment for the largest overlay (SPSIZE ≈ 52K), ample
   for a spell engine + in-memory index.
B. **Deep patch of the stock overlay**: replace 21E9h/27F3h/173Ch with a
   byte-wise comparator over a custom MAIN.DCT. Same effort as A but inside
   foreign code — no upside except reusing the suggestion UI flow.
C. **INTERNAL-only Cyrillic** (option A0): build a 4096-word perfect-hash
   INTERNAL.DCT with the stock overlay; zero patching, works today, but the
   capacity is what it is.

### Implemented: hybrid (A') — stock engine for English, own branch for Cyrillic

`cyrovl.py` patches the original overlay (SHA-256 checked):

```text
3A59h  7Fh -> FFh     PERSONAL.DCT keeps bit 7
37BCh  jmp 5BE0h      in the word check (function around 36xxh), after the
                      PERSONAL cache and INTERNAL misses, before the 21-letter
                      limit and the MAIN lookup. [bp+6] = the word, already
                      lowercased by the WS.EXE callback, NUL-terminated;
                      [bp+36h] = its length. Return 1 (37B4h) = found,
                      2 (3858h) = not found.
09E0h  jmp 5BE3h      the suggestion generator (called by fn 5). For a
                      Cyrillic word it writes its own candidates into the
                      engine's suggestion string at 1B49h (space-separated,
                      pointer [param+4Ah], index [param+48h]), clears the case
                      bytes at 1EFFh and sets the strategy counter 1B3Dh = 6
                      (exhausted); the engine's pop (0AAFh, fn 5/6) and case
                      fix (357Fh, follows the query: Мовва -> Мова) do the rest.
                      Return 0 = some, 1 = none (and [param+26h] = 0).
011Bh  heap start     1F50h -> end of the appended block
5BE0h  appended       8086 code + data (about 1.8 KB, including the 512-byte
                      block buffer; the overlay stays far below SPSIZE = 52K)
```

A word containing any byte >= 80h is looked up in the dictionary file (default
`UK.DCT`, current directory; `--dict` sets another name or a full path). The
file is opened and closed per lookup, so no state has to survive overlay
swapping. ASCII words take the original path unchanged (suggestions included).
Suggestions: dictionary words one edit away, at most 8 (WordStar shows 6):
transpositions first, then for each position 1, 2, ..., n and finally 0 (a wrong
first letter is the rarest typo) the deletion, the substitutions and the
insertions at that position. The alphabet is a build option (`--letters`,
Ukrainian by default, apostrophe included). No frequencies are available, so
rare but valid forms still appear; words flagged "no suggest" never do.

Dictionary format (`cyrdct.py`): 512-byte blocks, no header; lowercase OEM-code-
page words sorted by bytes; entry = prefix byte (bits 0-6 shared letters, bit 7
"accept, never suggest"), suffix bytes, 00h; the first entry of each block has
prefix 0 (+ bit 7); FFh ends a block. From VESUM, bit 7 marks forms whose every
reading is abbr/rare/arch/slang/alt/short/vulg/obsc or vocative, and words of
one or two letters (262 802 forms). Russian (`cyrdct.py opcorpora RU.DCT --cp cp866`,
OpenCorpora via pymorphy3-dicts-ru): 3 184 717 forms, 22 377 blocks, 11.5 MB;
Erro readings left out, Abbr/Arch/Slng/Dist/Infr and the е spelling of ё forms
accepted but not suggested (136 651 forms). Lookup = binary search
over the blocks' first words + linear scan of one block. VESUM 6.8.6 gives
3 775 633 forms, 26 800 blocks, 13.7 MB, ~15 block reads per word.

Verified: in emulation (`test_cyrovl.py`, synthetic and full UK.DCT: case,
apostrophe, ґ/ї, a 24-letter word, absent words, English words and suggestions
unchanged, no leaked handles) and in DOSBox-X with WSU.EXE (cp1125): ^QL passes
"Мова слово їжак м'ясо автобетоноперемішувачами МОВА" and stops at "мовва";
for "Мовва" the menu shows 1 Мова 2 Мойва 3 Моква 4 Мошва 5 Мовна 6 Овва.
Russian, WSR.EXE (cp866) with `cyrovl.py --dict RU.DCT --cp cp866 --letters ru`:
^QL passes "Язык слово ёжик ежик объём высокопроизводительными" and offers
1 Язык 2 Язв 3 Язва ... for "Язвк" (more with M).

## 9. Tooling in this project

```text
emu4.py        Unicorn harness: overlay + real dictionary files, DOS traps,
               hooks, fn dispatch
decode.py      standalone MAIN.DCT decoder (verified bit-exact vs the engine)
personal_cyr.py PERSONAL.DCT bit-7 strip: stock vs patched (3A59h)
cyrdct.py      builds UK.DCT / RU.DCT from a UTF-8 word list (+ reference lookup)
cyrovl.py      patches WSSPELL.OVR: PERSONAL fix + Cyrillic dictionary branch
gas16.py       16-bit 8086 assembly via GNU as, flat binary
test_cyrovl.py emulator test of the patched overlay
patchcp.py     WS.EXE code page tables cp437 -> cp1125 / cp866
```
