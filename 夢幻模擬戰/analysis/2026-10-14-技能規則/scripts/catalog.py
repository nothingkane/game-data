# 強化／弱化目錄：每種效果（屬性拆開）列出所有檔次，每檔附次數與兩個例子
# 用法：python catalog.py <effects.json> <vr_exclusions.json> <輸出 html 片段>
import json, sys, collections, html

EFF, EXC, OUT = sys.argv[1:4]
R = json.load(open(EFF, encoding="utf-8"))["records"]
EX = json.load(open(EXC, encoding="utf-8"))["items"]
EXKEY = {(e["name"], e["cat"].split("（")[0], float(e["val"])) for e in EX if e.get("table") == "range"}

KIND = {"天賦": "天賦", "專屬裝備": "專武", "士兵": "士兵", "鑄紋技能": "鑄紋"}
PRIO = {"主動": 0, "天賦": 1, "被動": 2, "專武": 3, "鑄紋": 4, "士兵": 5}
STAT_ORDER = ["攻擊", "智力", "防禦", "魔防", "技巧", "生命", "全屬性"]

def layer(r, x):
    if r["kind"] == "技能":
        return "被動" if x.get("segment") == "被動" or r.get("category") == "被動" else "主動"
    return KIND.get(r["kind"], r["kind"])

def split_stats(s):
    out = []
    for p in (s or "").split("、"):
        if p == "攻防": out += ["攻擊", "防禦"]
        elif p: out.append(p)
    return out

def base_label(b, unit):
    if unit == "%":
        if b in ("目標生命", "目標最大生命"): return "最大生命 %"
        if b == "目標剩餘生命": return "剩餘生命 %"
        if b == "造成傷害": return "本次傷害 %"
        return "%"
    if unit == "倍" and b:
        return b.replace("施加者", "施放者") + " ×"
    return unit or ""

# rows[(極性, 效果名)] -> tiers[(value, flag, unitlabel)] -> list of (layer, name)
rows = collections.OrderedDict()
def add(pol, label, value, flag, unit, lay, name):
    rows.setdefault((pol, label), collections.defaultdict(list))[(value, flag, unit)].append((lay, name))

SIMPLE = {  # 效果種類 -> 顯示名
    "buff": {"增傷": "增傷（造成傷害提升）", "減傷": "減傷（遭受傷害降低）", "冷卻縮短": "冷卻縮短",
             "反彈傷害": "反彈傷害", "防暴擊": "受暴擊率降低", "治療效果提升": "治療效果提升（施放方）",
             "受治療提升": "受治療提升（受治療方）", "吸血": "吸血", "回血": "回血", "護盾": "護盾"},
    "debuff": {"易傷": "易傷（遭受傷害提升）", "降傷": "降傷（造成傷害降低）", "受暴擊提升": "受暴擊率提升",
               "受治療降低": "受治療降低", "治療效果降低": "治療效果降低", "冷卻增加": "冷卻增加",
               "持續傷害": "持續傷害", "固定傷害": "一次性固定傷害"},
}
NONNUM = collections.Counter()
skipped = collections.Counter()
for r in R:
    for x in r["effects"]:
        pol, t, v, unit = x.get("polarity"), x.get("type"), x.get("value"), x.get("unit")
        if pol not in ("buff", "debuff"):
            skipped["neutral"] += 1; continue
        if (r["name"], t, float(v) if isinstance(v, (int, float)) else None) in EXKEY:
            skipped["人工排除"] += 1; continue
        lay = layer(r, x)
        flag = "每" if x.get("per") else ("層" if x.get("stack_max") else "")
        if not isinstance(v, (int, float)):
            NONNUM[(pol, t)] += 1; continue
        if t in ("屬性提升", "屬性降低"):
            if "射程" in (x.get("raw") or ""):  # 「攻擊射程+1」被解析成攻擊 1%
                skipped["射程誤當屬性"] += 1; continue
            for s in split_stats(x.get("stat")):
                if s not in STAT_ORDER: skipped["屬性名不認得:" + s] += 1; continue
                add(pol, ("屬性提升・" if pol == "buff" else "屬性降低・") + s, v, flag, "%", lay, r["name"])
        elif t == "暴擊提升":
            for s in split_stats(x.get("stat")) or ["暴擊率"]:
                if s in ("暴擊率", "暴擊傷害"):
                    add(pol, s + "提升", v, flag, "%", lay, r["name"])
        elif t in ("移動力／射程提升", "移動力／射程降低"):
            s = x.get("stat") or "移動力"
            add(pol, s + ("提升" if pol == "buff" else "降低"), v, flag, "格", lay, r["name"])
        elif t in SIMPLE.get(pol, {}):
            unit_l = "回合" if t in ("冷卻縮短", "冷卻增加") else base_label(x.get("base"), unit)
            add(pol, SIMPLE[pol][t], v, flag, unit_l, lay, r["name"])
        else:
            NONNUM[(pol, t)] += 1

def fmt(v):
    return str(int(v)) if float(v).is_integer() else str(v)

def unit_str(u, v):
    if u == "%" : return fmt(v) + "%"
    if u.endswith("%"): return fmt(v) + "%"
    if u.endswith("×"): return fmt(v) + " 倍"
    return fmt(v) + " " + u

ORDER_BUFF = [f"屬性提升・{s}" for s in STAT_ORDER] + ["暴擊率提升", "暴擊傷害提升", "增傷（造成傷害提升）", "減傷（遭受傷害降低）",
              "受暴擊率降低", "回血", "吸血", "護盾", "反彈傷害", "治療效果提升（施放方）", "受治療提升（受治療方）", "移動力提升", "射程提升", "冷卻縮短"]
ORDER_DEBUFF = [f"屬性降低・{s}" for s in STAT_ORDER] + ["易傷（遭受傷害提升）", "降傷（造成傷害降低）", "受暴擊率提升", "受治療降低", "治療效果降低",
              "移動力降低", "射程降低", "冷卻增加", "持續傷害", "一次性固定傷害"]

def render(pol, order):
    out = []
    keys = [k for k in order if (pol, k) in rows] + [k for (p, k) in rows if p == pol and k not in order]
    for k in keys:
        tiers = rows[(pol, k)]
        # 依單位分組（回血、持續傷害會有好幾種基準）
        byu = collections.defaultdict(list)
        for (v, flag, u), ex in tiers.items(): byu[u].append((v, flag, ex))
        first = True
        for u in sorted(byu, key=lambda u: (u not in ("%", "格", "回合"), u)):
            if u == "點":
                skipped["單位是點（疑似解析錯）"] += sum(len(e) for _, _, e in byu[u]); continue
            normal = sorted([t for t in byu[u] if not t[1]], key=lambda t: t[0])
            small = sorted({t[0] for t in byu[u] if t[1]})
            items = normal
            chips = []
            for v, flag, ex in items:
                names, seen = [], set()
                for lay, n in sorted(ex, key=lambda e: PRIO.get(e[0], 9)):
                    if n in seen: continue
                    seen.add(n); names.append(f"{html.escape(n)}<i>{lay}</i>")
                    if len(names) == 2: break
                chips.append(f'<li><b>{unit_str(u, v)}</b><span class="cnt">×{len(ex)}</span><span class="ex">{"、".join(names)}</span></li>')
            base = "" if u in ("%", "格", "回合") else f'<span class="base">以{html.escape(u.replace(" ×","").replace(" %",""))}計</span>'
            name = html.escape(k) if first else ""
            sm = "、".join(unit_str(u, v) for v in small) if small else "—"
            out.append(f'<tr><th scope="row">{name}{base}</th><td><ul class="tiers">{"".join(chips) or "<li>—</li>"}</ul></td><td class="small">{sm}</td></tr>')
            first = False
    return "\n".join(out)

nonnum = lambda pol: "、".join(f"{t} {n}" for (p, t), n in NONNUM.most_common() if p == pol and n >= 3)
frag = {
    "buff": render("buff", ORDER_BUFF), "debuff": render("debuff", ORDER_DEBUFF),
    "buff_nonnum": nonnum("buff"), "debuff_nonnum": nonnum("debuff"),
    "skipped": dict(skipped),
    "rows": {f"{p}:{k}": len(v) for (p, k), v in rows.items()},
}
json.dump(frag, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps({"skipped": frag["skipped"], "rows": frag["rows"]}, ensure_ascii=False, indent=0))
print("buff 無數值:", frag["buff_nonnum"]); print("debuff 無數值:", frag["debuff_nonnum"])
