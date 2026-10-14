# ws4spell

Cyrillic spelling for WordStar 4.0 for DOS: Ukrainian and Russian dictionaries with
suggestions, built from open word lists and plugged into the original spelling overlay.

WordStar 4.0 checks spelling with CorrectStar 3.0 (Houghton Mifflin), whose dictionary
format can only hold English: a 5-bit alphabet, an English phonetic index and English
endings. This project leaves the English checker as it is and adds a second path for
Cyrillic words:

- `patchcp.py` switches the letter and case tables of `WS.EXE` from cp437 to cp1125
  (Ukrainian) or cp866 (Russian), so WordStar treats Cyrillic letters as letters.
- `cyrdct.py` builds `UK.DCT` or `RU.DCT`, a simple block dictionary of every word form.
- `cyrovl.py` patches the original `WSSPELL.OVR`. A word with a Cyrillic letter is looked
  up in that dictionary; English words take the original path. Misspelt Cyrillic words
  get suggestions in the usual menu, with the case of the word you typed (`Мовва` ->
  `Мова`). Words you add to `PERSONAL.DCT` (A in the spelling menu) keep working after a
  restart. In the original overlay they are lost, because it strips bit 7 when it reads
  the file.
- `WS4DCT_FORMAT.md` describes the original dictionary format, the overlay interface and
  the patch, as reverse engineered from the files.

No WordStar files and no compiled dictionaries are included. You build them yourself.

## Requirements

- Python 3.10+
- GNU `as` and `objcopy` (binutils, any x86 target: Linux, MSYS2/MinGW, ...), used by
  `cyrovl.py` to assemble the 8086 code
- `unicorn` (only for the tests and `patchcp.py --check`)
- `pymorphy3` and `pymorphy3-dicts-ru` (only for the Russian dictionary)
- WordStar Professional 4.00 for DOS with spelling (`WSSPELL.OVR`, `MAIN.DCT`,
  `INTERNAL.DCT`, `PERSONAL.DCT`)
- A Cyrillic screen font and keyboard driver for DOS in the same code page (not part of
  this project). In DOSBox-X, `chcp 866` switches the font; for cp1125 use your own.

## Building

```sh
# WS.EXE -> WSU.EXE (cp1125) and WSR.EXE (cp866), next to it; the original stays unchanged
python patchcp.py C:/WS4/WS.EXE

# Ukrainian: VESUM (brown-uk/dict_uk) v6.8.6
gh release download v6.8.6 -R brown-uk/dict_uk -p dict_corp_vis.txt.bz2
python cyrdct.py dict_corp_vis.txt.bz2 UK.DCT
python cyrovl.py C:/WS4/WSSPELL.OVR WSSPELL.UK

# Russian: OpenCorpora via pymorphy3-dicts-ru
python -m pip install pymorphy3 pymorphy3-dicts-ru
python cyrdct.py opcorpora RU.DCT --cp cp866
python cyrovl.py C:/WS4/WSSPELL.OVR WSSPELL.RU --dict RU.DCT --cp cp866 --letters ru
```

Each dictionary takes a few minutes to build. The results:

| | forms | not suggested | file |
|---|---:|---:|---:|
| `UK.DCT` (cp1125) | 3 775 633 | 262 802 | 13.7 MB |
| `RU.DCT` (cp866) | 3 184 717 | 136 651 | 11.5 MB |

"Not suggested" forms are accepted by the check but never offered as suggestions. These
are abbreviations, rare, archaic, slang and alternative forms, vocatives, words of one
or two letters, and in Russian the е spelling of words with ё.

`cyrovl.py` checks the SHA-256 of `WSSPELL.OVR` (see Sources) and refuses any other file.

## Installing

In the WordStar directory, keep a copy of the original `WSSPELL.OVR`, then:

- Ukrainian: copy `WSSPELL.UK` as `WSSPELL.OVR`, add `UK.DCT`, start `WSU`;
- Russian: copy `WSSPELL.RU` as `WSSPELL.OVR`, add `RU.DCT`, start `WSR`.

One overlay serves one Cyrillic language. English is checked as before in both. To use
both languages, keep two WordStar directories or swap the overlay. The dictionary
is opened by the name given to `--dict`, by default relative to the current directory.
Start WordStar from its own directory, or build with a full path, e.g.
`--dict C:\WS4\UK.DCT` (at most 63 characters).

WordStar 4 keeps characters 80h-FFh in documents as `1Bh xx 1Ch`. Text typed in WordStar
is stored that way automatically. If you prepare a document with another program, it
has to use the same encoding.

## Other languages

Any language whose alphabet fits cp1125 or cp866 can be added the same way. You need
a UTF-8 word list with one form per line (all of them will be suggested) and the alphabet
for suggestions:

```sh
python cyrdct.py words.txt XX.DCT --cp cp866
python cyrovl.py C:/WS4/WSSPELL.OVR WSSPELL.XX --dict XX.DCT --cp cp866 --letters "..."
```

`--letters` takes the letters themselves (from a UTF-8 terminal) or `uk` / `ru`. Another
code page needs its own entry in `patchcp.py` (letter and case tables) and a matching
screen font.

Latin-script languages are not supported. The branch is chosen by the word: only words
with a byte >= 80h go to the new dictionary, and a plain ASCII word always goes to the
English one, so most German or French words would be checked as English.

## How it works

Details, with addresses, are in `WS4DCT_FORMAT.md`, section 8.

- **Check.** In the word check of the overlay, after the personal dictionary and the
  frequent-word table, a jump goes to new code appended to the overlay. The original
  code continues with the English dictionary and a 21-letter limit. The new code
  searches the dictionary file: a binary search over 512-byte blocks by their first
  words, then a scan of one block, about 15 reads per word.
- **Suggestions.** The overlay's suggestion generator is intercepted. For a Cyrillic word
  the new code collects up to 8 dictionary words one edit away (transposition, then
  deletion, substitution and insertion, position by position with the first letter
  last) and hands them to the original menu code, which applies the case of the typed
  word. WordStar shows 6 or 7 of them at a time.
- **Dictionary format.** Lowercase word forms in the OEM code page, sorted by bytes,
  front-coded in 512-byte blocks. Bit 7 of the prefix byte marks "do not suggest".
- **Personal dictionary.** One byte in the `PERSONAL.DCT` reader stops it from stripping
  bit 7.

The appended code (about 1.8 KB, 8086) stays well inside the memory WordStar reserves for
the overlay (SPSIZE, 52 KB). The dictionary file is opened and closed for each check and
each suggestion list, so nothing breaks when WordStar swaps the overlay out.

Limitations: the word lists have no frequencies, so rare but valid forms appear among the
suggestions. The personal dictionary holds about 1500 words, shared with the "ignore"
list of the session.

## Sources

**WordStar Professional 4.00**, build 020 (`Serial #FLM934PA 020`), 360K disk images from
WinWorld. The work was done on these files (SHA-256):

| File | Bytes | SHA-256 |
|---|---:|---|
| WSSPELL.OVR | 23520 | `7c9ce0a1f5ead66c00850f1e0c52a61d999c13a9bed68ef5f8bb91c1f2a48299` |
| MAIN.DCT | 277504 | `0b7817bb5f9ea5dad70869b8b4ac7dddddffdd7b37ee2ce0b1f4f1f1629c2b13` |
| INTERNAL.DCT | 25600 | `85e4fa74a415f4f9812c95280fae59af80d25f716c49ec180310c00071c2668c` |
| WS.EXE (020) | 78208 | `32b518f65887ea7b100266bd5598b79fd296b86c3ce1f762a4ae2f63db084eba` |
| WS.EXE (021) | 78341 | `046d2b70b554aa8d3329460e762f94b6f92733ada51b4625981fcd78674848c6` |

`patchcp.py` checks the tables it changes rather than the hash, and works on both builds.

**Ukrainian.** VESUM, <https://github.com/brown-uk/dict_uk>, release v6.8.6,
`dict_corp_vis.txt.bz2`, SHA-256
`e33803783ac138e6f3af2cf0e9428ba146c0ecfda7f5c41fe83ae00c7af24be9`. Dictionary data:
CC BY-NC-SA 4.0.

**Russian.** OpenCorpora, <https://opencorpora.org>, through `pymorphy3-dicts-ru`
2.4.417150.4580142. Dictionary data: CC BY-SA 3.0.

A dictionary built from these sources is a derivative of their data. If you distribute
it, the data license applies (for Ukrainian: non-commercial, share-alike).

## Tests

`WSDIR` is a directory with the original `WSSPELL.OVR`, `MAIN.DCT`, `INTERNAL.DCT` and
`PERSONAL.DCT`. The overlay runs under Unicorn, so the full-dictionary tests take a few
minutes.

```sh
python emu4.py WSDIR                    # original engine: check, personal dictionary, suggestions
python personal_cyr.py WSDIR            # PERSONAL.DCT: Cyrillic lost by the original, kept when patched
python test_cyrovl.py WSDIR             # patched overlay, small synthetic Ukrainian dictionary
python test_cyrovl.py WSDIR UK.DCT      # ... full Ukrainian dictionary
python test_cyrovl.py WSDIR RU.DCT      # ... full Russian dictionary (cp866)
python patchcp.py --check WSU.EXE cp1125    # case tables of the patched EXE, run in Unicorn
python decode.py WSDIR > words.txt      # all 60337 forms of the original English dictionary
```

The patches were also checked in WordStar 4.00 itself under DOSBox-X, with WSU.EXE and
WSR.EXE. Ukrainian and Russian words are accepted, including capitalised words, words
with an apostrophe and words longer than 21 letters. Typos are flagged and get
suggestions, and English spelling works as before.

## License

GPL v3, see `LICENSE`. WordStar is a trademark of its owners; this project is not
affiliated with them. It contains no WordStar files. The few bytes it expects at the
patched places are listed in `cyrovl.py` and `patchcp.py`.
