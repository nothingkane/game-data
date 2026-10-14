# -*- coding: utf-8 -*-
"""強化／弱化每一類效果的數值範圍（單次給的值）與文字寫明的封頂。
用法：python value_ranges.py <corpus.json> <stats.json> <exclusions.json>
- 先跑 analyze.py 產出 stats.json，再跑本腳本：只「新增」V_ 開頭的鍵，不動舊鍵。
- exclusions.json：人工讀原文後判定解析錯誤、要排除的事件（技能名＋類別＋數值＋理由）。
- 另寫 vr_tables.md（表格）、vr_events.json（全部事件，方便抽查）。
"""
import json, re, sys, os, statistics, collections

corpus_path, stats_path = sys.argv[1], sys.argv[2]
excl_path = sys.argv[3] if len(sys.argv) > 3 else None
outdir = os.path.dirname(os.path.abspath(stats_path))
R = json.load(open(corpus_path, encoding='utf-8'))
stats = json.load(open(stats_path, encoding='utf-8'))
EXCL = json.load(open(excl_path, encoding='utf-8'))['items'] if excl_path and os.path.exists(excl_path) else []

KIND_ZH = {'hero_skill': '英雄技能', 'talent': '天賦', 'rune': '鑄紋', 'gear': '專屬裝備', 'soldier': '士兵'}
GROUP_ORDER = ['主動', '被動', '天賦', '鑄紋', '專屬裝備', '士兵']

def group_of(r):
    if r['kind'] == 'hero_skill':
        return '被動' if r['category'] == '被動' else '主動'
    return KIND_ZH[r['kind']]

# ---- 與 analyze.py 相同的正規化（含剝掉專屬裝備開頭的強化等級屬性）----
GEAR_STAT = re.compile(r'^([^。；]*?[+＋]\d+%)[。；，]?')
def norm(t):
    t = re.sub(r'[“”"「」‘’\'『』]', '', t or '')
    return t.replace('遠端', '遠程').replace('（', '(').replace('）', ')').replace('％', '%')
for r in R:
    r['nt'] = norm(r['text'])
    if r['kind'] == 'gear':
        m = GEAR_STAT.match(r['nt'])
        if m:
            r['nt'] = r['nt'][m.end():]
    r['group'] = group_of(r)

CAPW = re.compile(r'最多|最高|最大(?!生命)|上限|不超過|至多')
NUM = r'(\d+(?:\.\d+)?)'

def sentence_of(t, a, b):
    s = max(t.rfind('。', 0, a), t.rfind('；', 0, a)) + 1
    ends = [i for i in (t.find('。', b), t.find('；', b)) if i != -1]
    e = min(ends) + 1 if ends else len(t)
    return t[s:e]

def lead(t, pos, n=8):
    """數字前面同一小句（不跨，。；）的 n 個字"""
    s = max(t.rfind('，', 0, pos), t.rfind('。', 0, pos), t.rfind('；', 0, pos), t.rfind(',', 0, pos))
    return t[max(s + 1, pos - n):pos]

EV = []
AUTO_EXCL = []
PER = re.compile(r'每(?!場|回合|次施加)')
def add(r, cat, pol, unit, val, a, b, numpos, extra=None):
    t = r['nt']
    ld = lead(t, numpos, 10)
    is_cap = bool(CAPW.search(ld))
    sent_s = max(t.rfind('。', 0, a), t.rfind('；', 0, a)) + 1
    lastv = max(sent_s - 1, t.rfind('%', 0, a), t.rfind(')', 0, a))
    per_unit = bool(PER.search(t[lastv + 1:a]))  # 只看上一個數值或括號之後，避免同句前段的「每」誤套到後面
    EV.append({'id': r['id'], 'name': r['name'], 'group': r['group'], 'kind': r['kind'], 'cat': cat, 'pol': pol, 'unit': unit,
               'val': val, 'cap': is_cap, 'per_unit': per_unit, 'pos': numpos, 'match': t[a:b], 'sentence': sentence_of(t, a, b)[:220]})

# ---- 1. 屬性詞＋方向＋數字（同 analyze.py 的 stat_events，改成可抓小數、帶位置）----
STAT = r'(攻擊|智力|防禦|魔防|技巧|全屬性|攻防(?:能力)?|生命|暴擊率|暴擊傷害|傷害|移動力|射程|治療效果|冷卻時間)'
DIR = r'(提升|增加|提高|降低|減少|下降|\+|-|－)'
STAT_RE = re.compile(STAT)
TAIL_RE = re.compile(r'(?P<gap>[^，。；\d]{0,3}?)' + DIR + r'\s*' + NUM + r'(%?)(?P<after>.?)')

def stat_type(pre, stat, up):
    recv = bool(re.search(r'(遭受|受到|受)[^，。；]{0,6}$', pre)) or bool(re.search(r'遭受|受到', pre[-6:]))
    if stat in ('暴擊率', '暴擊傷害'):
        return ('防暴擊（遭受暴擊率降低）', 'buff') if recv and not up else ('受暴擊提升', 'debuff') if recv else ('暴擊提升', 'buff') if up else ('暴擊降低', 'debuff')
    if stat == '傷害':
        if recv:
            return ('減傷（遭受傷害降低）', 'buff') if not up else ('易傷（遭受傷害提升）', 'debuff')
        return ('增傷（造成傷害提升）', 'buff') if up else ('降傷（造成傷害降低）', 'debuff')
    if stat == '治療效果':
        if recv:
            return ('受治療提升', 'buff') if up else ('受治療降低', 'debuff')
        return ('治療效果提升', 'buff') if up else ('治療效果降低', 'debuff')
    if stat == '冷卻時間':
        return ('冷卻縮短', 'buff') if not up else ('冷卻增加', 'debuff')
    if stat in ('移動力', '射程'):
        return ('移動力／射程提升', 'buff') if up else ('移動力／射程降低', 'debuff')
    if recv:
        return None
    return ('屬性提升（攻智防魔技生命）', 'buff') if up else ('屬性降低（攻智防魔技生命）', 'debuff')

for r in R:
    t = r['nt']
    for m0 in STAT_RE.finditer(t):
        stat = m0.group(1)
        m = TAIL_RE.match(t, m0.end())
        if not m:
            continue
        gap = m.group('gap')
        if STAT_RE.search(gap) or re.search(r'射程|範圍|移動', gap):
            continue  # 「普通攻擊射程+1」「傷害的範圍+1」：數字屬於後面那個詞
        d, val, pc, after = m.group(2), float(m.group(3)), m.group(4) == '%', m.group('after')
        up = d in ('提升', '增加', '提高', '+')
        s0 = max(t.rfind('，', 0, m0.start()), t.rfind('。', 0, m0.start()), t.rfind('；', 0, m0.start()))
        pre = t[max(s0 + 1, m0.start() - 10):m0.start()]
        typ = stat_type(pre, stat, up)
        if not typ:
            continue
        if not pc and ('倍率' in gap or after == '倍'):
            AUTO_EXCL.append({'table': 'range(auto)', 'name': r['name'], 'cat': '技能自身傷害倍率增減', 'unit': '倍', 'val': val,
                              'why': '「傷害倍率提升／降低 N 倍」是技能本身倍率的成長，不是 buff／debuff', 'sentence': sentence_of(t, m0.start(), m.end())[:200]})
            continue
        if pc:
            unit = '%'
        elif stat in ('移動力', '射程'):
            unit = '格'
        elif stat == '冷卻時間':
            unit = '回合'
        elif after in ('回', '層', '個', '次'):
            AUTO_EXCL.append({'table': 'range(auto)', 'name': r['name'], 'cat': typ[0], 'unit': after, 'val': val,
                              'why': '數字後面接「' + after + '」，不是屬性值（例：受到傷害後減少1回合持續時間）', 'sentence': sentence_of(t, m0.start(), m.end())[:200]})
            continue
        else:
            unit = '無單位（定值）'
        add(r, typ[0], typ[1], unit, val, m0.start(), m.end(), m.start(3))

# ---- 2. 回血、吸血、護盾、持續傷害、一次性固定傷害、反彈 ----
for r in R:
    t = r['nt']
    for m in re.finditer(r'恢復[^，。；]{0,16}?' + NUM + r'%(?:的)?(?:部隊)?(?:最大)?生命', t):
        if '傷害' in m.group(0):
            continue
        add(r, '回血', 'buff', '%最大生命', float(m.group(1)), m.start(), m.end(), m.start(1))
    for m in re.finditer(r'恢復[^，。；]{0,10}最大生命(?:值)?的' + NUM + '%', t):
        add(r, '回血', 'buff', '%最大生命', float(m.group(1)), m.start(), m.end(), m.start(1))
    for m in re.finditer(r'(智力|攻擊|防禦|魔防)[^，。；\d]{0,3}' + NUM + r'倍(?:的)?生命', t):
        add(r, '回血', 'buff', f'倍（施放者{m.group(1)}）', float(m.group(2)), m.start(), m.end(), m.start(2))
    for m in re.finditer(r'恢復量為[^，。；]{0,10}?(智力|攻擊)的?' + NUM + '倍', t):
        add(r, '回血', 'buff', f'倍（施放者{m.group(1)}）', float(m.group(2)), m.start(), m.end(), m.start(2))
    for m in re.finditer(r'傷害(?:數值)?[^，。；\d]{0,2}' + NUM + r'%(?:的)?生命', t):
        add(r, '吸血', 'buff', '%造成傷害', float(m.group(1)), m.start(), m.end(), m.start(1))
    for m in re.finditer(r'恢復量為[^，。；]{0,6}造成(?:的)?傷害的?' + NUM + '%', t):
        add(r, '吸血', 'buff', '%造成傷害', float(m.group(1)), m.start(), m.end(), m.start(1))
    # 護盾：抵擋 X 傷害（排除抵擋致命傷害）
    for m in re.finditer(r'抵擋[^，。；]{0,14}?' + NUM + r'%(?:的)?(?:最大)?(?:生命)?|抵擋[^，。；]{0,10}最大生命(?:值)?的?' + NUM + '%', t):
        seg = m.group(0)
        if '致命' in seg or '最大生命' not in t[m.start():m.end() + 6]:
            continue
        v = m.group(1) or m.group(2)
        add(r, '護盾', 'buff', '%最大生命', float(v), m.start(), m.end(), m.start(1) if m.group(1) else m.start(2))
    for m in re.finditer(r'抵擋[^，。；]{0,10}(智力|攻擊|防禦|魔防)[^，。；\d]{0,3}' + NUM + '倍', t):
        add(r, '護盾', 'buff', f'倍（{m.group(1)}）', float(m.group(2)), m.start(), m.end(), m.start(2))
    # 固定傷害：同一句有「行動結束時／回合開始時…受到」算持續傷害，其餘算一次性
    for c_m in re.finditer(r'[^。；]+', t):
        c = c_m.group(0); off = c_m.start()
        if '固定傷害' not in c:
            continue
        dot = bool(re.search(r'(行動結束|回合開始|回合結束)[^。；]{0,20}受到', c)) or '灼燒' in c
        cat = '持續傷害（DoT）' if dot else '固定傷害（一次性）'
        pol = 'debuff'
        for m in re.finditer(r'(攻擊|智力|防禦|魔防)(?:力)?(?:的)?' + NUM + r'倍', c):
            if re.match(r'(的)?生命', c[m.end():m.end() + 3]):
                continue  # 「智力2倍的生命」是回血
            add(r, cat, pol, f'倍（{m.group(1)}）', float(m.group(2)), off + m.start(), off + m.end(), off + m.start(2))
        for m in re.finditer(r'最大生命(?:值)?(?:的)?' + NUM + r'%|' + NUM + r'%(?:的)?最大生命', c):
            if '抵擋' in c[max(0, m.start() - 12):m.start()]:
                continue  # 護盾量，不是固定傷害
            v = m.group(1) or m.group(2)
            add(r, cat, pol, '%最大生命', float(v), off + m.start(), off + m.end(), off + (m.start(1) if m.group(1) else m.start(2)))
    for m in re.finditer(r'反彈[^，。；]{0,12}?' + NUM + '%', t):
        if re.search(r'遭受|降低', t[max(0, m.start() - 4):m.end()]):
            continue  # 「遭受反彈傷害降低 N%」是減傷，不是反彈
        add(r, '反彈傷害', 'buff', '%受到傷害', float(m.group(1)), m.start(), m.end(), m.start(1))

# ---- 3. 文字寫明的封頂（不含疊層上限，疊層另表）----
CAP_EV = []
for r in R:
    t = r['nt']
    for m in re.finditer(r'(最多|最高|最大(?!生命)|上限)(?:可以?)?(?:累積|疊加|提升|增加|降低|減少|提高|恢復|為|至|\+|-)?\s*' + NUM + r'(%|格|回合|層|個|次|倍|級)?', t):
        unit = m.group(3) or ''
        if unit in ('次',):
            continue
        # 往前 40 字內、同一筆最近的數值事件，決定這個封頂屬於哪一類
        prev = [e for e in EV if e['id'] == r['id'] and not e['cap'] and e['pos'] < m.start() and m.start() - e['pos'] <= 40]
        ctx = t[max(0, m.start() - 20):m.start()]
        if unit in ('層', '級') or (unit == '個' and re.search(r'累積|疊加|層', ctx + m.group(0))):
            cat = '計數器上限（層／個／級）'
        elif unit == '個':
            cat = '個數上限（驅散、偷取、施加幾個）'
        elif unit == '回合':
            cat = '冷卻縮短' if '冷卻' in t[max(0, m.start() - 40):m.start()] else '持續回合上限'
        elif prev:
            near = max(prev, key=lambda e: e['pos'])
            cat = near['cat']
            if not unit or (unit == '%' and near['unit'].startswith('%')):
                unit = near['unit']
        else:
            cat = '（無法歸類：依比例成長，句中沒有可對應的數值）'
        CAP_EV.append({'id': r['id'], 'name': r['name'], 'group': r['group'], 'cat': cat, 'unit': unit or '（無單位）', 'val': float(m.group(2)),
                       'match': m.group(0), 'sentence': sentence_of(t, m.start(), m.end())[:220]})

# ---- 套用人工排除 ----
excluded = []
def is_excl(e, lst):
    for x in lst:
        if x['name'] == e['name'] and x['cat'] == e['cat'] and float(x['val']) == e['val'] and x.get('table', 'range') == lst_tag[id(lst)]:
            return x
    return None
lst_tag = {}
def apply_excl(events, tag):
    keep = []
    for e in events:
        hit = next((x for x in EXCL if x.get('table', 'range') == tag and x['name'] == e['name'] and x['cat'] == e['cat'] and float(x['val']) == e['val']), None)
        if hit:
            excluded.append({'table': tag, 'name': e['name'], 'cat': e['cat'], 'unit': e['unit'], 'val': e['val'], 'why': hit['why'], 'sentence': e['sentence']})
        else:
            keep.append(e)
    return keep

excluded.extend(AUTO_EXCL)
RANGE_ALL = apply_excl([e for e in EV if not e['cap']], 'range')
RANGE = [e for e in RANGE_ALL if not e['per_unit']]
PERU = [e for e in RANGE_ALL if e['per_unit']]
CAPS = apply_excl(CAP_EV + [dict(e, cap_from_stat=True) for e in EV if e['cap']], 'cap')

def q(vals):
    vals = sorted(vals)
    if len(vals) >= 4:
        qs = statistics.quantiles(vals, n=4, method='inclusive')
        return round(qs[0], 2), statistics.median(vals), round(qs[2], 2)
    return vals[0], statistics.median(vals), vals[-1]

def fmt(v):
    return int(v) if float(v).is_integer() else v

def ex(e):
    return {'name': e['name'], 'group': e['group'], 'val': fmt(e['val']), 'sentence': e['sentence']}

md = []
# ---- 表 1：單次數值範圍 ----
rows = []
by = collections.defaultdict(list)
for e in RANGE:
    by[(e['pol'], e['cat'], e['unit'])].append(e)
for (pol, cat, unit), lst in sorted(by.items(), key=lambda x: (x[0][0], -len(x[1]))):
    vals = [e['val'] for e in lst]
    p25, med, p75 = q(vals)
    lo = min(lst, key=lambda e: e['val']); hi = max(lst, key=lambda e: e['val'])
    rows.append({'polarity': '強化' if pol == 'buff' else '弱化', 'name': cat, 'unit': unit, 'count': len(vals), 'min': fmt(lo['val']), 'p25': fmt(p25),
                 'median': fmt(med), 'p75': fmt(p75), 'max': fmt(hi['val']), 'per_unit_count': sum(1 for e in lst if e['per_unit']),
                 'min_example': ex(lo), 'max_example': ex(hi)})
stats['V1_value_range'] = {'title': '強化／弱化每一類的單次數值範圍（不含寫明的封頂、不含「每 X」增量）', 'note':
    '單位不同分開算；「每移動 1 格／每有 1 個…提升 N%」的單位增量另列 V1b；已排除解析錯誤（見 V4_excluded）。P25／P75 用 inclusive 四分位法',
    'rows': rows}
prow = []
pby = collections.defaultdict(list)
for e in PERU:
    pby[(e['pol'], e['cat'], e['unit'])].append(e)
for (pol, cat, unit), lst in sorted(pby.items(), key=lambda x: (x[0][0], -len(x[1]))):
    vals = [e['val'] for e in lst]
    lo = min(lst, key=lambda e: e['val']); hi = max(lst, key=lambda e: e['val'])
    prow.append({'polarity': '強化' if pol == 'buff' else '弱化', 'name': cat, 'unit': unit, 'count': len(vals), 'min': fmt(lo['val']),
                 'median': fmt(statistics.median(vals)), 'max': fmt(hi['val']), 'min_example': ex(lo), 'max_example': ex(hi)})
stats['V1b_per_unit_increment'] = {'title': '「每 X」的單位增量（每移動 1 格、每有 1 個強化…）', 'rows': prow}
md.append('### V1 單次數值範圍\n')
md.append('| 正負 | 類別 | 單位 | 次數 | 最小 | P25 | 中位數 | P75 | 最大 | 其中「每X」增量 |')
md.append('|---|---|---|---:|---:|---:|---:|---:|---:|---:|')
for d in rows:
    md.append(f"| {d['polarity']} | {d['name']} | {d['unit']} | {d['count']} | {d['min']} | {d['p25']} | {d['median']} | {d['p75']} | {d['max']} | {d['per_unit_count']} |")
md.append('\n### V1b 每X增量\n')
md.append('| 正負 | 類別 | 單位 | 次數 | 最小 | 中位數 | 最大 | 最小例 | 最大例 |')
md.append('|---|---|---|---:|---:|---:|---:|---|---|')
for d in prow:
    md.append(f"| {d['polarity']} | {d['name']} | {d['unit']} | {d['count']} | {d['min']} | {d['median']} | {d['max']} | {d['min_example']['name']}「{d['min_example']['sentence'][:60]}」 | {d['max_example']['name']}「{d['max_example']['sentence'][:60]}」 |")
md.append('\n### V1 極值原文\n')
md.append('| 類別 | 單位 | 最小：技能（組）原文 | 最大：技能（組）原文 |')
md.append('|---|---|---|---|')
for d in rows:
    a, b = d['min_example'], d['max_example']
    md.append(f"| {d['name']} | {d['unit']} | {a['val']}：{a['name']}（{a['group']}）「{a['sentence'][:90]}」 | {b['val']}：{b['name']}（{b['group']}）「{b['sentence'][:90]}」 |")

# ---- 表 2：分組比較 ----
grow = []
for (pol, cat, unit), lst in sorted(by.items(), key=lambda x: (x[0][0], -len(x[1]))):
    allmed = statistics.median([e['val'] for e in lst])
    for g in GROUP_ORDER:
        gv = [e['val'] for e in lst if e['group'] == g]
        if not gv:
            continue
        gm = statistics.median(gv)
        flag = ''
        if len(gv) >= 5 and len(lst) >= 15 and (gm >= allmed * 1.5 or gm <= allmed / 1.5):
            flag = '偏高' if gm > allmed else '偏低'
        grow.append({'name': cat, 'unit': unit, 'group': g, 'count': len(gv), 'min': fmt(min(gv)), 'median': fmt(gm), 'max': fmt(max(gv)),
                     'overall_median': fmt(allmed), 'flag': flag})
stats['V2_value_range_by_group'] = {'title': '單次數值按來源分組', 'note': '旗標：該組至少 5 次、整類至少 15 次，且組中位數 ≥ 整體 1.5 倍（偏高）或 ≤ 1/1.5（偏低）', 'rows': grow}
md.append('\n### V2 分組（只列有旗標的）\n')
md.append('| 類別 | 單位 | 組 | 次數 | 最小 | 中位數 | 最大 | 整體中位數 | 旗標 |')
md.append('|---|---|---|---:|---:|---:|---:|---:|---|')
for d in grow:
    if d['flag']:
        md.append(f"| {d['name']} | {d['unit']} | {d['group']} | {d['count']} | {d['min']} | {d['median']} | {d['max']} | {d['overall_median']} | {d['flag']} |")

# ---- 表 3：寫明的封頂 ----
cby = collections.defaultdict(list)
for e in CAPS:
    cby[(e['cat'], e['unit'])].append(e)
crows = []
for (cat, unit), lst in sorted(cby.items(), key=lambda x: -len(x[1])):
    vals = [e['val'] for e in lst]
    lo = min(lst, key=lambda e: e['val']); hi = max(lst, key=lambda e: e['val'])
    dist = collections.Counter(fmt(v) for v in vals)
    crows.append({'name': cat, 'unit': unit, 'count': len(vals), 'min': fmt(lo['val']), 'median': fmt(statistics.median(vals)), 'max': fmt(hi['val']),
                  'distribution': ', '.join(f'{k}×{v}' for k, v in sorted(dist.items())), 'min_example': ex(lo), 'max_example': ex(hi)})
stats['V3_written_caps'] = {'title': '文字寫明的封頂（最多／最高／最大／上限 N）', 'note': '類別＝同一句前面最近的數值事件；單位是層或個的歸「疊層上限」；「最多 N 次」不列（是次數限制）', 'rows': crows}
md.append('\n### V3 寫明的封頂\n')
md.append('| 類別 | 單位 | 次數 | 最小 | 中位數 | 最大 | 分布 |')
md.append('|---|---|---:|---:|---:|---:|---|')
for d in crows:
    md.append(f"| {d['name']} | {d['unit']} | {d['count']} | {d['min']} | {d['median']} | {d['max']} | {d['distribution']} |")
md.append('\n### V3 極值原文\n')
for d in crows:
    a, b = d['min_example'], d['max_example']
    md.append(f"- {d['name']}（{d['unit']}）最小 {a['val']}：{a['name']}「{a['sentence'][:100]}」；最大 {b['val']}：{b['name']}「{b['sentence'][:100]}」")

stats['V4_excluded'] = {'title': '人工讀原文後排除的解析錯誤', 'rows': excluded}
md.append('\n### V4 排除清單\n')
for x in excluded:
    md.append(f"- [{x['table']}] {x['cat']} {fmt(x['val'])}{x['unit']}：{x['name']}——{x['why']}")

json.dump(stats, open(stats_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump({'range_events': RANGE, 'cap_events': CAPS}, open(os.path.join(outdir, 'vr_events.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
open(os.path.join(outdir, 'vr_tables.md'), 'w', encoding='utf-8').write('\n'.join(md))
print('range events', len(RANGE), 'cap events', len(CAPS), 'excluded', len(excluded))
