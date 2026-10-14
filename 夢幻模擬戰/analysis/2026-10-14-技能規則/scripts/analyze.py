# -*- coding: utf-8 -*-
"""夢戰技能規則統計。
用法：python analyze.py <corpus.json> <輸出目錄> [review_judgments.json]
產出：stats.json（所有表格的數字）、tables.md（同一份數字排成 markdown 表，給 findings.md 抄）、
      samples_to_review.json（誤判抽查樣本，seed 固定）、examples.json（每條規則的原文例句）
有給 review_judgments.json 時，把人工判讀結果算成誤判率寫進 stats.json。
"""
import json, re, sys, random, collections, statistics, os

corpus_path, outdir = sys.argv[1], sys.argv[2]
review_path = sys.argv[3] if len(sys.argv) > 3 else None
R = json.load(open(corpus_path, encoding='utf-8'))

def norm(t):
    t = re.sub(r'[“”"「」‘’\'『』]', '', t or '')
    t = t.replace('遠端', '遠程').replace('（', '(').replace('）', ')').replace('，', '，')
    return t

GEAR_STAT = re.compile(r'^([^。；]*?[+＋]\d+%)[。；，]?')
for r in R:
    r['nt'] = norm(r['text'])
    if r['kind'] == 'gear':
        # 專屬裝備第一句「生命+2%」是裝備本身的強化等級屬性（跟學長帳號的強化等級走，wiki 滿級寫 +10%），不是技能效果，剝掉
        m = GEAR_STAT.match(r['nt'])
        if m:
            r['gear_stat'] = m.group(1)
            r['nt'] = r['nt'][m.end():]

KIND_ZH = {'hero_skill': '英雄技能', 'talent': '天賦', 'rune': '鑄紋技能', 'gear': '專屬裝備技能', 'soldier': '士兵技能'}
KINDS = list(KIND_ZH)
ACT = [r for r in R if r['kind'] == 'hero_skill' and r['category'] != '被動']
PAS = [r for r in R if r['kind'] == 'hero_skill' and r['category'] == '被動']
GROUPS = {'主動技能': ACT, '被動技能': PAS}
for k in ['talent', 'rune', 'gear', 'soldier']:
    GROUPS[KIND_ZH[k]] = [r for r in R if r['kind'] == k]
GROUP_ORDER = list(GROUPS)
ALL = R

stats = {'_meta': {'corpus': os.path.abspath(corpus_path), 'total_records': len(R),
                   'note': '每個表格是 list of {name,count,pct}；pct 以 denominator 為分母（%，一位小數）。多標籤表的 pct 加總可超過 100'}}
md = []
examples = {}

def pct(n, d):
    return round(100.0 * n / d, 1) if d else 0.0

def table(key, title, rows, denom, note='', cols=None):
    """rows: list of (name, count[, extra dict])"""
    out = []
    for row in rows:
        name, cnt = row[0], row[1]
        d = {'name': name, 'count': cnt, 'pct': pct(cnt, denom)}
        if len(row) > 2 and row[2]:
            d.update(row[2])
        out.append(d)
    stats[key] = {'title': title, 'denominator': denom, 'note': note, 'rows': out}
    md.append(f'\n### {key}｜{title}\n')
    md.append(f'分母 {denom}。{note}\n')
    extra_cols = cols or []
    md.append('| 名稱 | 筆數 | 占比 |' + ''.join(f' {c} |' for c in extra_cols))
    md.append('|---|---:|---:|' + ''.join('---|' for _ in extra_cols))
    for d in out:
        md.append(f"| {d['name']} | {d['count']} | {d['pct']}% |" + ''.join(f" {d.get(c, '')} |" for c in extra_cols))

def matrix(key, title, rowdefs, groups, note=''):
    """rowdefs: list of (name, predicate(rec)->bool)。每列對每個分組算命中筆數。"""
    gnames = list(groups)
    out = []
    for name, pred in rowdefs:
        d = {'name': name}
        tot = 0
        for g in gnames:
            n = sum(1 for r in groups[g] if pred(r))
            d[g] = n
            tot += n
        d['count'] = tot
        d['pct'] = pct(tot, sum(len(groups[g]) for g in gnames))
        out.append(d)
    denom = {g: len(groups[g]) for g in gnames}
    stats[key] = {'title': title, 'denominator': denom, 'denominator_total': sum(denom.values()), 'note': note, 'rows': out}
    md.append(f'\n### {key}｜{title}\n')
    md.append('分母：' + '、'.join(f'{g} {denom[g]}' for g in gnames) + f'（合計 {sum(denom.values())}）。{note}\n')
    md.append('| 名稱 | 合計 | 合計占比 |' + ''.join(f' {g} |' for g in gnames))
    md.append('|---|---:|---:|' + ''.join('---:|' for _ in gnames))
    for d in out:
        md.append(f"| {d['name']} | {d['count']} | {d['pct']}% |" + ''.join(f" {d[g]} |" for g in gnames))

def collect_examples(key, regex, pool, n=3, w=50, flags=0):
    ex = []
    for r in pool:
        m = re.search(regex, r['text'], flags) or re.search(regex, r['nt'], flags)
        if m:
            src = r['text'] if re.search(regex, r['text'], flags) else r['nt']
            m = re.search(regex, src, flags)
            # 取整句（以。；為界）
            s = src.rfind('。', 0, m.start()); s2 = src.rfind('；', 0, m.start()); s = max(s, s2) + 1
            e_candidates = [i for i in (src.find('。', m.end()), src.find('；', m.end())) if i != -1]
            e = min(e_candidates) + 1 if e_candidates else len(src)
            snippet = src[s:e]
            if len(snippet) > 160:
                a = max(0, m.start() - w); snippet = '…' + src[a:m.end() + w] + '…'
            ex.append({'kind': KIND_ZH[r['kind']], 'name': r['name'], 'owners': r['owners'][:3], 'src': r['src'], 'quote': snippet})
        if len(ex) >= n:
            break
    examples[key] = ex
    return ex

def has(regex):
    c = re.compile(regex)
    return lambda r: bool(c.search(r['nt']))

# =============== 1. 技能分類 ===============
table('1a_kind_counts', '語料組成（五種技能來源）',
      [(KIND_ZH[k], sum(1 for r in R if r['kind'] == k), {'ingame': sum(1 for r in R if r['kind'] == k and r['src'] == 'ingame'),
                                                         'wiki': sum(1 for r in R if r['kind'] == k and r['src'] == 'wiki')}) for k in KINDS],
      len(R), '英雄技能＝merged/skills.json；天賦只取遊戲畫面 214；鑄紋＝已解鎖 52（畫面）＋可獲得 55（wiki 全文）；士兵 165 筆裡 154 筆有技能文字', cols=['ingame', 'wiki'])
hs = [r for r in R if r['kind'] == 'hero_skill']
cat_c = collections.Counter(r['category'] or '（無）' for r in hs)
table('1b_hero_skill_category', '英雄技能 916 顆的分類欄（遊戲標的分類，不是關鍵字推的）',
      [(k, v) for k, v in cat_c.most_common()], len(hs), '被動 156 顆之外都算主動技能（760 顆）')
# 被動技能的 COST
table('1c_passive_cost', '被動技能的 COST', [(str(k), v) for k, v in sorted(collections.Counter(r['cost'] for r in PAS).items(), key=lambda x: str(x[0]))], len(PAS), 'None＝wiki 版沒抓 COST')
table('1d_active_cost', '主動技能的 COST', [(str(k), v) for k, v in sorted(collections.Counter(r['cost'] for r in ACT).items(), key=lambda x: str(x[0]))], len(ACT), 'None＝wiki 版沒抓 COST')

ACT_TAGS = [
    ('單體傷害', lambda r: r['category'] in ('物理傷害', '魔法傷害') and '範圍傷害' not in r['nt']),
    ('範圍傷害（文字有「範圍傷害」）', has(r'範圍傷害')),
    ('附帶治療／回血', has(r'恢復[^。；]{0,20}生命')),
    ('位移或傳送（擊退、拉拽、撞開、互換、傳送）', has(r'\[位移\]|擊退|拉拽|撞開|互換|傳送')),
    ('行動後再動（再次行動／額外行動 N 格）', has(r'再次行動|再行動|額外行動|再次移動|可再次攻擊')),
    ('召喚', has(r'召喚')),
    ('驅散（強化或弱化）', has(r'(?<![不法被能])驅散')),
    ('護盾', has(r'護盾')),
    ('技能替換（使用後換成另一顆）', has(r'替換為')),
    ('多選一（選擇施放 1 種）', has(r'選擇(施放|釋放)?\s*(1|一)\s*(種|個)')),
    ('有使用次數上限', has(r'最大使用次數|使用次數')),
    ('附帶被動段（文字含 [被動]）', has(r'\[被動\]')),
]
table('1e_active_tags', '主動技能 760 顆的功能標籤（多標籤，關鍵字判定）',
      [(n, sum(1 for r in ACT if p(r))) for n, p in ACT_TAGS], len(ACT), '一顆可同時有多個標籤；關鍵字清單見附錄 A')
for n, p in ACT_TAGS:
    examples['1e:' + n] = [{'name': r['name'], 'quote': r['text'][:90]} for r in ACT if p(r)][:3]

# 主動技能的「主要效果」單選分類（給圓餅圖）：分類欄優先，再看文字
def act_primary(r):
    c = r['category']
    if c in ('物理傷害', '魔法傷害'):
        return '傷害（' + c + '）'
    if c == '治療':
        return '治療'
    if c == '召喚' or re.search(r'召喚', r['nt']) and c == '主動':
        return '召喚'
    if c == '變身':
        return '變身'
    if c == '超絕強化':
        return '超絕強化（陣營大 buff）'
    if c in ('支援', '主動'):
        t = r['nt']
        if re.search(r'\[位移\]|擊退|拉拽|撞開|互換|傳送', t):
            return '位移／傳送'
        if re.search(r'恢復[^。；]{0,20}生命', t) and not re.search(r'造成[\d.]+倍', t):
            return '純輔助：含回血'
        return '純輔助：強化／弱化／其他'
    return '其他：' + str(c)
pc = collections.Counter(act_primary(r) for r in ACT)
table('1f_active_primary', '主動技能的主要效果（單選：先看遊戲分類欄，支援／主動類再看文字）',
      [(k, v) for k, v in pc.most_common()], len(ACT), '支援／主動類裡含位移字眼者歸「位移／傳送」')

def owner_bin(n):
    return '專屬（1 位英雄）' if n <= 1 else ('2–5 位共用' if n <= 5 else ('6–20 位共用' if n <= 20 else '21 位以上共用'))
for gname, pool in [('主動', ACT), ('被動', PAS)]:
    oc = collections.Counter(owner_bin(len(r['owners'])) for r in pool)
    table(f'1g_owners_{gname}', f'{gname}技能被幾位英雄共用', [(k, oc[k]) for k in ['專屬（1 位英雄）', '2–5 位共用', '6–20 位共用', '21 位以上共用']], len(pool),
          '共用＝merged/skills.json 的 heroes 名單人數；最常共用的主動：氣刃 26、大喝 25、斬陽 23；被動：壓制 15、破甲 14')

pre = re.compile(r'^[^。；，]*?[+＋]\d+%')
table('1h_stat_prefix', '鑄紋／專屬裝備開頭先寫一條「屬性+N%」的比例',
      [('鑄紋技能', sum(1 for r in GROUPS['鑄紋技能'] if pre.match(norm(r['text']))), {'組內筆數': len(GROUPS['鑄紋技能'])}),
       ('專屬裝備技能', sum(1 for r in GROUPS['專屬裝備技能'] if pre.match(norm(r['text']))), {'組內筆數': len(GROUPS['專屬裝備技能'])})],
      len(GROUPS['鑄紋技能']) + len(GROUPS['專屬裝備技能']), '專屬裝備的那條屬性隨強化等級變（遊戲畫面 +1～2%、wiki 滿級 +10%），統計強化／檔位時已剝掉', cols=['組內筆數'])

matrix('1i_role_markers', '各來源的角色記號（判斷「這類技能在做什麼」）', [
    ('提到「天賦」（改寫或加強天賦）', has(r'天賦')),
    ('提到具名效果 [XX]（不含 [被動][主動] 等類型標籤）', lambda r: any(b not in ('被動', '主動', '物理傷害', '魔法傷害', '支援', '治療', '召喚', '變身', '超絕強化', '指揮', '固定傷害', '觸發冷卻', '位移', '護盾', '免疫') for b in re.findall(r'\[([^\]]{1,10})\]', r['nt']))),
    ('以「士兵」為主詞', has(r'士兵')),
    ('含「不可驅散」', has(r'(不可|無法|不能)(被)?驅散|(不可|無法)(被)?免疫[和與]驅散')),
    ('含「行動結束」', has(r'行動結束')),
], GROUPS)

# =============== 2. 主動技能參數 ===============
cd_c = collections.Counter(r['cd'] for r in ACT)
table('2a_active_cd', '主動技能冷卻回合分布', [('無冷卻（欄位寫「無」）' if k == 0 else ('未載' if k is None else f'{k} 回合'), v)
                                    for k, v in sorted(cd_c.items(), key=lambda x: (x[0] is None, x[0] if x[0] is not None else 99))], len(ACT),
      '未載＝多選一或依形態變化的技能，遊戲畫面沒寫單一冷卻')
cd_by_cat = {}
for cat in ['物理傷害', '魔法傷害', '支援', '治療', '主動', '超絕強化', '變身', '召喚']:
    v = [r['cd'] for r in ACT if r['category'] == cat and r['cd'] is not None]
    cd_by_cat[cat] = v
table('2b_cd_by_category', '各分類的冷卻中位數與眾數',
      [(cat, len(v), {'中位數': statistics.median(v) if v else '', '眾數': collections.Counter(v).most_common(1)[0][0] if v else '',
                      '無冷卻筆數': sum(1 for x in v if x == 0)}) for cat, v in cd_by_cat.items()], len(ACT),
      '筆數＝該分類有冷卻數字的技能數', cols=['中位數', '眾數', '無冷卻筆數'])
rng_c = collections.Counter(r['range'] or '未載' for r in ACT)
table('2c_active_range', '主動技能射程分布', [(k, v) for k, v in rng_c.most_common()], len(ACT))
area_c = collections.Counter(r['area'] or '未載' for r in ACT)
table('2d_active_area', '主動技能範圍（area 欄）分布', [(k, v) for k, v in area_c.most_common()], len(ACT),
      '「N格」＝以落點為中心的菱形半徑 N（推論：遊戲畫面只寫格數，形狀由「直線」「圈」另標）；「N圈」＝方形一圈')

mult_rows = []
mult_data = {}
for cat in ['物理傷害', '魔法傷害']:
    for shape in ['單體', '範圍']:
        vals = []
        for r in ACT:
            if r['category'] != cat:
                continue
            m = re.search(r'造成(?:自身[^，。；]{0,6})?(\d+(?:\.\d+)?)倍(?:的)?(範圍)?傷害', r['nt'])
            if not m:
                continue
            is_area = bool(m.group(2)) or '範圍傷害' in r['nt'][:80]
            if (shape == '範圍') == is_area:
                vals.append(float(m.group(1)))
        mult_data[f'{cat}-{shape}'] = vals
        if vals:
            q = statistics.quantiles(vals, n=4) if len(vals) >= 4 else [min(vals), statistics.median(vals), max(vals)]
            mult_rows.append((f'{cat}・{shape}', len(vals), {'最小': min(vals), 'P25': round(q[0], 2), '中位數': statistics.median(vals),
                                                         'P75': round(q[2], 2), '最大': max(vals), '眾數': collections.Counter(vals).most_common(1)[0][0]}))
n_dmg = sum(1 for r in ACT if r['category'] in ('物理傷害', '魔法傷害'))
table('2e_multiplier', '傷害倍率（取第一個「造成 X 倍傷害」）', mult_rows, n_dmg,
      f'分母＝物理＋魔法傷害技能 {n_dmg} 顆；抓不到倍率的（固定傷害、倍率寫在被動段等）不列', cols=['最小', 'P25', '中位數', 'P75', '最大', '眾數'])
# 倍率分箱
bins = [(0, 0.3), (0.3, 0.5), (0.5, 1.0), (1.0, 1.3), (1.3, 1.5), (1.5, 1.7), (1.7, 2.0), (2.0, 99)]
for key, vals in mult_data.items():
    stats.setdefault('2f_multiplier_bins', {'title': '傷害倍率分箱（左閉右開）', 'series': {}})['series'][key] = [
        {'name': f'{a}–{b if b < 99 else "以上"}', 'count': sum(1 for v in vals if a <= v < b), 'pct': pct(sum(1 for v in vals if a <= v < b), len(vals))} for a, b in bins]
md.append('\n### 2f_multiplier_bins｜傷害倍率分箱\n')
md.append('| 區間 | ' + ' | '.join(mult_data) + ' |')
md.append('|---|' + '---:|' * len(mult_data))
for i, (a, b) in enumerate(bins):
    md.append(f'| {a}–{b if b < 99 else "以上"} | ' + ' | '.join(str(stats['2f_multiplier_bins']['series'][k][i]['count']) for k in mult_data) + ' |')

again = [r for r in ACT if re.search(r'再次行動|再行動|額外行動|再次移動|可再次攻擊', r['nt'])]
table('2g_act_again', '行動後再動：主動技能中寫「再次行動／額外行動 N 格／可再次攻擊」的', [(c, sum(1 for r in again if r['category'] == c)) for c in collections.Counter(r['category'] for r in again)],
      len(ACT), f'合計 {len(again)} 顆')
moves = collections.Counter(m for r in again for m in re.findall(r'(?:額外|再次|再)行動(\d)格', r['nt']))
table('2h_again_cells', '再動格數（額外／再次行動 N 格）', [(f'{k} 格', v) for k, v in sorted(moves.items())], len(again), '同一顆寫多個數字時各算一次')
no_tick = [r for r in R if '回合數不會減少' in r['nt']]
table('2i_no_tick', '「使用此技能後身上強化效果回合數不會減少」註記', [(KIND_ZH[k], sum(1 for r in no_tick if r['kind'] == k)) for k in KINDS], len(R),
      f'共 {len(no_tick)} 筆；其中同時寫再動的 {sum(1 for r in no_tick if re.search(r"再次行動|再行動|額外行動|可再次攻擊", r["nt"]))} 筆')
collect_examples('2i_no_tick', r'回合數不會減少', R)

# =============== 3. 觸發時機詞彙 ===============
TIMING = [
    ('戰鬥前（進入戰鬥前／戰前）', r'戰鬥前|戰前'),
    ('戰鬥中（進入戰鬥時／戰鬥中）', r'進入戰鬥時|(?<!場)戰鬥中|(?<!場)戰鬥時(?!間)'),
    ('戰鬥後（戰後／戰鬥結束後）', r'戰鬥後|戰後|戰鬥結束後'),
    ('主動攻擊方（主動攻擊／主動進入戰鬥）', r'主動(攻擊|進入戰鬥)'),
    ('被攻擊方（被…攻擊）', r'(?<!\[)被(?!動)[^，。；]{0,4}攻擊'),
    ('行動結束時', r'行動結束'),
    ('回合開始時', r'回合開始'),
    ('回合結束時', r'回合結束'),
    ('戰場開場（每場戰鬥開始／戰鬥開始時）', r'戰鬥開始'),
    ('使用／釋放技能時或後', r'(使用|釋放)[^，。；]{0,8}技能(時|後)|使用後|釋放後'),
    ('技能命中／攻擊前', r'攻擊前|命中[^，。；]{0,6}前'),
    ('受到傷害後', r'(受到|遭受)[^，。；]{0,8}傷害(後|時)'),
    ('擊殺敵軍時', r'(?<!未造成)(?<!未)(擊殺|擊敗)'),
    ('死亡時（自己或他人）', r'死亡(時|後)'),
    ('遭受致命傷害時', r'致命傷害|一擊致命'),
    ('移動距離（每移動 N 格／移動過幾格）', r'每移動|移動(了|過)?(超過|至少|不少於|大於)?\d+格(以上|及以上|後|時)|累積移動|未進行過移動|移動距離'),
    ('生命門檻（高於／低於 X%）', r'生命(值)?[^，。；]{0,4}(高於|低於|大於|小於|不低於|不高於|少於|多於)[^，。；]{0,2}\d+%|生命\d+%以[上下]'),
    ('獲得或遭受強化／弱化時', r'(獲得|遭受|被施加)[^，。；]{0,6}(強化|弱化)(效果|狀態)(時|後)'),
    ('被治療時', r'(受到|遭受|被)[^，。；]{0,6}治療(時|後)'),
    ('機率觸發（X% 機率）', r'\d+%(的)?機率'),
    ('觸發冷卻（間隔 N 回合）', r'觸發冷卻|需要間隔\d+回合'),
    ('次數限制（每場／每回合最多 N 次）', r'每場戰鬥(最多|僅|只)|每回合(最多|只|僅)|最多觸發|只能觸發'),
]
matrix('3a_timing', '觸發時機詞彙：含該時機的技能筆數', [(n, has(p)) for n, p in TIMING], GROUPS,
       '一筆可含多個時機。夢戰的「戰鬥」＝兩支部隊一次交戰（攻擊＋反擊），不是整場關卡；整場關卡叫「每場戰鬥」')
for n, p in TIMING:
    collect_examples('3a:' + n, p, ACT + PAS + GROUPS['天賦'], n=3)
# 時機詞彙的實際字串計次（全語料，一筆可多次）
tok = collections.Counter()
for r in R:
    for m in re.finditer(r'(進入戰鬥前|戰鬥前|戰前|進入戰鬥時|戰鬥中|戰鬥後|戰後|戰鬥結束後|主動攻擊進入戰鬥時|主動攻擊進入戰鬥後|主動攻擊進入戰鬥前|被攻擊進入戰鬥時|被攻擊進入戰鬥後|被攻擊進入戰鬥前|行動結束時|行動結束後|回合開始時|回合結束時|每場戰鬥開始時|戰鬥開始時|擊殺敵軍(時|後)|死亡時|受到傷害後|遭受傷害後|攻擊前|使用後|釋放後)', r['nt']):
        tok[m.group(1) if m.group(1) else m.group(0)] += 1
table('3b_timing_tokens', '時機字串原樣計次（全語料，同一筆出現兩次算兩次）', [(k, v) for k, v in tok.most_common()], sum(tok.values()), '占比＝占全部時機字串')

# =============== 4/5. 強化與弱化 ===============
STAT = r'(攻擊|智力|防禦|魔防|技巧|全屬性|攻防(?:能力)?|生命|暴擊率|暴擊傷害|傷害|移動力|射程|治療效果|冷卻時間)'
DIR = r'(提升|增加|提高|降低|減少|下降|\+|-|－)'
stat_re = re.compile(r'(?P<pre>[^，。；:：]{0,10}?)' + STAT + r'(?:[^，。；\d]{0,3}?)' + DIR + r'\s*(\d+)(%?)')

def stat_events(t):
    """回傳 [(類型, 正負向, 數值, 是否百分比, 片段)]。正負向：buff 或 debuff。"""
    ev = []
    for m in stat_re.finditer(t):
        pre, stat, d, val, p = m.group('pre'), m.group(2), m.group(3), int(m.group(4)), m.group(5) == '%'
        up = d in ('提升', '增加', '提高', '+')
        recv = bool(re.search(r'(遭受|受到|受)[^，。；]{0,6}$', pre)) or bool(re.search(r'遭受|受到', pre[-6:]))
        if stat in ('暴擊率', '暴擊傷害'):
            if recv:
                typ = ('防暴擊（遭受暴擊率降低）', 'buff') if not up else ('受暴擊提升', 'debuff')
            else:
                typ = ('暴擊提升', 'buff') if up else ('暴擊降低', 'debuff')
        elif stat == '傷害':
            if recv:
                typ = ('減傷（遭受傷害降低）', 'buff') if not up else ('易傷（遭受傷害提升）', 'debuff')
            else:
                typ = ('增傷（造成傷害提升）', 'buff') if up else ('降傷（造成傷害降低）', 'debuff')
        elif stat == '治療效果':
            if recv:
                typ = ('受治療提升', 'buff') if up else ('受治療降低', 'debuff')
            else:
                typ = ('治療效果提升', 'buff') if up else ('治療效果降低', 'debuff')
        elif stat == '冷卻時間':
            typ = ('冷卻縮短', 'buff') if not up else ('冷卻增加', 'debuff')
        elif stat in ('移動力', '射程'):
            typ = ('移動力／射程提升', 'buff') if up else ('移動力／射程降低', 'debuff')
        else:
            if recv:
                continue
            typ = ('屬性提升（攻智防魔技生命）', 'buff') if up else ('屬性降低（攻智防魔技生命）', 'debuff')
        ev.append((typ[0], typ[1], val, p, t[max(0, m.start()):m.end()]))
    return ev

for r in R:
    r['ev'] = stat_events(r['nt'])

BUFF_KW = [
    ('護盾', r'護盾'),
    ('免疫（含 [免疫] 與免疫特定效果）', r'(?<!無法)(?<!法被)(?<!不可)(?<!驅散和)(?<!驅散與)免疫'),
    ('不死／抵擋致命傷害', r'抵擋[^，。；]{0,4}致命|不會死亡|無法被一擊致命|免除[^，。；]{0,4}致命'),
    ('行動後再動', r'(?<!觸發)(再次行動|再行動|額外行動|再次移動)(?!時)'),
    ('先攻（先於敵軍攻擊）', r'先於敵(軍|方)[^，。；]{0,4}攻擊|先攻'),
    ('反擊強化（可反擊遠程等）', r'(?<!無法)(?<!不能)(?<!無法進行)反擊'),
    ('反彈傷害', r'(?<!遭受)反彈'),
    ('吸血（恢復造成傷害 X% 的生命）', r'恢復[^，。；]{0,10}造成[^，。；]{0,3}傷害[^，。；]{0,6}生命|造成傷害[^，。；]{0,4}\d+%的生命'),
    ('回血（恢復生命）', r'恢復[^，。；]{0,15}生命'),
    ('護衛（替友軍承受攻擊）', r'替[^，。；]{0,8}承受|護衛範圍'),
    ('無視（防禦／護衛／地形／減免）', r'無視[^，。；]{0,6}(防禦|魔防|護衛|地形|減免|阻擋)'),
    ('隨機強化效果', r'隨機[^，。；]{0,4}強化(效果|狀態)'),
    ('[指揮] 光環', r'\[指揮\]'),
    ('超絕強化（陣營大 buff）', r'超絕強化|攻防能力大幅提升'),
]
DEBUFF_KW = [
    ('無法反擊', r'無法反擊|不能反擊'),
    ('沉默（無法使用主動技能）', r'無法使用主動技能'),
    ('定身（無法移動）', r'(?<!\()無法移動'),
    ('眩暈／無法行動', r'眩暈|暈眩|無法行動|催眠|冰凍'),
    ('禁療（無法被治療／治療反轉）', r'無法(被|遭受)治療|傷口詛咒|治療反轉|治療[^，。；]{0,4}轉(化|變)為傷害'),
    ('禁強化（無法遭受強化）', r'無法(遭受|獲得)強化'),
    ('禁護衛（無法護衛／無法被護衛）', r'無法(進行)?護衛|不能護衛|無法被護衛'),
    ('持續傷害（灼燒等，行動結束時受固定傷害）', r'灼燒|流血|行動結束時[^。；]{0,10}受到[^。；]{0,15}固定傷害'),
    ('偷取／轉移強化', r'偷取|轉移[^，。；]{0,4}(強化|弱化)|複製'),
    ('隨機弱化效果', r'隨機[^，。；]{0,4}弱化(效果|狀態)'),
    ('強力弱化效果', r'強力弱化'),
    ('嘲諷', r'嘲諷'),
]

def buff_types(r):
    s = set(e[0] for e in r['ev'] if e[1] == 'buff')
    for n, p in BUFF_KW:
        if re.search(p, r['nt']):
            s.add(n)
    return s

def not_immune_ctx(t, m):
    # 「免疫“無法使用主動技能”」這類是免疫，不是施加弱化：同一句前 14 字內有「免疫」就不算
    a = max(t.rfind('。', 0, m.start()), t.rfind('；', 0, m.start()), m.start() - 14)
    return '免疫' not in t[a:m.start()]

def debuff_types(r):
    s = set(e[0] for e in r['ev'] if e[1] == 'debuff')
    for n, p in DEBUFF_KW:
        if any(not_immune_ctx(r['nt'], m) for m in re.finditer(p, r['nt'])):
            s.add(n)
    return s

for r in R:
    r['bt'] = buff_types(r); r['dt'] = debuff_types(r)

def type_matrix(key, title, attr, note):
    names = collections.Counter(n for r in R for n in r[attr])
    matrix(key, title, [(n, (lambda n: lambda r: n in r[attr])(n)) for n, _ in names.most_common()], GROUPS, note)

type_matrix('4a_buff_types', '強化（buff）種類：含該種類的技能筆數', 'bt',
            '數值型（屬性、增傷、減傷、暴擊、移動、冷卻）由「屬性詞＋提升/降低＋數字」解析，帶「遭受／受到」前綴的方向反轉；其餘用關鍵字')
type_matrix('5a_debuff_types', '弱化（debuff）種類：含該種類的技能筆數', 'dt',
            '同上。注意數值型會把「自身代價」（例：糖分過量 自身造成傷害降低）也算成弱化，見附錄抽查')
table('4b_any_buff', '至少含一種強化的技能', [(g, sum(1 for r in GROUPS[g] if r['bt'])) for g in GROUP_ORDER], len(R), '各列占比以全語料為分母；各組自己的占比見 matrix')
table('5b_any_debuff', '至少含一種弱化的技能', [(g, sum(1 for r in GROUPS[g] if r['dt'])) for g in GROUP_ORDER], len(R))
for n, p in BUFF_KW + DEBUFF_KW:
    collect_examples('4/5:' + n, p, ACT + PAS + GROUPS['天賦'] + GROUPS['專屬裝備技能'], n=3)

# 持續回合：以「句」為單位（。；切），句子裡有弱化詞就歸弱化句、只有強化詞歸強化句
def clause_kind(c):
    ev = stat_events(c)
    b = any(e[1] == 'buff' for e in ev) or any(re.search(p, c) for _, p in BUFF_KW)
    d = any(e[1] == 'debuff' for e in ev) or any(re.search(p, c) for _, p in DEBUFF_KW) or re.search(r'弱化', c)
    if d and not b:
        return 'debuff'
    if b and not d:
        return 'buff'
    if b and d:
        return 'both'
    return 'other'

dur = {'buff': collections.Counter(), 'debuff': collections.Counter(), 'both': collections.Counter(), 'other': collections.Counter()}
for r in R:
    for c in re.split(r'[。；]', r['nt']):
        for m in re.finditer(r'持續(\d+)回合', c):
            dur[clause_kind(c)][int(m.group(1))] += 1
alld = collections.Counter()
for k in dur:
    alld.update(dur[k])
rows = []
for n in sorted(alld):
    rows.append((f'{n} 回合', alld[n], {'強化句': dur['buff'][n], '弱化句': dur['debuff'][n], '兩者都有': dur['both'][n], '其他': dur['other'][n]}))
table('4c_duration', '「持續 N 回合」的 N 分布（全語料，一句一次）', rows, sum(alld.values()),
      '句子＝以。；切開；強化句／弱化句由該句的關鍵字判定', cols=['強化句', '弱化句', '兩者都有', '其他'])
for k in ['buff', 'debuff']:
    tot = sum(dur[k].values())
    stats['4c_duration'][k + '_share'] = {f'{n}': pct(v, tot) for n, v in sorted(dur[k].items())}
# 有強化卻沒寫持續（常駐／條件式）
perm = collections.Counter()
for g in GROUP_ORDER:
    perm[g] = sum(1 for r in GROUPS[g] if r['bt'] and '持續' not in r['nt'])
table('4d_buff_no_duration', '含強化但全文沒有「持續」二字（常駐或條件即時生效）', [(g, perm[g], {'組內含強化筆數': sum(1 for r in GROUPS[g] if r['bt'])}) for g in GROUP_ORDER],
      len(R), '占比以全語料為分母', cols=['組內含強化筆數'])

STACK = [
    ('超絕強化互斥（無法和其他超絕強化疊加）', r'無法(和|與)(其他的?)?超絕強化(技能)?疊加'),
    ('指揮同類不同時生效', r'與(其他|同類)指揮技能不能同時生效'),
    ('可累積／可疊加（具名效果疊層）', r'可(以)?(累積|疊加)'),
    ('寫明疊層上限（最多／最高 N 層或個）', r'(最多|最高|最大)(可以?)?(累積|疊加)?\s*(為)?\d+\s*(層|個|次)?|可(累積|疊加)\d+(層|個|次)'),
    ('明寫不可疊加', r'(無法|不可|不能)[^，。；]{0,4}疊加|不可累積|效果無法疊加'),
    ('疊層上限被其他技能 +N', r'(疊加上限|累積數量|累積層數|可以累積的[^，。；]{0,6}個數)\+\d'),
    ('疊加或施加時刷新持續回合', r'刷新[^，。；]{0,12}(持續回合|持續時間)|持續回合回復至最大|刷新至最大持續回合'),
    ('依身上強化／弱化個數加成', r'每(有|擁有)\s*(1|一)個?[^，。；]{0,4}(強化|弱化)(效果|狀態)|(強化|弱化)(效果|狀態)數量'),
    ('改寫持續回合（回合數 +N／-N）', r'(回合數|持續回合|持續時間)\s*[+＋\-－]\s*\d'),
    ('使用後強化回合數不減', r'回合數不會減少'),
    ('地形效果覆蓋優先序', r'地形覆蓋優先'),
    ('共用疊層上限', r'共用\d+層'),
]
matrix('4e_stack_rules', '疊加／計數規則的字面出現次數', [(n, has(p)) for n, p in STACK], GROUPS,
       '技能文字裡「沒有」任何一條通用的「同屬性 buff 怎麼疊」規則；以上全是例外條款')
for n, p in STACK:
    collect_examples('4e:' + n, p, R, n=4)
caps = collections.Counter()
for r in R:
    for m in re.finditer(r'(?:可(?:以)?(?:累積|疊加)[^。；]{0,12}?(?:最多|最高|最大)(?:可以)?(?:累積|疊加)?\s*(?:為)?(\d+)|(?:最多|最高|最大)(?:可以)?(?:累積|疊加)\s*(\d+)|可(?:累積|疊加)(\d+)(?:層|個|次))', r['nt']):
        v = next(x for x in m.groups() if x)
        caps[int(v)] += 1
table('4f_stack_caps', '具名效果疊層上限 N 的分布', [(f'{k}', v) for k, v in sorted(caps.items())], sum(caps.values()), '只抓「可累積/疊加…最多 N」的句型')

# 弱化持續回合單獨表（給第 5 節）
table('5c_debuff_duration', '弱化句的持續回合', [(f'{n} 回合', v) for n, v in sorted(dur['debuff'].items())], sum(dur['debuff'].values()))
table('4g_buff_duration', '強化句的持續回合', [(f'{n} 回合', v) for n, v in sorted(dur['buff'].items())], sum(dur['buff'].values()))

SUP = [r for r in ACT if r['category'] == '超絕強化']
table('4h_superbuff_4turn', '超絕強化技能寫「持續 4 回合」的比例', [('持續4回合', sum(1 for r in SUP if '持續4回合' in r['nt']))], len(SUP), '分母＝分類欄為超絕強化的 38 顆')

# =============== 6. 驅散與免疫 ===============
DISPEL = [
    ('驅散敵方強化', r'(?<![不法被能])驅散[^，。；]{0,10}強化(效果|狀態)'),
    ('驅散／清除己方弱化', r'(驅散|清除)[^，。；]{0,10}弱化(效果|狀態)'),
    ('偷取強化', r'偷取[^，。；]{0,8}強化'),
    ('轉移／複製效果', r'轉移[^，。；]{0,6}(強化|弱化)|複製'),
    ('[免疫]（具名狀態）', r'\[免疫\]'),
    ('免疫所有／全部弱化', r'免疫(所有|全部)[^，。；]{0,2}弱化'),
    ('免疫特定效果（免疫「XX」）', r'(?<!無法)(?<!法被)(?<!不可)(?<!驅散和)(?<!驅散與)免疫(?!(所有|全部)[^，。；]{0,2}弱化)(?!\])(?![和與]驅散)[^，。；]{1,12}'),
    ('免疫位移', r'免疫[^，。；]{0,3}位移|無法被位移'),
    ('不可驅散', r'(不可|無法|不能)(被)?驅散|(不可|無法)(被)?免疫[和與]驅散'),
    ('無法免疫（穿透免疫）', r'(無法|不可|不能)(被)?(驅散[和與])?免疫'),
    ('免疫下 N 個弱化（次數型）', r'免疫下\d*個?[^，。；]{0,4}弱化'),
    ('降低弱化持續回合', r'弱化[^，。；]{0,6}(持續回合|回合數)[^，。；]{0,2}[-－]'),
]
matrix('6a_dispel_immune', '驅散、免疫、不可驅散', [(n, has(p)) for n, p in DISPEL], GROUPS)
for n, p in DISPEL:
    collect_examples('6a:' + n, p, ACT + PAS + GROUPS['天賦'] + GROUPS['專屬裝備技能'], n=3)
dn = collections.Counter()
for r in R:
    for m in re.finditer(r'驅散[^，。；]{0,8}?(\d+|所有|全部)個?[^，。；]{0,2}(強化|弱化)', r['nt']):
        dn[(m.group(2), '所有' if m.group(1) in ('所有', '全部') else m.group(1))] += 1
table('6b_dispel_count', '一次驅散幾個', [(f'{k[0]}×{k[1]}', v) for k, v in sorted(dn.items(), key=lambda x: (x[0][0], x[0][1]))], sum(dn.values()))
# 主動技能裡「不可驅散」占比
UND = dict(DISPEL)['不可驅散']
table('6c_undispellable_share', '各組含「不可驅散」的比例', [(g, sum(1 for r in GROUPS[g] if re.search(UND, r['nt'])), {'組內筆數': len(GROUPS[g]), '組內占比': pct(sum(1 for r in GROUPS[g] if re.search(UND, r['nt'])), len(GROUPS[g]))}) for g in GROUP_ORDER],
      len(R), cols=['組內筆數', '組內占比'])

# =============== 7. 光環與條件 ===============
COND = [
    ('[指揮] 光環', r'\[指揮\]'),
    ('周圍 N 格／圈（以自身為中心）', r'周圍\d+(格|圈)'),
    ('N 格範圍內（未寫周圍）', r'(?<!周圍)\d+格(範圍)?(以)?內'),
    ('相鄰', r'相鄰'),
    ('全場', r'全場'),
    ('地形條件（樹林、山地、水中…或泛稱地形）', r'樹林|山地|水中|草地|沙漠|城牆|平地|地形|水域|雪地|沼澤'),
    ('生命門檻', r'生命(值)?[^，。；]{0,4}(高於|低於|大於|小於|不低於|不高於|少於|多於)[^，。；]{0,2}\d+%|生命\d+%以[上下]'),
    ('兵種條件／特效（步槍騎飛水弓法僧魔刺）', r'步兵|槍兵|騎兵|飛兵|水兵|弓兵|法師|僧侶|魔物|刺客'),
    ('近戰／遠程士兵條件', r'(近戰|遠程)(士兵|部隊|攻擊|傷害)'),
    ('陣營條件（「XX」友軍）', r'[“"「][^”"」]{2,8}[”"」](友軍|部隊|陣營)'),
    ('性別條件', r'女性|男性'),
    ('身上有強化／弱化為條件', r'(擁有|具有|有|存在)[^，。；]{0,6}(強化|弱化)(效果|狀態)'),
    ('距離／移動格數為條件', r'每移動|每間隔|間隔\d格|距離'),
]
def has_raw_or_norm(p):
    c = re.compile(p)
    return lambda r: bool(c.search(r['text']) or c.search(r['nt']))
matrix('7a_conditions', '光環、地形、HP、兵種等條件寫法', [(n, has_raw_or_norm(p)) for n, p in COND], GROUPS)
for n, p in COND:
    collect_examples('7a:' + n, p, ACT + PAS + GROUPS['天賦'], n=3)
rad = collections.Counter()
for r in R:
    for m in re.finditer(r'周圍(\d+)(格|圈)', r['nt']):
        rad[f'周圍{m.group(1)}{m.group(2)}'] += 1
table('7b_aura_radius', '「周圍 N 格／圈」的 N', [(k, v) for k, v in sorted(rad.items())], sum(rad.values()))
cmdr = collections.Counter()
for r in R:
    for m in re.finditer(r'\[指揮\][^。；]{0,4}?周圍(\d+)格', r['nt']):
        cmdr[m.group(1)] += 1
table('7c_command_radius', '[指揮] 光環的半徑', [(f'{k} 格', v) for k, v in sorted(cmdr.items())], sum(cmdr.values()))
hp = collections.Counter()
for r in R:
    for m in re.finditer(r'生命(?:值)?[^，。；]{0,4}?(高於|低於|大於|小於|不低於|不高於|少於|多於)[^，。；\d]{0,2}(\d+)%', r['nt']):
        hp[f"{'高於' if m.group(1) in ('高於', '大於', '不低於', '多於') else '低於'} {m.group(2)}%"] += 1
    for m in re.finditer(r'生命(\d+)%以([上下])', r['nt']):
        hp[f"{'高於' if m.group(2) == '上' else '低於'} {m.group(1)}%"] += 1
table('7d_hp_threshold', '生命門檻的數值', [(k, v) for k, v in sorted(hp.items(), key=lambda x: (x[0][:2], int(re.search(r'\d+', x[0]).group())))], sum(hp.values()))
terr = collections.Counter()
for r in R:
    for w in set(re.findall(r'樹林|山地|水中|草地|沙漠|城牆|平地|水域|雪地|沼澤|防禦地形', r['nt'])):
        terr[w] += 1
table('7e_terrain_terms', '具體地形詞', [(k, v) for k, v in terr.most_common()], len(R), '一筆含兩種地形各算一次')
arm = collections.Counter()
for r in R:
    for w in set(re.findall(r'步兵|槍兵|騎兵|飛兵|水兵|弓兵|法師|僧侶|魔物|刺客', r['nt'])):
        arm[w] += 1
table('7f_army_terms', '兵種詞出現筆數', [(k, v) for k, v in arm.most_common()], len(R))
sp = sum(1 for r in R if re.search(r'有特效', r['nt']))
table('7g_special_effect', '「對 X 有特效」句（兵種特攻）', [('含「有特效」', sp)], len(R))

# =============== 8. 數值慣例 ===============
tiers = {'buff': collections.Counter(), 'debuff': collections.Counter()}
by_type = collections.defaultdict(collections.Counter)
for r in R:
    for typ, pol, val, p, _ in r['ev']:
        if p:
            tiers[pol][val] += 1
            by_type[typ][val] += 1
for pol in ['buff', 'debuff']:
    tot = sum(tiers[pol].values())
    top = tiers[pol].most_common(15)
    table(f'8a_{pol}_pct_tiers', f'{"強化" if pol == "buff" else "弱化"}百分比檔位（前 15 名）', [(f'{k}%', v) for k, v in top], tot,
          f'所有「屬性詞＋提升/降低＋N%」的 N；共 {tot} 個數字')
    stats[f'8a_{pol}_pct_tiers']['multiple_of_5_share'] = pct(sum(v for k, v in tiers[pol].items() if k % 5 == 0), tot)
rows = []
for typ, c in sorted(by_type.items(), key=lambda x: -sum(x[1].values())):
    vals = list(c.elements())
    rows.append((typ, len(vals), {'中位數': statistics.median(vals), '眾數': c.most_common(1)[0][0], '前三檔': '、'.join(f'{k}%×{v}' for k, v in c.most_common(3))}))
table('8b_pct_by_type', '各強化／弱化類型的百分比', rows, sum(len(list(c.elements())) for c in by_type.values()), cols=['中位數', '眾數', '前三檔'])

heal = collections.Counter(); heal_ex = collections.defaultdict(list)
for r in R:
    t = r['nt']
    for m in re.finditer(r'恢復[^，。；]{0,16}?(\d+)%(?:的)?(?:最大)?生命', t):
        if '傷害' in m.group(0):
            continue  # 「恢復造成傷害 X% 的生命」歸吸血
        k = '最大生命百分比' ; heal[k] += 1; heal_ex[k].append(m.group(1))
    for m in re.finditer(r'(智力|攻擊|防禦|魔防)[^，。；\d]{0,3}(\d+(?:\.\d+)?)倍(?:的)?生命', t):
        k = f'施放者{m.group(1)}×倍率'; heal[k] += 1; heal_ex[k].append(m.group(2))
    for m in re.finditer(r'傷害(?:數值)?[^，。；\d]{0,2}(\d+)%(?:的)?生命', t):
        k = '吸血（造成傷害×%）'; heal[k] += 1; heal_ex[k].append(m.group(1))
table('8c_heal_base', '回血的基準', [(k, v, {'常見數值': '、'.join(f'{a}×{b}' for a, b in collections.Counter(heal_ex[k]).most_common(4))}) for k, v in heal.most_common()],
      sum(heal.values()), '百分比＝最大生命 %；倍率＝施放者屬性 × N', cols=['常見數值'])
sh = collections.Counter(); sh_ex = collections.defaultdict(list)
for r in R:
    for c in re.split(r'[。；]', r['nt']):
        if '護盾' not in c:
            continue
        m = re.search(r'(\d+)%(?:的)?最大生命|最大生命(?:的)?(\d+)%', c)
        if m:
            sh['部隊最大生命 %'] += 1; sh_ex['部隊最大生命 %'].append(next(x for x in m.groups() if x)); continue
        m = re.search(r'(智力|攻擊|防禦|魔防)[^，。；\d]{0,4}(\d+(?:\.\d+)?)倍', c)
        if m:
            k = f'{m.group(1)}×倍率'; sh[k] += 1; sh_ex[k].append(m.group(2)); continue
        sh['未寫數值（免疫型或次數型護盾）'] += 1
table('8d_shield_base', '護盾的基準（含「護盾」的句子）', [(k, v, {'常見數值': '、'.join(f'{a}×{b}' for a, b in collections.Counter(sh_ex[k]).most_common(4))}) for k, v in sh.most_common()],
      sum(sh.values()), cols=['常見數值'])
collect_examples('8d:護盾', r'護盾', R, n=5)
fx = collections.Counter(); fx_ex = collections.defaultdict(list)
for r in R:
    for c in re.split(r'[。；]', r['nt']):
        if '固定傷害' not in c:
            continue
        m = re.search(r'(攻擊|智力|防禦|魔防)(?:力)?(?:的)?(\d+(?:\.\d+)?)倍', c)
        if m:
            k = f'{m.group(1)}×倍率'; fx[k] += 1; fx_ex[k].append(m.group(2)); continue
        m = re.search(r'(\d+)%', c)
        if m and '生命' in c:
            fx['生命 %'] += 1; continue
        fx['其他／未寫'] += 1
table('8e_fixed_damage_base', '[固定傷害] 的基準（含「固定傷害」的句子）', [(k, v, {'常見數值': '、'.join(f'{a}×{b}' for a, b in collections.Counter(fx_ex[k]).most_common(4))}) for k, v in fx.most_common()],
      sum(fx.values()), '[固定傷害]＝不過防禦的傷害（推論，依字面）', cols=['常見數值'])
chance = collections.Counter()
for r in R:
    for m in re.finditer(r'(\d+)%(?:的)?機率', r['nt']):
        chance[int(m.group(1))] += 1
table('8f_chance', '機率觸發的機率值', [(f'{k}%', v) for k, v in sorted(chance.items())], sum(chance.values()))

# =============== 9. 文字模板 ===============
ARMY = '步兵|槍兵|騎兵|飛兵|水兵|弓兵|法師|僧侶|魔物|刺客'
TEMPLATES = [
    ('T01 類型標籤開頭「[物理傷害]／[支援]／[被動]…」', r'^\[(物理傷害|魔法傷害|支援|治療|召喚|變身|主動|被動|超絕強化|指揮)\]'),
    ('T02 攻擊對象「攻擊單個敵軍／攻擊範圍內(多個|所有)敵軍」', r'攻擊(單個|範圍內[^，]{0,4}|\d條直線上的所有|直線上的所有)敵軍|對[^，。；]{0,12}(所有|單個)敵軍造成'),
    ('T03 倍率「造成 X 倍(範圍)傷害」', r'造成[^，。；]{0,8}\d+(\.\d+)?倍(的)?(範圍)?傷害'),
    ('T04 戰前「(進入)戰鬥前／戰前，…」', r'(進入)?戰鬥前|戰前'),
    ('T05 戰後「戰鬥後／戰後，…」', r'戰鬥後|戰後'),
    ('T06 主動攻擊「主動攻擊進入戰鬥時／後」', r'主動(攻擊)?進入戰鬥(時|前|後)|主動攻擊(時|後|前)'),
    ('T07 被攻擊「被(…)攻擊進入戰鬥時／後」', r'(?<!\[)被(?!動)[^，。；]{0,4}攻擊(進入戰鬥)?(時|前|後)'),
    ('T08 行動結束「行動結束時，…」', r'行動結束(時|後)'),
    ('T09 回合開始「(每)回合開始時，…」', r'回合開始'),
    ('T10 持續「，持續 N 回合」', r'持續\d+回合'),
    ('T11 再動「使用後可以額外行動 N 格，可再次攻擊」', r'(額外|再次|再)行動\d*格?[^。；]{0,6}可(以)?再次攻擊|再次移動\d格|(額外|再次)行動'),
    ('T12 回合不減註記「(使用此技能後，身上攜帶的強化效果回合數不會減少)」', r'回合數不會減少'),
    ('T13 指揮光環「[指揮]周圍 N 格以內的所有友軍部隊…」', r'\[指揮\][^。；]{0,4}周圍\d+格'),
    ('T14 範圍對象「(周圍)N 格範圍內的(所有|N 個)友軍／敵軍」', r'\d+(格|圈)(範圍)?(以)?內[^，。；]{0,6}(友軍|敵軍)|相鄰[^，。；]{0,6}(友軍|敵軍)|全場[^，。；]{0,6}(友軍|敵軍)'),
    ('T15 生命門檻「部隊生命高於／低於 X% 時，…」', r'生命(值)?[^，。；]{0,4}(高於|低於|大於|小於)[^，。；]{0,2}\d+%|生命\d+%以[上下]'),
    ('T16 機率「X% 的機率…」', r'\d+%(的)?機率'),
    ('T17 觸發冷卻「([觸發冷卻]該效果需要間隔 N 回合才可以再次觸發)」', r'觸發冷卻|需要間隔\d+回合'),
    ('T18 護衛「替相鄰友軍承受(物理|魔法|所有)攻擊」', r'替[^，。；]{0,6}承受[^，。；]{0,4}攻擊'),
    ('T19 驅散「驅散(敵軍|自身) N 個強化／弱化效果」', r'(?<![不法被能])驅散[^，。；]{0,10}(強化|弱化)'),
    ('T20 驅散屬性註記「不可驅散／無法免疫」', r'(不可|無法)(被)?(驅散|免疫)'),
    ('T21 屬性增減「(屬性)提升／降低 N%」', r'(攻擊|智力|防禦|魔防|技巧|暴擊率|暴擊傷害|傷害|移動力|射程|全屬性|生命|治療效果)[^，。；\d]{0,3}(提升|降低|增加|減少|\+|-)\s*\d+'),
    ('T22 回血「恢復(…)N% 生命／智力 N 倍的生命」', r'恢復[^，。；]{0,16}生命'),
    ('T23 上限註記「(最多／最高提升 N%)」', r'(最多|最高|最大)[^，。；]{0,6}\d+'),
    ('T24 次數限制「每場戰鬥最多觸發 N 次／最大使用次數」', r'每場戰鬥(最多|僅|只)|最大使用次數|每回合(最多|只|僅)|最多觸發|只能觸發'),
    ('T25 技能替換「使用後將此技能替換為[XX]」', r'替換為'),
    ('T26 兵種特攻「對「X」有特效」', r'有特效'),
    ('T27 免疫「免疫(XX)」', r'(?<!無法)(?<!法被)(?<!不可)(?<!驅散和)(?<!驅散與)免疫'),
    ('T28 線性加成「每(移動 N 格／有 1 個 X)，…提升 N%」', r'每(移動|有|擁有|間隔|損失|累積|穿過|消耗|死亡|命中|造成)[^。；]{0,16}?(提升|增加|降低|減少|\+)'),
    ('T29 施加具名效果「獲得／施加[XX]：…」', r'(獲得|施加|進入)[^，。；]{0,8}\[[^\]]+\]'),
    ('T30 傷害方式改寫「造成[固定傷害]／視為魔法傷害」', r'固定傷害|視為(物理|魔法)傷害'),
]
TPL_C = [(n, re.compile(p)) for n, p in TEMPLATES]
def tpl_hits(t):
    return [n for n, c in TPL_C if c.search(t)]
matrix('9a_templates', '文字模板：含該句型的技能筆數', [(n, (lambda c: lambda r: bool(c.search(r['nt'])))(c)) for n, c in TPL_C], GROUPS)
# 句級覆蓋率
sent_tot = collections.Counter(); sent_cov = collections.Counter(); unc_samples = []
rec_cov = collections.Counter()
for g in GROUP_ORDER:
    for r in GROUPS[g]:
        sents = [s for s in re.split(r'[。；]', r['nt']) if len(s.strip()) >= 4]
        ok_all = True
        for s in sents:
            sent_tot[g] += 1
            if tpl_hits(s):
                sent_cov[g] += 1
            else:
                ok_all = False
                if len(unc_samples) < 400:
                    unc_samples.append((g, r['name'], s))
        if sents and ok_all:
            rec_cov[g] += 1
table('9b_template_coverage', '模板覆蓋率', [(g, sent_cov[g], {'句子數': sent_tot[g], '句覆蓋率': pct(sent_cov[g], sent_tot[g]),
                                               '整筆每句都命中': rec_cov[g], '整筆覆蓋率': pct(rec_cov[g], len(GROUPS[g])),
                                               '至少命中一個模板': sum(1 for r in GROUPS[g] if tpl_hits(r['nt'])), '至少一個占比': pct(sum(1 for r in GROUPS[g] if tpl_hits(r['nt'])), len(GROUPS[g]))})
                                       for g in GROUP_ORDER], sum(sent_tot.values()),
      '句子＝以。；切開、長度≥4；「筆數」欄＝命中至少一個模板的句子數', cols=['句子數', '句覆蓋率', '整筆每句都命中', '整筆覆蓋率', '至少命中一個模板', '至少一個占比'])
tot_s = sum(sent_tot.values()); tot_c = sum(sent_cov.values())
stats['9b_template_coverage']['overall_sentence_coverage'] = pct(tot_c, tot_s)
random.Random(7).shuffle(unc_samples)
stats['9c_uncovered_samples'] = [{'group': g, 'name': n, 'sentence': s[:120]} for g, n, s in unc_samples[:15]]
# 傷害技能的骨架句
dmg = [r for r in ACT if r['category'] in ('物理傷害', '魔法傷害')]
skel = sum(1 for r in dmg if re.search(TEMPLATES[1][1], r['nt']) and re.search(TEMPLATES[2][1], r['nt']))
stats['9d_damage_skeleton'] = {'title': '傷害技能同時有 T02 攻擊對象＋T03 倍率句', 'count': skel, 'denominator': len(dmg), 'pct': pct(skel, len(dmg))}
md.append(f'\n### 9d_damage_skeleton\n傷害技能同時有 T02＋T03：{skel}/{len(dmg)}＝{pct(skel, len(dmg))}%')
for n, p in TEMPLATES:
    collect_examples('9a:' + n, p, ACT + PAS + GROUPS['天賦'], n=2)

# =============== 抽查樣本 ===============
SEED = int(os.environ.get('MZ_SEED', '20261016'))
rng = random.Random(SEED)
def sample_pairs(attr, n=20):
    pairs = [(r['id'], t) for r in R for t in sorted(r[attr])]
    rng.shuffle(pairs)
    return pairs[:n]
def evidence(r, typ, attr):
    # 找觸發這個類型的片段
    for e in r['ev']:
        if e[0] == typ:
            i = r['nt'].find(e[4]); return r['nt'][max(0, i - 40): i + len(e[4]) + 25]
    for n, p in (BUFF_KW if attr == 'bt' else DEBUFF_KW):
        if n == typ:
            m = re.search(p, r['nt']); return r['nt'][max(0, m.start() - 40): m.end() + 25]
    return ''
samples = {}
byid = {r['id']: r for r in R}
for attr, key in [('bt', 'buff'), ('dt', 'debuff')]:
    samples[key] = [{'id': i, 'kind': KIND_ZH[byid[i]['kind']], 'name': byid[i]['name'], 'label': t, 'evidence': evidence(byid[i], t, attr)} for i, t in sample_pairs(attr)]
tpairs = [(r['id'], n, p) for r in R for n, p in TIMING if re.search(p, r['nt'])]
rng.shuffle(tpairs)
samples['timing'] = []
for i, n, p in tpairs[:20]:
    m = re.search(p, byid[i]['nt'])
    samples['timing'].append({'id': i, 'kind': KIND_ZH[byid[i]['kind']], 'name': byid[i]['name'], 'label': n, 'evidence': byid[i]['nt'][max(0, m.start() - 35): m.end() + 30]})
json.dump(samples, open(os.path.join(outdir, 'samples_to_review.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

for rp in sys.argv[3:]:
    if not os.path.exists(rp):
        print('找不到判讀檔', rp); continue
    J = json.load(open(rp, encoding='utf-8'))
    res = {'_note': J.get('_note', ''), '_file': os.path.basename(rp)}
    for key, lst in J.items():
        if key.startswith('_'):
            continue
        wrong = [x for x in lst if not x['correct']]
        res[key] = {'sampled': len(lst), 'wrong': len(wrong), 'error_rate_pct': pct(len(wrong), len(lst)),
                    'wrong_items': [{'name': x['name'], 'label': x['label'], 'why': x.get('why', '')} for x in wrong]}
    tag = os.path.splitext(os.path.basename(rp))[0]
    stats['appendix_misclassification_' + tag] = res
    md.append(f'\n### appendix_misclassification_{tag}')
    for k, v in res.items():
        if not k.startswith('_'):
            md.append(f"- {k}：抽 {v['sampled']}、錯 {v['wrong']}、誤判率 {v['error_rate_pct']}%")

# 關鍵字清單（附錄 A）
stats['appendix_keywords'] = {
    'active_tags': {n: '(程式判定)' for n, _ in ACT_TAGS},
    'timing': dict(TIMING), 'buff_keywords': dict(BUFF_KW), 'debuff_keywords': dict(DEBUFF_KW),
    'stat_parser': stat_re.pattern, 'stack': dict(STACK), 'dispel_immune': dict(DISPEL), 'conditions': dict(COND), 'templates': dict(TEMPLATES)}

json.dump(stats, open(os.path.join(outdir, 'stats.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
json.dump(examples, open(os.path.join(outdir, 'examples.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
open(os.path.join(outdir, 'tables.md'), 'w', encoding='utf-8').write('\n'.join(md))
print('ok', len(stats), 'tables;', 'examples', len(examples))
