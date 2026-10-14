# -*- coding: utf-8 -*-
"""第 2.3 節傷害倍率改用 area 欄分單體／範圍＋各節極端值點名。
用法：python extremes.py <corpus.json> <stats.json>
只新增 M_／X_ 開頭的鍵，不改舊鍵；並在 _errata 記錄 2e／2f 已被 M_ 取代。另寫 ex_tables.md。
"""
import json, re, sys, os, statistics, collections

corpus_path, stats_path = sys.argv[1], sys.argv[2]
outdir = os.path.dirname(os.path.abspath(stats_path))
R = json.load(open(corpus_path, encoding='utf-8'))
stats = json.load(open(stats_path, encoding='utf-8'))
md = []

def norm(t):
    t = re.sub(r'[“”"「」‘’\'『』]', '', t or '')
    return t.replace('遠端', '遠程').replace('（', '(').replace('）', ')').replace('％', '%')
for r in R:
    r['nt'] = norm(r['text'])
H = [r for r in R if r['kind'] == 'hero_skill']
ACT = [r for r in H if r['category'] != '被動']

def fmt(v):
    return int(v) if float(v).is_integer() else v
def sent(t, a, b):
    s = max(t.rfind('。', 0, a), t.rfind('；', 0, a)) + 1
    ends = [i for i in (t.find('。', b), t.find('；', b)) if i != -1]
    return t[s:(min(ends) + 1 if ends else len(t))][:200]

# ================= 2.3 傷害倍率：用 area 欄 =================
def first_mult(r):
    """從該分類的標籤 [物理傷害]／[魔法傷害] 之後找第一個「造成…X倍」；沒有標籤就從頭找"""
    t = r['nt']
    tag = '[' + r['category'] + ']'
    i = t.find(tag)
    start = i if i != -1 else 0
    m = re.search(r'造成[^，。；]{0,10}?(\d+(?:\.\d+)?)倍', t[start:])
    if not m:
        return None, None
    return float(m.group(1)), sent(t, start + m.start(), start + m.end())

rows = []
detail = collections.defaultdict(list)
for r in ACT:
    if r['category'] not in ('物理傷害', '魔法傷害'):
        continue
    v, s = first_mult(r)
    if v is None:
        continue
    shape = '未載' if r['area'] is None else ('單體' if r['area'] == '單體' else '範圍')
    detail[(r['category'], shape)].append({'name': r['name'], 'val': v, 'area': r['area'], 'src': r['src'], 'sentence': s})

def summarize(lst):
    vals = sorted(e['val'] for e in lst)
    q = statistics.quantiles(vals, n=4, method='inclusive') if len(vals) >= 4 else [vals[0], statistics.median(vals), vals[-1]]
    lo = min(lst, key=lambda e: e['val']); hi = max(lst, key=lambda e: e['val'])
    los = sorted({e['name'] for e in lst if e['val'] == lo['val']}); his = sorted({e['name'] for e in lst if e['val'] == hi['val']})
    return {'count': len(vals), 'min': fmt(lo['val']), 'p25': fmt(round(q[0], 2)), 'median': fmt(statistics.median(vals)), 'p75': fmt(round(q[2], 2)),
            'max': fmt(hi['val']), 'mode': fmt(collections.Counter(vals).most_common(1)[0][0]),
            'min_names': los, 'max_names': his, 'min_example': {'name': lo['name'], 'sentence': lo['sentence']}, 'max_example': {'name': hi['name'], 'sentence': hi['sentence']}}

for scope in ['全部（遊戲畫面＋wiki 補）', '只看遊戲畫面版']:
    for (cat, shape) in [('物理傷害', '單體'), ('物理傷害', '範圍'), ('魔法傷害', '單體'), ('魔法傷害', '範圍')]:
        lst = [e for e in detail[(cat, shape)] if scope.startswith('全部') or e['src'] == 'ingame']
        if lst:
            d = summarize(lst); d.update({'scope': scope, 'name': f'{cat}・{shape}'})
            rows.append(d)
bins = [(0, 0.3), (0.3, 0.5), (0.5, 1.0), (1.0, 1.3), (1.3, 1.5), (1.5, 1.7), (1.7, 2.0), (2.0, 99)]
binrows = {}
for (cat, shape), lst in detail.items():
    if shape == '未載':
        continue
    binrows[f'{cat}・{shape}'] = [{'name': f'{a}–{b if b < 99 else "以上"}', 'count': sum(1 for e in lst if a <= e['val'] < b)} for a, b in bins]
stats['M_multiplier_by_area_field'] = {
    'title': '傷害倍率（單體／範圍改用 area 欄；倍率取 [物理傷害]／[魔法傷害] 標籤之後第一個「造成…X倍」）',
    'note': 'area＝單體 算單體，其餘（直線、N格、N圈、全場、自身）算範圍；wiki 補的 177 顆用 wiki 的 span 欄。取代 2e_multiplier／2f_multiplier_bins',
    'rows': rows, 'bins': binrows, 'area_missing': len(detail[('物理傷害', '未載')]) + len(detail[('魔法傷害', '未載')])}
# 舊法與新法的差異逐筆
diffs = []
for r in ACT:
    if r['category'] not in ('物理傷害', '魔法傷害'):
        continue
    m = re.search(r'造成(?:自身[^，。；]{0,6})?(\d+(?:\.\d+)?)倍(?:的)?(範圍)?傷害', r['nt'])
    v_new, s_new = first_mult(r)
    if not m and v_new is None:
        continue
    old_shape = None
    if m:
        old_shape = '範圍' if (bool(m.group(2)) or '範圍傷害' in r['nt'][:80]) else '單體'
    new_shape = None if r['area'] is None else ('單體' if r['area'] == '單體' else '範圍')
    old_v = float(m.group(1)) if m else None
    if old_shape != new_shape or old_v != v_new:
        diffs.append({'name': r['name'], 'category': r['category'], 'area': r['area'], 'src': r['src'], 'old': [old_shape, old_v], 'new': [new_shape, v_new]})
stats['M_multiplier_diff_vs_old'] = {'title': '2.3 舊表與新表逐筆差異', 'rows': diffs}
stats.setdefault('_errata', []).append('2026-10-14：2e_multiplier／2f_multiplier_bins 用文字關鍵字判單體／範圍，有 9 顆判錯（例：青龍破陣 area＝單體但文字有後續範圍傷害），改看 M_multiplier_by_area_field')

md.append('### M 傷害倍率（area 欄）\n')
md.append('| 範圍 | 類型 | 筆數 | 最小 | P25 | 中位數 | P75 | 最大 | 眾數 | 最小是誰 | 最大是誰 |')
md.append('|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|')
for d in rows:
    md.append(f"| {d['scope']} | {d['name']} | {d['count']} | {d['min']} | {d['p25']} | {d['median']} | {d['p75']} | {d['max']} | {d['mode']} | {'、'.join(d['min_names'][:6])}{'…' if len(d['min_names']) > 6 else ''} | {'、'.join(d['max_names'][:6])}{'…' if len(d['max_names']) > 6 else ''} |")
md.append('\n極值原文：')
for d in rows:
    if d['scope'].startswith('全部'):
        md.append(f"- {d['name']} 最小 {d['min']}：{d['min_example']['name']}「{d['min_example']['sentence'][:110]}」；最大 {d['max']}：{d['max_example']['name']}「{d['max_example']['sentence'][:110]}」")
md.append(f"\n逐筆差異 {len(diffs)} 筆：")
for x in diffs:
    md.append(f"- {x['name']}（{x['category']}，area={x['area']}，{x['src']}）：舊 {x['old']} → 新 {x['new']}")

# ================= 各節極端值點名 =================
X = {}
def names_where(pool, pred):
    return sorted({r['name'] for r in pool if pred(r)})
# 2.1 冷卻
cd7 = sorted([(r['cd'], r['name'], r['category'], r['src']) for r in ACT if r['cd'] is not None and r['cd'] >= 7], key=lambda x: (-x[0], x[1]))
cd0 = sorted([(r['name'], r['category']) for r in ACT if r['cd'] == 0])
cd1 = sorted([(r['name'], r['category']) for r in ACT if r['cd'] == 1])
cdna = sorted([r['name'] for r in ACT if r['cd'] is None])
X['cooldown'] = {'cd_7_plus': [{'cd': c, 'name': n, 'category': k, 'src': s} for c, n, k, s in cd7],
                 'cd_0_none': [{'name': n, 'category': k} for n, k in cd0], 'cd_1': [{'name': n, 'category': k} for n, k in cd1], 'cd_missing': cdna}
# 2.2 射程、範圍的兩端
X['range_extremes'] = {'range_7': names_where(ACT, lambda r: r['range'] == '7格'), 'range_full': names_where(ACT, lambda r: r['range'] == '全場'),
                       'area_full': names_where(ACT, lambda r: r['area'] == '全場'), 'area_5_or_6': names_where(ACT, lambda r: r['area'] in ('5格', '6格')),
                       'area_3ring': names_where(ACT, lambda r: r['area'] == '3圈')}
# 2.4 再動格數
X['again_cells'] = {f'{n}格': names_where(ACT, lambda r, n=n: re.search(rf'(額外|再次|再)行動{n}格', r['nt'])) for n in (2, 3, 4)}
# 4.2／5.2 持續回合兩端
X['duration_extremes'] = {f'{n}回合': names_where(R, lambda r, n=n: f'持續{n}回合' in r['nt']) for n in (5, 6)}
# 4.3 疊層上限兩端
cap_pat = re.compile(r'(?:可(?:以)?(?:累積|疊加)[^。；]{0,12}?(?:最多|最高|最大)(?:可以)?(?:累積|疊加)?\s*(?:為)?(\d+)|(?:最多|最高|最大)(?:可以)?(?:累積|疊加)\s*(\d+)|可(?:累積|疊加)(\d+)(?:層|個|次))')
capn = collections.defaultdict(set)
for r in R:
    for m in cap_pat.finditer(r['nt']):
        capn[int(next(x for x in m.groups() if x))].add(r['name'])
X['stack_cap_extremes'] = {str(k): sorted(v) for k, v in sorted(capn.items()) if k in (min(capn), max(capn)) or k >= 7}
# 6 驅散 5 個與「所有」
d5 = collections.defaultdict(set)
for r in R:
    for m in re.finditer(r'驅散[^，。；]{0,8}?(\d+|所有|全部)個?[^，。；]{0,2}(強化|弱化)', r['nt']):
        k = ('所有' if m.group(1) in ('所有', '全部') else m.group(1))
        if k in ('5', '所有', '3'):
            d5[f'驅散{m.group(2)}×{k}'].add(r['name'])
X['dispel_extremes'] = {k: sorted(v) for k, v in sorted(d5.items())}
# 7 光環半徑與 HP 門檻兩端
rad = collections.defaultdict(set)
for r in R:
    for m in re.finditer(r'周圍(\d+)(格|圈)', r['nt']):
        if int(m.group(1)) >= 5:
            rad[f'周圍{m.group(1)}{m.group(2)}'].add(r['name'])
cmd = collections.defaultdict(set)
for r in R:
    for m in re.finditer(r'\[指揮\][^。；]{0,4}?周圍(\d+)格', r['nt']):
        if m.group(1) in ('1', '3'):
            cmd[f'[指揮]{m.group(1)}格'].add(r['name'])
hp = collections.defaultdict(set)
for r in R:
    for m in re.finditer(r'生命(?:值)?[^，。；]{0,4}?(高於|低於|大於|小於|不低於|不高於|少於|多於)[^，。；\d]{0,2}(\d+)%', r['nt']):
        lab = ('高於' if m.group(1) in ('高於', '大於', '不低於', '多於') else '低於') + f' {m.group(2)}%'
        hp[lab].add(r['name'])
hp_keys = sorted(hp, key=lambda k: (k[:2], int(re.search(r'\d+', k).group())))
hp_ext = {k: sorted(hp[k]) for k in hp_keys if k in (hp_keys[0], hp_keys[-1]) or k.startswith('高於 1') or k.startswith('低於 1')}
X['aura_hp_extremes'] = {'radius_5_plus': {k: sorted(v) for k, v in rad.items()}, 'command_1_or_3': {k: sorted(v) for k, v in cmd.items()}, 'hp_extremes': hp_ext}
# 8 機率兩端
ch = collections.defaultdict(set)
for r in R:
    for m in re.finditer(r'(\d+)%(?:的)?機率', r['nt']):
        ch[int(m.group(1))].add(r['name'])
X['chance_extremes'] = {f'{k}%': sorted(v) for k, v in sorted(ch.items()) if k in (min(ch), max(ch), 20, 25)}
stats['X_extremes_named'] = {'title': '各節極端值點名', **X}

md.append('\n### X 冷卻 7 回合以上')
for x in X['cooldown']['cd_7_plus']:
    md.append(f"- {x['cd']} 回合：{x['name']}（{x['category']}，{x['src']}）")
md.append(f"\n無冷卻（{len(cd0)} 顆）：" + '、'.join(f'{n}（{k}）' for n, k in cd0))
md.append(f"\n1 回合（{len(cd1)} 顆）：" + '、'.join(n for n, k in cd1))
md.append(f"\n未載（{len(cdna)} 顆）：" + '、'.join(cdna))
for k in ['range_extremes', 'again_cells', 'duration_extremes', 'stack_cap_extremes', 'dispel_extremes', 'aura_hp_extremes', 'chance_extremes']:
    md.append(f'\n### X {k}\n' + json.dumps(X[k], ensure_ascii=False))

json.dump(stats, open(stats_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(os.path.join(outdir, 'ex_tables.md'), 'w', encoding='utf-8').write('\n'.join(md))
print('ok', len(rows), 'mult rows;', len(diffs), 'diffs')
