"""Emulator test of cyrovl.py: the patched overlay checks and suggests Cyrillic words.

  python test_cyrovl.py WSDIR                 synthetic Ukrainian dictionary (seconds to build)
  python test_cyrovl.py WSDIR UK.DCT          a full dictionary built by cyrdct.py
  python test_cyrovl.py WSDIR RU.DCT          a file name starting with RU: Russian, cp866

WSDIR holds the original WordStar 4.0 WSSPELL.OVR, MAIN.DCT, INTERNAL.DCT, PERSONAL.DCT.
The full-dictionary runs take a few minutes (every instruction goes through Python).
"""
import itertools
import os
import sys

import cyrdct
import cyrovl
import emu4

UK = dict(
    cp='cp1125', letters=cyrovl.UK, name='UK.DCT', personal='київ',
    real=['мова', 'слово', 'їжак', "м'ясо", 'ґанок', 'автобетоноперемішувачами'],  # 24 letters
    absent=['мовва', 'хатаа', 'ьььь', 'автобетоноперемішувачамищ', 'зкщф'],
    sugg={'мовва': 'мова', 'Мовва': 'Мова', 'мвоа': 'мова', 'мива': 'мова', 'мва': 'мова',
          'їжк': 'їжак', 'мясо': "м'ясо"})
RU = dict(
    cp='cp866', letters=cyrovl.RU, name='RU.DCT', personal='щас',
    real=['язык', 'слово', 'ёжик', 'ежик', 'объём', 'высокопроизводительными'],     # 23 letters
    absent=['языкк', 'ьььь', 'высокопроизводительнымищ', 'зкщф'],
    sugg={'язвк': 'язык', 'Язвк': 'Язык', 'сллово': 'слово', 'солво': 'слово', 'слво': 'слово',
          'ёжк': 'ёжик', 'обём': 'объём'})


def synthetic(lang):
    abc = 'абвгґдеєжзиіїйклмнопрстуфхцчшщьюя'
    ws = {a + b + c + 'ка' for a, b, c in itertools.product(abc[:12], abc[10:22], 'аоі')}
    return cyrdct.build(sorted((w.encode(lang['cp']), 0) for w in ws | set(lang['real'])))


def run(wsdir, lang, dct):
    cp = lang['cp']
    img = cyrovl.build(open(os.path.join(wsdir, 'WSSPELL.OVR'), 'rb').read(),
                       lang['name'], cp, lang['letters'])
    o = emu4.Ovl(wsdir, trace_io=False, img=img)
    o.dosfs = {lang['name']: dct}
    o.files[7] = ('WordStar\r\n' + lang['personal'] + '\r\n').encode(cp) + b'\x1a'
    emu4.open_dicts(o)
    found = lang['real'] + [w.upper() for w in lang['real'][:3]] + [lang['personal'], 'the', 'cats']
    res = {w: emu4.check(o, w, cp) for w in found + lang['absent'] + ['zzqxw']}
    sugg = {w: emu4.suggestions(o, w, cp) for w in list(lang['sugg']) + ['teh']}
    for w, s in sugg.items():
        print(f'  {w} -> {s}')
    bad = [w for w in found if res[w] != 1] + [w for w in lang['absent'] + ['zzqxw'] if res[w]]
    assert not bad, bad
    miss = [w for w, want in list(lang['sugg'].items()) + [('teh', 'the')] if want not in sugg[w]]
    assert not miss, miss
    assert getattr(o, 'opened', 0) == 0, 'dictionary handle left open'


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    if len(sys.argv) > 2:
        lang = RU if os.path.basename(sys.argv[2]).upper().startswith('RU') else UK
        dct = open(sys.argv[2], 'rb').read()
    else:
        lang, dct = UK, synthetic(UK)
    print(f'{lang["name"]}: {len(dct) // cyrdct.BLOCK} blocks')
    run(sys.argv[1], lang, dct)
    print('OK')
