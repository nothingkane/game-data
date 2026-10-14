# -*- coding: utf-8 -*-
"""
夢幻模擬戰：拿 parse_effects.py 的解析結果跟人工對照組逐欄比對（離線，只用標準函式庫）

用法: python 夢幻模擬戰/tools/test_parse_effects.py [-v]
前置條件: merged/ 已由 build_merged.py 產生；對照組在 tools/effects_golden.json。
預期結果: 印出每一欄的命中率；全部一致 exit 0，有任何一欄不一致、少了或多了效果就 exit 1，-v 印出每一處不一致。

比法（細節寫在 effects_golden.json 的 _meta）:
- 解析器是現跑的（呼叫 parse_effects.build_records()），不讀 merged/effects.json，避免比到舊檔。
- damage、effects 是這段文字該有的全部：先照（類型、數值、屬性）配對，配不到的算少了，實際多出來的算多了。
- 每一筆效果的每一欄都比；對照組沒寫的欄位視為 null（timing 視為 []、permanent 視為 false）。
- 另外驗：每一筆效果的 raw 與 raw_of 都是原文的子字串（每個欄位追得回原文）。
"""
import collections
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.dont_write_bytecode = True          # 不要在 tools/ 留 __pycache__
import parse_effects  # noqa: E402

GOLDEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "effects_golden.json")
EFFECT_FIELDS = ["type", "polarity", "stat", "value", "unit", "base", "duration", "permanent", "stack_max", "cap", "per",
                 "dispellable", "immunable", "timing", "target", "condition", "chance"]
DAMAGE_FIELDS = ["multiplier", "dtype", "scope"]
SHELL_FIELDS = ["cooldown", "cooldown_from", "area", "category"]
DEFAULT = {"timing": [], "permanent": False}


def same(field, want, got):
    if field == "timing":
        return sorted(want or []) == sorted(got or [])
    if field == "condition":
        if want is None:
            return got is None
        return got is not None and all(any(w in g for g in got) for w in want)
    if isinstance(want, (int, float)) and isinstance(got, (int, float)) and not isinstance(want, bool):
        return abs(want - got) < 1e-9
    return want == got


def pair(wants, gots, keys):
    """照 keys 配對；回傳 [(want, got 或 None)]、多出來的 got。"""
    left = list(gots)
    out = []
    for w in wants:
        hit = None
        for strict in (True, False):
            for g in left:
                ks = keys if strict else keys[:1]
                if all(same(k, w.get(k, DEFAULT.get(k)), g.get(k)) for k in ks):
                    hit = g
                    break
            if hit:
                break
        if hit:
            left.remove(hit)
        out.append((w, hit))
    return out, left


def main():
    verbose = "-v" in sys.argv
    golden = json.load(open(GOLDEN, encoding="utf-8"))["items"]
    records = {r["id"]: r for r in parse_effects.build_records()}
    hits, total = collections.Counter(), collections.Counter()
    problems = []

    def check(field, want, got, where):
        total[field] += 1
        if same(field, want, got):
            hits[field] += 1
        else:
            problems.append(f"{where} {field}：期望 {want!r}，實際 {got!r}")

    kinds = collections.Counter(item["id"].split(":")[0] for item in golden)
    for item in golden:
        rid, exp = item["id"], item["expect"]
        rec = records.get(rid)
        if rec is None:
            problems.append(f"{rid}：解析結果裡沒有這一筆")
            total["(找得到這一筆)"] += 1
            continue
        for f in SHELL_FIELDS:
            if f in exp:
                check(f, exp[f], rec.get(f), rid)
        if "gear_stat" in exp:
            gs = rec.get("gear_stat") or {}
            check("gear_stat", exp["gear_stat"], {"stat": gs.get("stat"), "value": gs.get("value")}, rid)
        if item.get("effects_checked") is False:
            continue
        # 傷害倍率
        pairs, extra = pair(exp["damage"], rec["damage"], DAMAGE_FIELDS)
        for w, g in pairs:
            for f in DAMAGE_FIELDS:
                check("damage." + f, w[f], g.get(f) if g else "（少了這筆）", f"{rid} damage {w['multiplier']}")
        total["damage（沒有多出來的）"] += 1
        if extra:
            problems.append(f"{rid} 多出來的傷害：{[d['raw'] for d in extra]}")
        else:
            hits["damage（沒有多出來的）"] += 1
        # 效果
        pairs, extra = pair(exp["effects"], rec["effects"], ["type", "value", "stat"])
        for w, g in pairs:
            for f in EFFECT_FIELDS:
                want = w.get(f, DEFAULT.get(f))
                got = g.get(f) if g else "（少了這筆）"
                check(f, want, got, f"{rid} {w['type']}{'' if w.get('value') is None else w['value']}")
        total["effects（沒有多出來的）"] += 1
        if extra:
            problems.append(f"{rid} 多出來的效果：{[(e['type'], e['value'], e['raw']) for e in extra]}")
        else:
            hits["effects（沒有多出來的）"] += 1
        check("unparsed_count", exp["unparsed_count"], len(rec["unparsed"]), rid)
        # 每個欄位追得回原文
        for e in rec["effects"]:
            texts = [e["raw"]] + [x for v in e["raw_of"].values() for x in (v if isinstance(v, list) else [v])]
            total["raw 是原文子字串"] += 1
            bad = [x for x in texts if x not in rec["text"]]
            if bad:
                problems.append(f"{rid} raw 不在原文裡：{bad}")
            else:
                hits["raw 是原文子字串"] += 1

    print(f"對照組 {len(golden)} 筆（{'、'.join(f'{k} {v}' for k, v in kinds.items())}），"
          f"手寫時拿不準的 {sum(1 for i in golden if i.get('unsure'))} 筆")
    print("逐欄命中率：")
    for f in list(total):
        print(f"  {f:<24} {hits[f]:>4}/{total[f]:<4} {100.0 * hits[f] / total[f]:5.1f}%")
    all_hits, all_total = sum(hits.values()), sum(total.values())
    print(f"合計 {all_hits}/{all_total}（{100.0 * all_hits / all_total:.1f}%），不一致 {len(problems)} 處")
    if problems:
        for p in problems if verbose else problems[:20]:
            print("  ✗ " + p)
        if not verbose and len(problems) > 20:
            print(f"  …還有 {len(problems) - 20} 處，加 -v 看全部")
        sys.exit(1)


if __name__ == "__main__":
    main()
