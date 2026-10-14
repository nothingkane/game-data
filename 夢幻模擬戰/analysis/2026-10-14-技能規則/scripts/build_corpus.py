# -*- coding: utf-8 -*-
"""把夢戰資料攤平成一份技能語料 corpus.json。
用法：python build_corpus.py <夢幻模擬戰資料根目錄> <輸出 corpus.json 路徑>
來源優先序：遊戲畫面（ingame）> wiki。只讀不寫資料目錄。
"""
import json, glob, os, re, sys

root, out = sys.argv[1], sys.argv[2]

def load(p):
    with open(os.path.join(root, p), encoding='utf-8') as f:
        return json.load(f)

def parse_cd(v):
    """ingame 的 cooldown 是整數（0＝欄位寫「無」）；wiki 的 cd 是「3回合」/「无」/None。"""
    if v is None:
        return None
    if isinstance(v, int):
        return v
    m = re.match(r'(\d+)', str(v))
    if m:
        return int(m.group(1))
    if str(v) in ('无', '無'):
        return 0
    return None

recs = []

# 1. 英雄技能（主動＋被動，含超絕、變身、召喚）
for s in load('merged/skills.json')['skills']:
    w = s.get('wiki') or {}
    if 'text' in s:  # 遊戲畫面有讀到
        cat, cd, rng, area, text, src = s['category'], parse_cd(s['cooldown']), s['range'], s['area'], s['text'], 'ingame'
    else:
        cat, cd, rng, area, text, src = w.get('type'), parse_cd(w.get('cd')), w.get('range'), w.get('span'), w.get('description'), 'wiki'
    owners = s.get('heroes') or s.get('heroes_wiki') or w.get('heroes') or []
    recs.append(dict(kind='hero_skill', name=s['name'], owners=owners, category=cat, cd=cd,
                     range=rng, area=area, cost=s.get('cost'), text=text or '', src=src))

# 2. 天賦：只取遊戲畫面版（214 隻）。wiki 版把 1～4 星串成一段，切不乾淨，不納入
for f in sorted(glob.glob(os.path.join(root, 'merged/heroes/*.json'))):
    with open(f, encoding='utf-8') as fh:
        h = json.load(fh)
    t = h.get('talent')
    if isinstance(t, dict) and t.get('text'):
        recs.append(dict(kind='talent', name=t.get('name'), owners=[h['name']], category='天賦',
                         cd=None, range=None, area=None, cost=None, text=t['text'], src='ingame'))

# 3. 鑄紋：已解鎖 52 顆讀遊戲畫面；可獲得未解鎖的 55 顆用 wiki 全文補
rune = load('sources/ingame/rune_skills.json')
for r in rune['unlocked']:
    recs.append(dict(kind='rune', name=r['name'], owners=[r['hero']], category='鑄紋', cd=None,
                     range=None, area=None, cost=None, text=r['text'], src='ingame'))
for hero, text in rune['obtainable_text_wiki'].items():
    recs.append(dict(kind='rune', name=rune['obtainable'].get(hero, '?'), owners=[hero], category='鑄紋',
                     cd=None, range=None, area=None, cost=None, text=text, src='wiki'))

# 4. 專屬裝備技能 164 件（遊戲畫面為主）
for g in load('merged/exclusive_gear.json')['items']:
    sk = g.get('skill') or {}
    if sk.get('text'):
        recs.append(dict(kind='gear', name=sk.get('name') or g['name'], owners=[g['owner']], category='專屬裝備',
                         cd=None, range=None, area=None, cost=None, text=sk['text'], src='ingame',
                         gear=g['name']))

# 5. 士兵技能 165（只有 wiki）
for s in load('sources/wiki/data/soldiers.json'):
    if s.get('skillDescription'):
        recs.append(dict(kind='soldier', name=s['name'], owners=[], category='士兵:' + s['type'], cd=None,
                         range=s.get('range'), area=None, cost=None, text=s['skillDescription'], src='wiki',
                         level=s.get('level')))

for i, r in enumerate(recs):
    r['id'] = i
with open(out, 'w', encoding='utf-8') as f:
    json.dump(recs, f, ensure_ascii=False, indent=0)
from collections import Counter
print(len(recs), Counter(r['kind'] for r in recs), Counter((r['kind'], r['src']) for r in recs))
