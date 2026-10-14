# -*- coding: utf-8 -*-
"""
夢幻模擬戰：把技能文字拆成結構化的效果欄位（離線，只用標準函式庫）

用法: python 夢幻模擬戰/tools/parse_effects.py
      （build_merged.py 跑完會自動呼叫；只改了這支的規則時可以單獨跑）
前置條件: merged/ 已由 build_merged.py 產生；sources/ingame/rune_skills.json 與 sources/wiki/data/soldiers.json 在。
預期結果: merged/effects.json，一段技能文字一筆，五種來源（技能、天賦、鑄紋技能、專屬裝備、士兵）；
          印出各來源筆數、有沒解析到的句子的筆數、句子覆蓋率、各效果類型的筆數，同一份數字寫進 _meta.coverage。

規則摘要（欄位定義、為什麼這樣切、已知限制見 docs/ADR-002-effect-fields.md）:
- 傷害倍率的單體／範圍一律看技能的 area 欄（wiki 版看 span）；沒有 area 的來源（天賦、鑄紋、裝備、士兵、
  技能文字裡 [被動] 那一段）才看文字，標 scope_from: text。
- 「最多提升 N%」是封頂，放 cap，不當成單次數值；「可累積，最多 N 層」放 stack_max。
- dispellable／immunable 只在文字寫了「不可驅散」「無法免疫」才填 false，沒寫是 null，不猜預設。
- 「被」只算「被…攻擊」，不算 [被動] 標籤；「無法免疫」「驅散和免疫」不是免疫效果。
- 沒有任何規則解析到的句子原樣放 unparsed，不硬塞。
- 關鍵字與時機分類沿用 2026-10-14 研究喵的技能規則統計（三輪人工抽查修過的版本），分類名去掉括號裡的說明。
"""
import collections
import glob
import json
import os
import re

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
MERGED = os.path.join(BASE, "merged")
INGAME = os.path.join(BASE, "sources", "ingame")
WIKI = os.path.join(BASE, "sources", "wiki", "data")
GENERATED = {"note": "parse_effects.py 產生，不要手改"}
KINDS = ["技能", "天賦", "鑄紋技能", "專屬裝備", "士兵"]
PASSIVE_KINDS = {"天賦", "鑄紋技能", "專屬裝備", "士兵"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(name, data):
    with open(os.path.join(MERGED, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


# ───────────────────────── 1. 收集五種來源 ─────────────────────────

def parse_cd(value):
    """遊戲畫面的 cooldown 是整數（0＝寫「無」）；wiki 的 cd 是「3回合」「无」或 None。"""
    if value is None or isinstance(value, int):
        return value
    m = re.match(r"(\d+)", str(value))
    if m:
        return int(m.group(1))
    return 0 if str(value) in ("无", "無") else None


SHELL = ["category", "cost", "cooldown", "range", "area"]
WIKI_SHELL = {"category": "type", "cooldown": "cd", "range": "range", "area": "span"}


def skill_records():
    out = []
    for row in load(os.path.join(MERGED, "skills.json"))["skills"]:
        wiki = row.get("wiki") or {}
        heroes = row.get("heroes") or row.get("heroes_wiki") or []
        if "text" in row:
            variants = row.get("variants") or [row]
            for i, facts in enumerate(variants):
                rec = {"id": f"技能:{row['name']}" + (f"#{i + 1}" if i else ""), "kind": "技能", "name": row["name"],
                       "heroes": heroes, "text": facts["text"], "text_from": "ingame"}
                for key in SHELL:
                    rec[key] = facts.get(key)
                if rec["cooldown"] is None and wiki.get("cd"):
                    rec["cooldown"], rec["cooldown_from"] = parse_cd(wiki["cd"]), "wiki"
                if len(variants) > 1:
                    rec["variant"] = f"{i + 1}/{len(variants)}（同名技能在不同英雄身上寫的不一樣）"
                out.append(rec)
        elif wiki.get("description"):
            rec = {"id": f"技能:{row['name']}", "kind": "技能", "name": row["name"], "heroes": heroes,
                   "text": wiki["description"], "text_from": "wiki", "cost": None}
            for key, wkey in WIKI_SHELL.items():
                value = parse_cd(wiki.get(wkey)) if key == "cooldown" else wiki.get(wkey)
                rec[key] = value
                if value is not None:
                    rec[key + "_from"] = "wiki"
            out.append({k: rec[k] for k in ["id", "kind", "name", "heroes", "text", "text_from"] + SHELL}
                       | {k: v for k, v in rec.items() if k.endswith("_from") and k != "text_from"})
    return out


def hero_files():
    return [load(p) for p in sorted(glob.glob(os.path.join(MERGED, "heroes", "*.json")))]


def talent_records(heroes):
    return [{"id": f"天賦:{h['talent']['name']}", "kind": "天賦", "name": h["talent"]["name"], "heroes": [h["name"]],
             "text": h["talent"]["text"], "text_from": "ingame"}
            for h in heroes if (h.get("talent") or {}).get("text")]


def rune_records(heroes):
    """合併英雄檔的 rune_skill 加 rune_skills.json，照（英雄, 技能名）去重；遊戲畫面讀到的內文優先。"""
    found = {}

    def put(hero, name, text, text_from):
        key = (hero, name)
        if not text or (key in found and found[key]["text_from"] == "ingame"):
            return
        found[key] = {"id": f"鑄紋技能:{name}", "kind": "鑄紋技能", "name": name, "heroes": [hero],
                      "text": text, "text_from": text_from}

    for h in heroes:
        rune = h.get("rune_skill") or {}
        if rune.get("text"):
            put(h["name"], rune["name"], rune["text"], "ingame")
        elif rune.get("text_wiki"):
            put(h["name"], rune["name"], rune["text_wiki"], "wiki")
        elif rune.get("description") and rune.get("name") != "暫無":
            put(h["name"], rune["name"], rune["description"], "wiki")
    rune_file = load(os.path.join(INGAME, "rune_skills.json"))
    for r in rune_file["unlocked"]:
        put(r["hero"], r["name"], r["text"], "ingame")
    for hero, text in rune_file["obtainable_text_wiki"].items():
        put(hero, rune_file["obtainable"][hero], text, "wiki")
    return sorted(found.values(), key=lambda r: r["id"])


def gear_records():
    return [{"id": f"專屬裝備:{g['name']}", "kind": "專屬裝備", "name": g["name"], "skill_name": g["skill"]["name"],
             "heroes": [g["owner"]], "text": g["skill"]["text"], "text_from": "ingame"}
            for g in load(os.path.join(MERGED, "exclusive_gear.json"))["items"] if g["skill"].get("text")]


def soldier_records():
    return [{"id": f"士兵:{s['name']}", "kind": "士兵", "name": s["name"], "soldier_type": s.get("type"),
             "heroes": s.get("heroes", []), "text": s["skillDescription"], "text_from": "wiki"}
            for s in load(os.path.join(WIKI, "soldiers.json")) if s.get("skillDescription")]


# ───────────────────────── 2. 文字前處理 ─────────────────────────
# 換成半形、引號統一成 "，長度不變，所以位置可以直接回原文取片段（raw 一律是原文的子字串）。
NORM = str.maketrans({"（": "(", "）": ")", "：": ":", "“": '"', "”": '"', "「": '"', "」": '"', "『": '"', "』": '"',
                      "‘": "'", "’": "'", "＋": "+", "－": "-", ",": "，", ";": "；", "　": " "})
CN_NUM = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5}


def norm(text):
    return text.translate(NORM).replace("遠端", "遠程")


def num(s):
    if s in CN_NUM:
        return CN_NUM[s]
    v = float(s)
    return int(v) if v.is_integer() else v


# 一段文字裡用 [被動]／[物理傷害]… 標籤分段；[被動]、[指揮] 開頭的段是被動段，其餘是主動段
SEG_TAG = re.compile(r"\[(被動|指揮|主動|物理傷害|魔法傷害|支援|治療|變身|召喚|超絕強化)\]")
# 專屬裝備第一句「生命+2%」是裝備本身隨強化等級走的能力加成，不是技能效果，另外放 gear_stat
GEAR_STAT = re.compile(r"^((?:生命|攻擊|智力|防禦|魔防|技巧|治療效果)(?:[、，](?:生命|攻擊|智力|防禦|魔防|技巧))*)"
                       r"\+(\d+(?:\.\d+)?)%[。；，]?")
# 獨立成句、但其實是在註記前一句的：「該效果無法被驅散。」
NOTE_START = re.compile(r"^\s*(該效果|此效果|以上效果|上述效果|無法被驅散|不可驅散|無法免疫|不可免疫|持續\d+回合[。；]?\s*(\(|$))")


def segments(t, default):
    cuts = [m for m in SEG_TAG.finditer(t) if m.start() == 0 or t[m.start() - 1] in '。；)" ']
    if not cuts:
        return [(0, len(t), default)]
    out = []
    if cuts[0].start() > 0:
        out.append((0, cuts[0].start(), default))
    for i, m in enumerate(cuts):
        end = cuts[i + 1].start() if i + 1 < len(cuts) else len(t)
        out.append((m.start(), end, "被動" if m.group(1) in ("被動", "指揮") else "主動"))
    return out


def split_sentences(t, s, e, quote_aware):
    """以。；切句；quote_aware 時引號與括號裡的。；不切（一個狀態的定義不被切開）。
    以「(」開頭的、或「該效果無法被驅散」這類註記句併進前一句。"""
    spans, start, quote, paren = [], s, False, 0
    for i in range(s, e):
        ch = t[i]
        if quote_aware and ch == '"':
            quote = not quote
        elif quote_aware and ch == "(":
            paren += 1
        elif quote_aware and ch == ")":
            paren = max(0, paren - 1)
        elif ch in "。；" and not quote and paren == 0:
            spans.append((start, i + 1))
            start = i + 1
    if start < e:
        spans.append((start, e))
    out = []
    for a, b in spans:
        piece = t[a:b]
        if out and (piece.lstrip().startswith("(") or NOTE_START.match(piece)):
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def quote_mask(t):
    inside, q = [False] * len(t), False
    for i, ch in enumerate(t):
        if ch == '"':
            q = not q
        inside[i] = q
    return inside


# ───────────────────────── 3. 規則 ─────────────────────────
DMG = re.compile(r"造成(?P<pre>[^，。；傷]{0,8}?)(?P<v>\d+(?:\.\d+)?)倍(?:的)?(?P<area>範圍)?(?P<dt>物理|魔法)?(?P<area2>範圍)?(?:戰鬥|攻擊|技能)?傷害")

STAT = r"(?:攻擊|智力|防禦|魔防|技巧|全屬性|攻防(?:能力)?|生命|暴擊率|暴擊傷害|傷害|移動力|射程|治療效果|冷卻時間)"
ATTR = r"(?:攻擊|智力|防禦|魔防|技巧)"
STAT_LIST = STAT + r"(?:[，、和與及]" + STAT + r"|(?<=攻擊|智力|防禦|魔防|技巧)" + ATTR + r")*"
STAT_RE = re.compile(r"(?P<pre>[^，。；:]{0,10}?)(?P<stats>" + STAT_LIST + r")"
                     r"(?P<gap>[^，。；\d%]{0,3}?)(?P<dir>提升|增加|提高|降低|減少|下降|\+|-)\s*(?P<v>\d+(?:\.\d+)?)(?P<pct>%?)")
# 倒裝：「降低敵軍10%的攻擊、防禦」「提升自身20%攻擊和魔防」
STAT_RE2 = re.compile(r"(?P<dir>提升|增加|提高|降低|減少)(?P<who>[^，。；\d]{0,6}?)(?P<v>\d+(?:\.\d+)?)%的?(?P<stats>" + STAT_LIST + r")")
STAT_ONE = re.compile(STAT)
CAPW = re.compile(r"最多|最高|最大(?!生命|持續)|上限|不超過|至多")
CAP_RE = re.compile(r"(?P<w>最大不超過|最高不超過|最多不超過|不超過|最多|最高|最大(?!生命|持續)|上限|至多)"
                    r"(?:可以?)?(?P<acc>累積|疊加)?(?:施加|偷取|驅散)?(?:為|至|到)?(?:提升|增加|降低|減少|提高|\+|-)?(?:至|到|為)?"
                    r"(?P<who>[^，。；\d]{0,8}?)\s*(?P<v>\d+(?:\.\d+)?)\s*(?P<u>%|格|回合|層|個|次|倍|點)?")
STACK_NEAR = re.compile(r"(累積|疊加)[^。；]{0,3}$")
DUR_RE = re.compile(r"持續(?P<n>\d+)回合|持續至[^，。；\"]{1,12}")           # 效果後面的
DUR_BEFORE = re.compile(r"(?P<n>\d+)回合(?:的|內)")                          # 效果前面的：「獲得2回合的[地陷]」
CHANCE_RE = re.compile(r"(\d+)%(?:的)?機率")
PER_RE = re.compile(r"每(?!場|回合|個部隊|次)[^，。；]{1,16}")

TIMING = [  # 研究喵 3a_timing 的最終版（第三輪修過）；生命門檻、機率、觸發冷卻、次數限制不算時機，分到 condition／chance
    ("戰鬥前", r"戰鬥前|戰前"),
    ("戰鬥中", r"進入戰鬥時|(?<!場)戰鬥中|(?<!場)戰鬥時(?!間)|交戰(?:時|中)"),
    ("戰鬥後", r"戰鬥後|戰後|戰鬥結束後"),
    ("主動攻擊方", r"主動(?:攻擊|進入戰鬥)"),
    ("被攻擊方", r"(?<!\[)被(?!動)[^，。；]{0,4}攻擊"),
    ("行動結束時", r"行動結束"),
    ("回合開始時", r"回合開始"),
    ("回合結束時", r"回合結束"),
    ("戰場開場", r"戰鬥開始"),
    ("使用技能時或後", r"(?:使用|釋放|施放)[^，。；]{0,8}技能(?:時|後)|使用後|釋放後"),
    ("攻擊前", r"攻擊前|命中[^，。；]{0,6}前"),
    ("受到傷害後", r"(?:受到|遭受)(?![^，。；]{0,4}致命)[^，。；]{0,8}傷害(?:後|時)"),
    ("擊殺敵軍時", r"(?<!未造成)(?<!未)(?:擊殺|擊敗)"),
    ("死亡時", r"死亡(?:時|後)"),
    ("遭受致命傷害時", r"致命傷害|一擊致命"),
    ("移動距離", r"每移動|移動(?:了|過)?(?:超過|至少|不少於|大於)?\d+格(?:以上|及以上|後|時)|累積移動|未進行過移動|移動距離"),
    ("獲得或遭受強化／弱化時", r"(?:獲得|遭受|被施加)[^，。；]{0,6}(?:強化|弱化)(?:效果|狀態)(?:時|後)"),
    ("被治療時", r"(?:受到|遭受|被)[^，。；]{0,6}治療(?:時|後)"),
]
TIMING_C = [(n, re.compile(p)) for n, p in TIMING]
COND_RE = re.compile(r"若|如果|假如|(?<!相)當|擁有|具有|處於|位於|存在|沒有|高於|低於|大於|小於|多於|少於|生命(?:值)?\s*[>＞<＜]"
                     r"|觸發[^，。；]{0,14}時|生命\d+%以[上下]|步兵|槍兵|騎兵|飛兵|水兵|弓兵|法師|僧侶|魔物|刺客|樹林|山地|水中|草地|沙漠|城牆|平地|地形|水域|雪地"
                     r"|女性|男性|近戰|遠程|觸發冷卻|需要間隔|每場戰鬥最多|每回合最多|最多觸發|只能觸發|競技模式")
LIMIT_RE = re.compile(r"觸發冷卻|需要間隔|每場戰鬥最多|每回合最多|最多觸發|只能觸發")

# 驅散／免疫註記
NOTE_BOTH = re.compile(r"(?:無法|不可|不能)(?:被)?(?:驅散[和與及、]免疫|免疫[和與及、]驅散)")
NOTE_DISP = re.compile(r"(?:無法|不可|不能)(?:被)?驅散")
NOTE_IMMU = re.compile(r"(?:無法|不可|不能)(?:被)?免疫")
NOTE_ALL = re.compile(r"(本技能施加的|所有效果|所有特殊效果|上述|以上)[^。；]{0,8}$")

# 關鍵字效果（研究喵 BUFF_KW／DEBUFF_KW 修過三輪的版本，加上這次要的排除）
KW = [
    ("不死", "buff", r"(?<!\[)(?<!觸發)抵擋[^，。；]{0,4}致命傷害|不會死亡(?!時)|免除[^，。；]{0,4}致命|不會遭受致命一擊"),
    ("先攻", "buff", r"先於敵(?:軍|方)[^，。；]{0,4}攻擊|先攻"),
    ("護衛", "buff", r"替[^，。；]{0,8}承受[^，。；]{0,4}攻擊|護衛範圍"),
    ("無視", "buff", r"無視[^，。；]{0,6}?(?:防禦|魔防|護衛|地形|減免|阻擋)"),
    ("隨機強化", "buff", r"隨機[^，。；]{0,4}強化(?:效果|狀態)(?![^，。；]{0,2}(?:持續回合|回合數))"),
    ("超絕強化", "buff", r"攻防能力大幅提升"),
    ("強化回合不減", "buff", r"強化(?:效果|狀態)(?:回合數|持續時間)不會減少"),
    ("反彈傷害", "buff", r"(?<!遭受)反彈(?!下)"),
    ("無法反擊", "debuff", r"無法反擊|不能反擊"),
    ("沉默", "debuff", r"無法使用主動技能"),
    ("定身", "debuff", r"(?<!\()無法移動"),
    ("眩暈", "debuff", r"眩暈|暈眩|無法行動|催眠|冰凍"),
    ("禁療", "debuff", r"無法(?:被|遭受)治療|治療反轉|治療[^，。；]{0,4}轉(?:化|變)為傷害|治療效果變為[^，。；]{0,8}傷害"),
    ("禁強化", "debuff", r"無法(?:遭受|獲得)強化"),
    ("禁護衛", "debuff", r"無法(?:進行)?護衛|不能護衛|無法被護衛"),
    ("持續傷害", "debuff", r"灼燒|流血"),
    ("偷取強化", "debuff", r"偷取[^，。；]{0,10}強化"),
    ("強力弱化", "debuff", r"強力弱化(?:效果|狀態)"),
    ("隨機弱化", "debuff", r"隨機[^，。；]{0,4}弱化(?:效果|狀態)(?![^，。；]{0,2}(?:持續回合|回合數))"),
    ("嘲諷", "debuff", r"嘲諷"),
    ("被動失效", "debuff", r"被動技能失效"),
    ("兵種特效", "buff", r"對(?:\"[^\"，。；]{1,4}\"[和與及、]?)+有特效"),
]
KW_C = [(t, p, re.compile(r)) for t, p, r in KW]
KW_PRIORITY = {"強力弱化": 0, "偷取強化": 1}           # 同一段同時中兩條時留誰（數字小的優先）
COUNT_BEFORE = re.compile(r"(\d+|[一二兩三四五])個[^，。；]{0,8}$")
IMMUNE_RE = re.compile(r"(?<!無法)(?<!法被)(?<!不可)(?<!不能)(?<!驅散和)(?<!驅散與)(?<!驅散及)(?<!驅散、)免疫(?![和與及、]驅散)(?!的)"
                       r"(?P<obj>[^，。；]{0,14})")
DISPEL_RE = re.compile(r"(?<![不法被能可])(?:驅散|清除)(?P<who>[^，。；]{0,10}?)(?:(?P<n>\d+|[一二兩三四五])個|(?P<all>所有|全部))?"
                       r"[^，。；\d]{0,4}?(?P<k>強化|弱化)(?:效果|狀態)")
AGAIN_RE = re.compile(r"(?<!觸發)(?:額外|再次|再)(?:行動|移動)(?!時)|再次攻擊")
SHIELD_KW = re.compile(r"(?:獲得|施加|轉化為|提供)[^，。；]{0,12}?\[護盾\]")
SHIELD_RE = [
    (re.compile(r"抵擋[^，。；\d]{0,8}?(?P<v>\d+(?:\.\d+)?)%(?:的)?最大生命"), "目標最大生命", "%"),
    (re.compile(r"抵擋[^，。；\d]{0,8}?最大生命(?:值)?(?:的)?(?P<v>\d+(?:\.\d+)?)%"), "目標最大生命", "%"),
    (re.compile(r"抵擋[^，。；\d]{0,10}?(?P<s>智力|攻擊|防禦|魔防)(?:的)?(?P<v>\d+(?:\.\d+)?)倍"), "施放者{s}", "倍"),
]
HEAL_RE = [
    (re.compile(r"恢復(?P<pre>[^，。；]{0,16}?)(?P<v>\d+(?:\.\d+)?)%(?:的)?(?:部隊)?(?P<max>最大)?生命"), None, "%"),
    (re.compile(r"恢復[^，。；\d]{0,10}?(?P<b>最大生命|已損失生命|損失生命|剩餘生命)(?:值)?的(?P<v>\d+(?:\.\d+)?)%"), None, "%"),
    (re.compile(r"生命(?:值)?恢復(?P<v>\d+(?:\.\d+)?)%"), "目標生命", "%"),
    (re.compile(r"(?P<who>施法者|施放者|施加者|攻擊者|自身|英雄)?(?P<s>智力|攻擊|防禦|魔防)(?:的)?(?P<v>\d+(?:\.\d+)?)倍(?:的)?(?:生命|治療)"),
     "施放者{s}", "倍"),
    (re.compile(r"恢復量為[^，。；\d]{0,6}?(?P<s>智力|攻擊|防禦|魔防)的?(?P<v>\d+(?:\.\d+)?)倍"), "施放者{s}", "倍"),
    (re.compile(r"(?P<v>\d+(?:\.\d+)?)倍(?P<s>智力|攻擊|防禦|魔防)的生命"), "施放者{s}", "倍"),
]
LIFESTEAL_RE = [
    re.compile(r"恢復[^，。；]{0,10}?造成(?:的)?傷害(?:數值)?(?:的)?(?P<v>\d+(?:\.\d+)?)%(?:的)?生命"),
    re.compile(r"恢復量為[^，。；]{0,6}造成(?:的)?傷害的?(?P<v>\d+(?:\.\d+)?)%"),
]
REFLECT_RE = re.compile(r"反彈[^，。；]{0,12}?(?P<v>\d+(?:\.\d+)?)%")
FIXED_WORD = re.compile(r"固定傷害")
FIXED_BASE = [
    (re.compile(r"(?P<s>攻擊|智力|防禦|魔防)(?:力)?(?:的)?(?P<v>\d+(?:\.\d+)?)倍"), "倍"),
    (re.compile(r"(?P<v>\d+(?:\.\d+)?)倍(?:的)?(?P<s>攻擊|智力|防禦|魔防)"), "倍"),
    (re.compile(r"(?P<s>最大生命|剩餘生命|已損失生命)[^，。；\d]{0,6}?(?P<v>\d+(?:\.\d+)?)%"), "%"),
    (re.compile(r"(?P<v>\d+(?:\.\d+)?)%(?:的)?(?P<s>最大生命|剩餘生命|已損失生命)"), "%"),
]
CASTER = re.compile(r"施法者|施放者|施加者|攻擊者|自身|英雄|托娃")

# 誰吃到這個效果：取效果前面最後一個「對象詞」
TARGET_TOKENS = [
    (re.compile(r"(?:單個|1個|1名|一名|一個|最近的)(?:其他)?敵(?:軍|方)(?:部隊|英雄)?"), "單個敵軍"),
    (re.compile(r"全場[^，。；]{0,6}?敵(?:軍|方)"), "全場敵軍"),
    (re.compile(r"(?:所有|全部|多個|範圍內|周圍|相鄰|直線上)[^，。；]{0,8}?敵(?:軍|方)"), "範圍敵軍"),
    (re.compile(r"敵軍|敵方(?:部隊|英雄)?|傷害來源|攻擊來源|攻擊者"), "敵軍"),
    (re.compile(r"(?:單個|1個|1名|一名|一個)(?:其他)?(?:友軍|(?<!軍)(?<!方)部隊)|(?:最低|最高)的(?:其他)?友軍"), "單個友軍"),
    (re.compile(r"全場[^，。；]{0,4}?友軍"), "全場友軍"),
    (re.compile(r"(?:所有|全部|多個|範圍內|周圍|相鄰)[^，。；]{0,8}?(?:友軍|(?<!軍)(?<!方)部隊)"), "範圍友軍"),
    (re.compile(r"友軍|這些部隊"), "友軍"),
    (re.compile(r"使其|對其|令其|讓其|(?<![尤極])其(?![他餘中])|目標"), "其"),
    (re.compile(r"自身|自己|施放者|施法者|本部隊|此部隊|(?<![軍方個])部隊|本次(?=傷害)|(?:本技能|此技能|該技能)(?=的?傷害|造成)"), "自身"),
    (re.compile(r"召喚|分身|虛影|幻象|感召"), "召喚物"),
]
GAIN = re.compile(r"獲得|進入(?=\[)")
INSTANT = {"回血", "吸血", "驅散", "固定傷害", "冷卻縮短", "冷卻增加", "再動", "偷取強化", "先攻"}
TRIGGERED = INSTANT | {"隨機弱化", "隨機強化", "強力弱化"}
NON_STATUS = INSTANT | {"強化回合不減", "兵種特效"}     # 不是掛在身上的狀態：不掛持續回合、不吃「不可驅散」
DMG_CATS = ("物理傷害", "魔法傷害")


class Parser:
    def __init__(self, rec):
        self.rec = rec
        self.t = norm(rec["text"])
        self.raw_text = rec["text"]
        self.effects = []
        self.damage = []
        self.claimed = []          # 被規則吃掉的區間（算覆蓋率用）

    # ── 小工具 ──
    def raw(self, s, e):
        return self.raw_text[s:e]

    def seg_of(self, pos):
        for s, e, kind in self.segs:
            if s <= pos < e:
                return kind
        return self.segs[-1][2]

    def scope_of(self, pos):
        for s, e in self.scopes:
            if s <= pos < e:
                return s, e
        return self.scopes[-1]

    def clause_start(self, pos, floor):
        return max(floor, max(self.t.rfind(c, 0, pos) for c in "，。；:") + 1)

    def is_active_dmg_segment(self, pos):
        return self.rec["kind"] == "技能" and self.seg_of(pos) == "主動" and self.rec.get("category") in DMG_CATS

    def area_scope(self):
        area = self.rec.get("area")
        if area is None:
            return None
        return "單體" if area in ("單體", "自身") else "範圍"

    def add(self, typ, pol, s, e, **kw):
        eff = {"polarity": pol, "type": typ, "stat": kw.get("stat"), "value": kw.get("value"), "unit": kw.get("unit"),
               "base": kw.get("base"), "_s": s, "_e": e}
        self.effects.append(eff)
        return eff

    # ── 主流程 ──
    def run(self):
        t, rec = self.t, self.rec
        start = 0
        if rec["kind"] == "專屬裝備":
            m = GEAR_STAT.match(t)
            if m:
                rec["gear_stat"] = {"stat": "、".join(re.split(r"[、，]", m.group(1))), "value": num(m.group(2)), "unit": "%",
                                    "raw": self.raw(m.start(), m.end(2) + 1),
                                    "note": "裝備本身的能力加成，隨強化等級變（遊戲畫面拍的是學長當時的等級），不是技能效果"}
                self.claimed.append((m.start(), m.end()))
                start = m.end()
        default = None
        if rec["kind"] == "技能":
            default = "被動" if rec.get("category") == "被動" else "主動"
        self.segs = [(s if s else start, e, k) for s, e, k in segments(t[:], default) if e > start]
        balanced = t.count('"') % 2 == 0 and t.count("(") == t.count(")")
        self.scopes, self.fines = [], []
        for s, e, _ in self.segs:
            s = max(s, start)
            self.scopes += split_sentences(t, s, e, balanced)
            self.fines += split_sentences(t, s, e, False)
        self.inq = quote_mask(t)
        self.parse_damage()
        self.parse_stats()
        self.parse_values()
        self.parse_keywords()
        self.effects = sorted((x for x in self.effects if x["_s"] >= start), key=lambda x: x["_s"])   # 裝備能力加成那句不算效果
        for eff in self.effects:
            eff["_raw_of"] = {}
        self.attach_caps()
        for eff in self.effects:
            self.attach_context(eff)
        self.attach_notes()
        return self.finish()

    # ── 傷害倍率 ──
    def parse_damage(self):
        rec = self.rec
        for m in DMG.finditer(self.t):
            pos = m.start()
            hits = re.match(r"(\d+)次", m.group("pre"))
            d = {"multiplier": num(m.group("v")), "dtype": None, "scope": None}
            if m.group("dt"):
                d["dtype"], d["dtype_from"] = m.group("dt"), "text"
            elif self.is_active_dmg_segment(pos):
                d["dtype"], d["dtype_from"] = rec["category"][:2], "category"
            if self.is_active_dmg_segment(pos) and self.area_scope():
                # area 欄描述的是傷害技能（分類為物理／魔法傷害）的打擊範圍；支援、主動類技能的 area 是位移或增益的範圍
                d["scope"], d["scope_from"] = self.area_scope(), "area"
            else:
                s0, _ = self.scope_of(pos)
                ctx = self.t[max(s0, self.clause_start(pos, s0) - 12):m.end()]
                wide = m.group("area") or m.group("area2") or re.search(r"所有|周圍|範圍內|直線|全場|多個", ctx[-30:])
                d["scope"], d["scope_from"] = ("範圍" if wide else "單體"), "text"
            if hits:
                d["hits"] = int(hits.group(1))
            d["segment"] = self.seg_of(pos)
            d["raw"] = self.raw(m.start(), m.end())
            self.damage.append(d)
            self.claimed.append((m.start(), m.end()))

    # ── 屬性詞＋方向＋數字 ──
    def stat_kind(self, stat, pre, gap, up):
        recv = bool(re.search(r"(遭受|受到)[^後時]*$", pre)) or bool(re.search(r"受[^，。；後時]{0,6}$", pre)) or \
            gap.startswith("受")
        if stat in ("暴擊率", "暴擊傷害"):
            if recv:
                return ("防暴擊", "buff") if not up else ("受暴擊提升", "debuff")
            return ("暴擊提升", "buff") if up else ("暴擊降低", "debuff")
        if stat == "傷害":
            if recv:
                return ("減傷", "buff") if not up else ("易傷", "debuff")
            return ("增傷", "buff") if up else ("降傷", "debuff")
        if stat == "治療效果":
            if recv or "受" in pre[-3:]:
                return ("受治療提升", "buff") if up else ("受治療降低", "debuff")
            return ("治療效果提升", "buff") if up else ("治療效果降低", "debuff")
        if stat == "冷卻時間":
            return ("冷卻縮短", "buff") if not up else ("冷卻增加", "debuff")
        if stat in ("移動力", "射程"):
            return ("移動力／射程提升", "buff") if up else ("移動力／射程降低", "debuff")
        if recv:
            return None
        return ("屬性提升", "buff") if up else ("屬性降低", "debuff")

    def parse_stats(self):
        t = self.t
        for m in STAT_RE.finditer(t):
            pre, gap = m.group("pre"), m.group("gap")
            clause_pre = pre[max(pre.rfind("，"), pre.rfind("("), -1) + 1:]
            if CAPW.search(clause_pre + m.group("stats") + gap):
                continue                                   # 「最多提升 N%」是封頂，由 attach_caps 處理
            if self.in_pool_paren(m.start("stats")):
                continue                                   # 「強力弱化效果(…移動力-5…)」是候選池
            if "固定" in gap or (m.group("stats") == "傷害" and re.search(r"固定$|\]$", pre)):
                continue                                   # 「遭受固定傷害降低」以外的固定傷害寫法交給 parse_values
            stats = STAT_ONE.findall(m.group("stats"))
            if "，" in m.group("stats") and re.search(r"(恢復|回復|損失|消耗|剩餘|最大)$", pre):
                stats = stats[1:]
            up = m.group("dir") in ("提升", "增加", "提高", "+")
            stat = stats[-1]
            kind = self.stat_kind(stat, pre, gap, up)
            if not kind:
                continue
            if m.group("pct"):
                unit = "%"
            elif stat in ("移動力", "射程"):
                unit = "格"
            elif stat == "冷卻時間":
                unit = "回合"
            else:
                unit = "點"
            stat_name = "、".join(stats)
            s, e = m.start("stats"), m.end()
            if unit in ("格", "回合") and t.startswith(unit, e):
                e += len(unit)
            self.add(kind[0], kind[1], s, e, stat=stat_name, value=num(m.group("v")), unit=unit)

        for m in STAT_RE2.finditer(t):
            if self.overlaps(m.start(), m.end()):
                continue
            stats = STAT_ONE.findall(m.group("stats"))
            up = m.group("dir") in ("提升", "增加", "提高")
            kind = self.stat_kind(stats[-1], m.group("who"), "", up)
            if kind:
                self.add(kind[0], kind[1], m.start(), m.end(), stat="、".join(stats), value=num(m.group("v")), unit="%")

    # ── 回血、吸血、護盾、固定傷害、持續傷害、反彈 ──
    def parse_values(self):
        t = self.t
        for rx in LIFESTEAL_RE:
            for m in rx.finditer(t):
                self.add("吸血", "buff", m.start(), m.end(), value=num(m.group("v")), unit="%", base="造成傷害")
        for rx, base, unit in HEAL_RE:
            for m in rx.finditer(t):
                if self.overlaps(m.start(), m.end(), ("吸血", "回血")):
                    continue
                gd = m.groupdict()
                if gd.get("pre") is not None and "傷害" in gd["pre"]:
                    continue
                if base is None:
                    if gd.get("b"):
                        b = "目標" + gd["b"].replace("損失生命", "已損失生命").replace("已已", "已")
                    elif gd.get("max"):
                        b = "目標最大生命"
                    else:
                        b = "目標生命"
                else:
                    b = base.format(s=gd.get("s"))
                    if gd.get("who") == "施加者":
                        b = b.replace("施放者", "施加者")
                self.add("回血", "buff", m.start(), m.end(), value=num(m.group("v")), unit=unit, base=b)
        for rx, base, unit in SHIELD_RE:
            for m in rx.finditer(t):
                if "致命" in m.group(0):
                    continue
                self.add("護盾", "buff", m.start(), m.end(), value=num(m.group("v")), unit=unit,
                         base=base.format(s=m.groupdict().get("s")))
        for m in SHIELD_KW.finditer(t):
            s0, e0 = self.scope_of(m.start())
            if not any(x["type"] == "護盾" and s0 <= x["_s"] < e0 for x in self.effects):
                self.add("護盾", "buff", m.start(), m.end())
        for m in REFLECT_RE.finditer(t):
            self.add("反彈傷害", "buff", m.start(), m.end(), value=num(m.group("v")), unit="%", base="受到傷害")
        for w in FIXED_WORD.finditer(t):
            after, before = t[w.end():w.end() + 4], t[max(0, w.start() - 6):w.start()]
            if re.match(r"\]?(時|後|的生命|降低|提升)", after) or re.search(r"免疫\"?$|該\[?$|遭受$|受到$", before):
                continue
            s0, e0 = self.scope_of(w.start())
            lo, hi = max(s0, w.start() - 26), min(e0, w.end() + 22)
            best = None
            for rx, unit in FIXED_BASE:
                for m in rx.finditer(t, lo, hi):
                    dist = abs(m.start() - w.start())
                    if best is None or dist < best[0]:
                        best = (dist, m, unit)
            if not best:
                continue
            _, m, unit = best
            stat = m.group("s")
            who = None
            if "生命" in stat:
                base = "目標" + stat
            else:
                who = list(CASTER.finditer(t, max(lo, m.start() - 8), m.start()))
                who = who[-1] if who else None
                base = ("施加者" if who and who.group(0) == "施加者" else "施放者") + stat
            ctx = t[s0:w.end()]
            dot = re.search(r"(行動結束|回合開始|回合結束)[^。；]{0,14}受到", ctx[-40:]) or "灼燒" in ctx[-30:]
            s, e = min(m.start(), w.start(), who.start() if who else len(t)), max(m.end(), w.end())
            e += 1 if t[e:e + 1] == "]" else 0
            self.add("持續傷害" if dot else "固定傷害", "debuff", s, e, value=num(m.group("v")), unit=unit, base=base)

    def overlaps(self, s, e, types=None):
        return any(x["_s"] < e and s < x["_e"] and (types is None or x["type"] in types) for x in self.effects)

    def immune_ctx(self, pos):
        s0, _ = self.scope_of(pos)
        a = max(s0, pos - 14)
        return "免疫" in self.t[a:pos]

    def in_pool_paren(self, pos):
        """「強力弱化效果(無法被治療，眩暈，…)」括號裡列的是候選池，不是各自施加。"""
        open_ = self.t.rfind("(", 0, pos)
        return open_ != -1 and self.t.find(")", open_) > pos and re.search(r"弱化(效果|狀態)$", self.t[max(0, open_ - 6):open_])

    # ── 關鍵字效果 ──
    def parse_keywords(self):
        t = self.t
        hits = []
        for typ, pol, rx in KW_C:
            for m in rx.finditer(t):
                if pol == "debuff" and (self.immune_ctx(m.start()) or self.in_pool_paren(m.start())):
                    continue
                if typ in ("先攻", "沉默", "定身", "眩暈") and re.search(r"無法觸發|免疫[^，。；]{0,3}$", t[max(0, m.start() - 6):m.start()]):
                    continue
                hits.append((typ, pol, m))
        hits.sort(key=lambda h: (KW_PRIORITY.get(h[0], 9), h[2].start()))
        kept = []
        for h in hits:
            if any(k[2].start() < h[2].end() and h[2].start() < k[2].end() for k in kept):
                continue
            kept.append(h)
        kept.sort(key=lambda h: h[2].start())
        for typ, pol, m in kept:
            if self.overlaps(m.start(), m.end(), (typ,)):
                continue
            c0 = self.clause_start(m.start(), 0)
            if re.search(r"(擁有|具有|存在|處於|帶有)[^，。；]{0,16}$", t[c0:m.start()]) and \
                    re.match(r"[^，。；]{0,12}?(時|則|的敵軍|的友軍|的部隊)", t[m.end():]):
                continue                     # 「擁有[護盾]時」「敵軍擁有…[治療反轉]效果」是條件，不是給這個效果
            if typ == "持續傷害":
                s0, e0 = self.scope_of(m.start())
                if any(x["type"] == "持續傷害" and m.end() <= x["_s"] <= m.end() + 40 and x["_s"] < e0 for x in self.effects):
                    continue                 # 「[灼燒]:“…受到攻擊1倍的固定傷害”」是狀態名，數值那筆已經記了
            kw = {}
            if typ in ("隨機強化", "隨機弱化", "強力弱化", "偷取強化"):
                c = COUNT_BEFORE.search(t, max(0, m.start() - 14), m.start()) or re.search(r"(\d+|[一二兩三四五])個", m.group(0))
                if c:
                    kw = {"value": num(c.group(1)), "unit": "個"}
            elif typ == "禁療":
                v = re.search(r"治療量(\d+)%", t[m.start():m.end() + 10])
                if v:
                    kw = {"value": num(v.group(1)), "unit": "%"}
            elif typ == "兵種特效":
                kw = {"stat": "、".join(re.findall(r'"([^"]+)"', m.group(0)))}
            elif typ == "無視":
                kw = {"stat": re.search(r"(防禦|魔防|護衛|地形|減免|阻擋)", m.group(0)).group(1)}
                v = re.search(r"(\d+)%", m.group(0))
                if v:
                    kw.update(value=num(v.group(1)), unit="%")
            elif typ == "護衛":
                v = re.match(r"(?:提升為|為|\+)?(\d+)格", t[m.end():m.end() + 6])
                if v:
                    kw = {"value": num(v.group(1)), "unit": "格"}
            self.add(typ, pol, m.start(), m.end(), **kw)
        for m in IMMUNE_RE.finditer(t):
            obj = m.group("obj")
            if t[m.start() - 1:m.start()] == "[":
                obj = ""                         # 具名狀態 [免疫]，後面接的不是免疫的對象
            obj = re.split(r"[\"']", obj)[0] if not obj.startswith(('"', "'")) else obj[:obj.find(obj[0], 1) + 1] or obj
            stat = re.sub(r"^(?:並|且)?(?:反彈)?", "", obj)
            v = re.search(r"下(\d+)個", stat)
            self.add("免疫", "buff", m.start(), m.start() + 2 + len(obj), stat=stat or None,
                     value=num(v.group(1)) if v else None, unit="個" if v else None)
        for m in DISPEL_RE.finditer(t):
            if t[m.start() - 1:m.start()] == "每":
                continue                         # 「每驅散一個弱化效果，則恢復10%生命」是計數
            n = m.group("n")
            buff = m.group("k") == "弱化"
            self.add("驅散", "buff" if buff else "debuff", m.start(), m.end(), stat=m.group("k") + "效果",
                     value=None if n is None else num(n), unit="個")
        for m in AGAIN_RE.finditer(t):
            c0 = self.clause_start(m.start(), 0)
            if re.search(r"無法|不能|觸發", t[c0:m.start()]) or re.search(r"效果", t[m.end():m.end() + 2]):
                continue
            near = [x for x in self.effects if x["type"] == "再動" and m.start() - x["_e"] <= 6 and x["_e"] <= m.end()]
            v = re.match(r"(\d+)格", t[m.end():m.end() + 4])
            if near:
                x = near[-1]
                x["_e"] = m.end() + (v.end() if v else 0)
                if v and x["value"] is None:
                    x["value"], x["unit"] = num(v.group(1)), "格"
                continue
            self.add("再動", "buff", m.start(), m.end() + (v.end() if v else 0),
                     value=num(v.group(1)) if v else None, unit="格" if v else None)

    # ── 封頂與疊層 ──
    def attach_caps(self):
        t = self.t
        for m in CAP_RE.finditer(t):
            unit = m.group("u")
            if unit == "次" or re.search(r"觸發|使用", m.group("who") or "") or "機率" in t[max(0, m.start() - 4):m.start()]:
                continue
            s0, e0 = self.scope_of(m.start())
            before = [x for x in self.effects if s0 <= x["_s"] < m.start()]
            stack = m.group("acc") or unit == "層" or STACK_NEAR.search(t[max(s0, m.start() - 8):m.start()])
            if stack:
                targets = [x for x in before if x.get("stack_max") is None]
                for x in targets:
                    x["stack_max"] = num(m.group("v"))
                    x["_raw_of"]["stack_max"] = (m.start(), m.end())
                continue
            cands = [x for x in before if x.get("cap") is None and (x["value"] is not None or unit == "個")]
            if cands:
                x = cands[-1]
                x["cap"] = num(m.group("v"))
                x["cap_unit"] = unit or x["unit"]
                x["_raw_of"]["cap"] = (m.start(), m.end())

    # ── 時機、對象、條件、持續、機率、每 X ──
    def attach_context(self, eff):
        t, rec = self.t, self.rec
        s0, e0 = self.scope_of(eff["_s"])
        pos = eff["_s"]
        eff["segment"] = self.seg_of(pos) if rec["kind"] == "技能" else None
        prefix = t[s0:pos]
        # 同一句裡前一個效果；中間沒有「。；」才算同一串（「戰鬥中攻擊提升20%，防禦提升10%」的防禦也是戰鬥中）
        prev = next((x for x in reversed(self.effects) if s0 <= x["_s"] < pos and "timing" in x), None)
        between = t[prev["_e"]:pos] if prev else ""
        chained = bool(prev) and not re.search(r"[。；]", between)
        lo = prev["_s"] if prev else s0
        # 時機：前一個效果開頭到這個效果之間的時機詞；這段沒有就沿用前一個效果的
        found = sorted((m.start(), m.end(), name) for name, rx in TIMING_C for m in rx.finditer(t, lo, pos))
        timing = []
        for a, b, name in found:
            if name not in timing:
                timing.append(name)
            eff["_raw_of"].setdefault("timing", []).append((a, b))
        if not found and chained:
            timing = list(prev["timing"])
            if "timing" in prev["_raw_of"]:
                eff["_raw_of"]["timing"] = list(prev["_raw_of"]["timing"])
        lead_static = rec["kind"] == "鑄紋技能" and pos == 0 and "+" in t[pos:eff["_e"]]
        if lead_static:
            timing = []                          # 鑄紋開頭的「智力+5%」是鑄紋本身的常駐加成，後面的時機、回合數不是它的
            eff["_raw_of"].pop("timing", None)
        eff["timing"] = timing
        # 持續：同一句裡效果後面第一個「持續 N 回合」，沒有再看前面的「N 回合的」
        eff["duration"] = None
        if (eff["type"] not in NON_STATUS or self.inq[pos]) and not lead_static:
            hi = e0
            if self.inq[pos] and eff["type"] in TRIGGERED:
                q = t.find('"', eff["_e"], e0)
                hi = q if q != -1 else e0        # 狀態裡觸發才施加的，引號外的回合數是狀態本身的
            d = DUR_RE.search(t, eff["_e"], hi)
            if not d:
                d = next(reversed(list(DUR_BEFORE.finditer(t, s0, pos))), None)
            if d:
                n = d.group("n")
                eff["duration"] = int(n) if n else None
                eff["_raw_of"]["duration"] = (d.start(), d.end())
        passive_ctx = rec["kind"] in PASSIVE_KINDS or eff["segment"] == "被動"
        eff["permanent"] = bool(passive_ctx and "duration" not in eff["_raw_of"] and eff["type"] not in NON_STATUS | TRIGGERED
                                and not timing and not self.inq[pos] and not CHANCE_RE.search(prefix))
        # 每 X：同一句裡最近的「每…」，中間不能隔著別的效果；隔著的話沿用前一個效果的（「每移動1格，攻擊提升4%，防禦提升20%」）
        per = [m for m in PER_RE.finditer(t, s0, pos)]
        eff["per"] = None
        if per:
            m = per[-1]
            end = min(m.end(), pos)
            if t[end:pos].count("，") <= 1 and not any(end <= x["_s"] < pos for x in self.effects):
                eff["per"] = self.raw(m.start(), end).rstrip("，,")
                eff["_raw_of"]["per"] = (m.start(), end)
            elif chained and prev.get("per") and prev["value"] is not None and eff["value"] is not None:
                eff["per"] = prev["per"]
                eff["_raw_of"]["per"] = prev["_raw_of"]["per"]
        # 機率
        ch = list(CHANCE_RE.finditer(t, s0, pos))
        eff["chance"] = int(ch[-1].group(1)) if ch else None
        if ch:
            eff["_raw_of"]["chance"] = (ch[-1].start(), ch[-1].end())
        # 條件：前一個效果開頭到這個效果之間、本身沒有效果的小句；這段沒有就沿用前一個效果的（隔了引號不沿用）
        conds = []
        a = lo
        while a < pos:
            b = min([i for i in (t.find(c, a, pos) for c in "，:；。") if i != -1] or [pos])
            piece = t[a:b]
            then = t[b + 1:b + 2] in ("則", "就") if b < pos else False
            skip = "有特效" in piece or piece.lstrip().startswith("每") or \
                (piece.lstrip().startswith("(") and LIMIT_RE.search(piece))   # 每 X 放 per；次數限制的括號只往前掛
            if (COND_RE.search(piece) or then) and not skip and not any(a <= x["_s"] < b for x in self.effects):
                conds.append((a, b))
            a = b + 1
        if not conds and chained and '"' not in between and prev["_raw_of"].get("condition"):
            conds = [c for c in prev["_raw_of"]["condition"] if t[c[0]:c[0] + 1] != "("]
        # 次數限制、觸發冷卻的括號註記：效果後面、中間沒隔「；」或句號（括號前緊貼的句號不算）
        for m in list(LIMIT_RE.finditer(t, eff["_e"], e0))[:1]:
            p0 = t.rfind("(", eff["_e"], m.start())
            if p0 != -1 and not re.search(r"[。；]", t[eff["_e"]:p0].rstrip("。")):
                p1 = t.find(")", m.start(), e0)
                conds.append((p0, p1 + 1 if p1 != -1 else e0))
        conds = [(a + len(m.group(0)) if (m := SEG_TAG.match(t, a)) else a, b) for a, b in conds]
        eff["condition"] = [self.raw(a, b).strip(" ，,") for a, b in conds if self.raw(a, b).strip(" ，,")] or None
        if conds:
            eff["_raw_of"]["condition"] = conds
        # 對象
        eff["target"], eff["target_from"] = self.target(eff, s0, pos)
        if eff["polarity"] == "debuff" and (eff["target"] in ("自身", "召喚物")):
            eff["polarity"] = "neutral"           # 施放者自己吃的代價、召喚物的屬性定義，不算對敵弱化

    def resolve(self, label, pos, seg_start):
        """「其」「目標」往前找最近的敵軍／友軍；找不到依技能的 area。"""
        if label != "其":
            return label, "text"
        best = None
        for rx, lab in TARGET_TOKENS:
            if lab in ("其", "自身", "召喚物"):
                continue
            for m in rx.finditer(self.t, seg_start, pos):
                if best is None or m.end() > best[0] or (m.end() == best[0] and m.end() - m.start() > best[1]):
                    best = (m.end(), m.end() - m.start(), lab)
        if best:
            return best[2], "text"
        return None, None

    def in_when_clause(self, at, s0, pos):
        """at 所在的小句是不是觸發條件：「…時，」或「…，則…」。"""
        c0 = self.clause_start(at + 1, s0)
        ends = [i for i in (self.t.find("，", at, pos), self.t.find(":", at, pos)) if i != -1]
        if not ends:
            return False                   # 跟效果在同一小句
        end = min(ends)
        return self.t[c0:end].rstrip('"').endswith("時") or self.t[end + 1:end + 2] in ("則", "就")

    def tokens(self, eff, s0, pos):
        """效果前面（含效果本身那段裡的敵軍／友軍）所有對象詞，照位置排。"""
        t, out = self.t, []
        in_quote = self.inq[pos]
        actor_only = eff["type"] in ("驅散", "偷取強化") and eff["polarity"] == "debuff"
        for rx, lab in TARGET_TOKENS:
            # 只有驅散看效果本身那段裡的對象（「驅散敵軍1個強化效果」）；其他效果那段裡的詞是基準（「自身攻擊2倍」）
            end = eff["_e"] if eff["type"] == "驅散" and lab not in ("自身", "其", "召喚物") else pos
            per = eff["_raw_of"].get("per")
            for m in rx.finditer(t, s0, end):
                if per and per[0] <= m.start() < per[1]:
                    continue               # 「每命中1名友軍」是計數，不是對象
                if any(x is not eff and x["_s"] <= m.start() < x["_e"] for x in self.effects):
                    continue               # 別的效果本身那段裡的詞（「替相鄰友軍承受攻擊，遭受暴擊率降低」的友軍）
                if eff["polarity"] == "buff" and self.in_when_clause(m.start(), s0, pos):
                    continue               # 「命中友軍時，冷卻時間-1」：「…時」那一小句是觸發條件，裡面的對象不是受益者
                if lab == "自身":
                    if actor_only or re.match(r"擁有|的|周圍|所在|最多", t[m.end():m.end() + 2]):
                        continue           # 「對敵軍施加等同於自身擁有…」的自身是所有格，不是對象
                    if in_quote and self.inq[m.start()]:
                        continue           # 狀態定義（引號）裡的「自身」指持有這個狀態的部隊，回到引號前面找
                out.append((m.end(), m.end() - m.start(), lab, m.start()))
        out.sort()
        return out

    def target(self, eff, s0, pos):
        t, rec = self.t, self.rec
        seg_start = next((s for s, e, k in self.segs if s <= pos < e), 0)
        toks = self.tokens(eff, s0, pos)
        best = max(toks, key=lambda x: (x[0], x[1])) if toks else None
        c_eff = self.clause_start(pos, s0)
        if eff["type"] == "固定傷害":
            # 一次性固定傷害打的是別人：只看同一小句附近的對象詞，沒有就照傷害技能的 area
            near = [x for x in toks if x[3] >= c_eff - 12 and x[2] != "自身"]
            best = max(near, key=lambda x: (x[0], x[1])) if near else None
        c_prev = self.clause_start(max(s0, c_eff - 1), s0)
        if eff["type"] == "降傷" and not (best and best[3] >= c_prev) and not self.inq[pos] and \
                (PER_RE.search(t, max(s0, c_eff - 16), pos) or re.search(r"第.次", t[c_eff:pos])):
            return "自身", "text"               # 「每移動1格，傷害降低5%」：本技能自己的倍率衰減
        gains = list(GAIN.finditer(t, s0, pos))
        if gains and eff["type"] != "固定傷害":
            g = gains[-1]
            gc = self.clause_start(g.start(), s0)
            pc = max(s0, gc - 1)
            prev_clause = t[self.clause_start(pc, s0):pc]
            governed = best and re.search(r"(使|令|讓|為|對)得?$", t[max(s0, best[3] - 3):best[3]])
            # 「獲得」沒寫主詞時是自己拿到；但主詞從前一小句延續（「敵軍…行動結束時，獲得…」「使敵軍…，獲得…」）時不算
            friendly = best and "友軍" in best[2]
            if best is None or (best[3] < gc and not self.inq[g.start()] and "時" not in t[gc:g.start()]
                                and not governed and not friendly and not prev_clause.endswith(("時", "後"))):
                best = (g.end(), 2, "自身", g.start())
        if best and best[2] == "自身" and best[3] < c_eff and eff["polarity"] == "debuff" and \
                re.search(r"造成(?!的?傷害)|施加|附加", t[c_eff:pos]):
            best = None                          # 「部隊…，20%機率造成強力弱化效果」：造成／施加的對象是對手
        label, src = None, None
        if best:
            label, src = self.resolve(best[2], best[3], seg_start)
            if label in ("敵軍", "單個敵軍", "範圍敵軍", "全場敵軍") and eff["polarity"] == "buff":
                label = None                     # 增益不會給敵軍，這個對象詞是傷害句的，不是這個效果的
        if eff["type"] == "固定傷害" and label and "友軍" in label:
            label = label.replace("友軍", "敵軍")    # 一次性傷害打的一定是對手；「目標…對周圍的其他友軍造成」是從目標那邊說的
        if label == "敵軍" and self.is_active_dmg_segment(pos) and self.area_scope():
            return ("單個敵軍" if self.area_scope() == "單體" else "範圍敵軍"), "area"
        if label:
            return label, src
        if eff["polarity"] == "debuff":
            if self.is_active_dmg_segment(pos) and self.area_scope():
                return ("單個敵軍" if self.area_scope() == "單體" else "範圍敵軍"), "area"
            return "敵軍", "default"
        if eff["type"] in ("再動", "強化回合不減"):
            return "自身", "default"             # 行動相關的是施放者自己（「使用後可以再行動」）
        if rec["kind"] == "技能" and self.seg_of(pos) == "主動" and rec.get("category") not in DMG_CATS:
            if rec.get("range") == "自身":
                return "自身", "area"
            if rec.get("area"):
                return ("單個友軍" if rec["area"] == "單體" else "範圍友軍"), "area"
        return "自身", "default"

    # ── 不可驅散／無法免疫 ──
    def attach_notes(self):
        t = self.t
        taken = []
        notes = []
        for rx, fields in ((NOTE_BOTH, ("dispellable", "immunable")), (NOTE_DISP, ("dispellable",)), (NOTE_IMMU, ("immunable",))):
            for m in rx.finditer(t):
                if any(a < m.end() and m.start() < b for a, b in taken):
                    continue
                taken.append((m.start(), m.end()))
                notes.append((m, fields))
        for eff in self.effects:
            eff["dispellable"] = None
            eff["immunable"] = None
        for m, fields in sorted(notes, key=lambda n: n[0].start()):
            s0, e0 = self.scope_of(m.start())
            if t[m.end():m.end() + 1] == "的":            # 「無法免疫的[固定傷害]」「不可驅散的強力弱化效果」只管後面那一個
                targets = [x for x in self.effects if m.end() <= x["_s"] <= m.end() + 14][:1]
            elif NOTE_ALL.search(t[max(0, m.start() - 16):m.start()]):
                targets = [x for x in self.effects if x["type"] not in NON_STATUS or self.inq[x["_s"]]]
            else:
                targets = [x for x in self.effects if s0 <= x["_s"] < m.start() and (x["type"] not in NON_STATUS or self.inq[x["_s"]])]
            for x in targets:
                for f in fields:
                    if x[f] is None:
                        x[f] = False
                        x["_raw_of"][f] = (m.start(), m.end())

    # ── 輸出 ──
    def finish(self):
        rec = self.rec
        effects = []
        for x in self.effects:
            raw_of = {}
            for k, v in x["_raw_of"].items():
                vs = v if isinstance(v, list) else [v]
                texts = [self.raw(a, b) for a, b in vs]
                raw_of[k] = texts if isinstance(v, list) else texts[0]
            self.claimed.append((x["_s"], x["_e"]))    # 只有效果本身算覆蓋；回合數、註記這些附屬片段不算
            out = {"polarity": x["polarity"], "type": x["type"], "stat": x["stat"], "value": x["value"], "unit": x["unit"],
                   "base": x["base"], "duration": x["duration"], "permanent": x["permanent"],
                   "stack_max": x.get("stack_max"), "cap": x.get("cap")}
            if x.get("cap") is not None:
                out["cap_unit"] = x["cap_unit"]
            out.update({"per": x.get("per"), "dispellable": x["dispellable"], "immunable": x["immunable"],
                        "timing": x["timing"], "target": x["target"], "target_from": x["target_from"],
                        "condition": x["condition"], "chance": x["chance"], "segment": x["segment"],
                        "raw": self.raw(x["_s"], x["_e"]), "raw_of": raw_of})
            effects.append(out)
        unparsed, total, covered = [], 0, 0
        for a, b in self.fines:
            piece = self.raw(a, b).strip()
            body = SEG_TAG.sub("", norm(piece))
            if len(re.sub(r"[\s，。；:()\"'\[\]、]", "", body)) < 4:
                continue
            total += 1
            if any(s < b and a < e for s, e in self.claimed):
                covered += 1
            else:
                unparsed.append(piece)
        rec["damage"] = self.damage
        rec["effects"] = effects
        rec["unparsed"] = unparsed
        rec["_sentences"] = (total, covered)
        return rec


def parse(rec):
    return Parser(rec).run()


def build_records():
    heroes = hero_files()
    records = skill_records() + talent_records(heroes) + rune_records(heroes) + gear_records() + soldier_records()
    ids = collections.Counter(r["id"] for r in records)
    dup = [i for i, n in ids.items() if n > 1]
    if dup:
        raise SystemExit(f"id 重複：{dup}")
    return [parse(r) for r in records]


def coverage(records):
    total = sum(r["_sentences"][0] for r in records)
    covered = sum(r["_sentences"][1] for r in records)
    by_kind = {}
    for kind in KINDS:
        part = [r for r in records if r["kind"] == kind]
        t = sum(r["_sentences"][0] for r in part)
        c = sum(r["_sentences"][1] for r in part)
        by_kind[kind] = {"筆數": len(part), "ingame": sum(1 for r in part if r["text_from"] == "ingame"),
                         "wiki": sum(1 for r in part if r["text_from"] == "wiki"),
                         "有 unparsed 的筆數": sum(1 for r in part if r["unparsed"]),
                         "句子": t, "解析到的句子": c, "句子覆蓋率": round(100.0 * c / t, 1) if t else None}
    types = collections.Counter((e["polarity"], e["type"]) for r in records for e in r["effects"])
    return {
        "筆數": len(records),
        "有 unparsed 的筆數": sum(1 for r in records if r["unparsed"]),
        "句子": total, "解析到的句子": covered, "句子覆蓋率": round(100.0 * covered / total, 1) if total else None,
        "句子的定義": "以。；切開（括號開頭的、「該效果無法被驅散」「持續N回合」這類註記句併回前一句），去掉標點後至少 4 個字；"
                     "有任何效果本身、傷害倍率或專屬裝備能力加成的原文片段落在句子裡就算解析到（回合數、註記這些附屬片段不算）",
        "各來源": by_kind,
        "傷害倍率筆數": sum(len(r["damage"]) for r in records),
        "各類型筆數": {f"{t}（{p}）": n for (p, t), n in sorted(types.items(), key=lambda x: (x[0][0], -x[1]))},
    }


def main():
    records = build_records()
    cov = coverage(records)
    for r in records:
        del r["_sentences"]
    dump("effects.json", {"_meta": dict(GENERATED, coverage=cov), "records": records})
    print(f"效果欄位：{cov['筆數']} 筆，句子覆蓋率 {cov['句子覆蓋率']}%（{cov['解析到的句子']}/{cov['句子']}），"
          f"有 unparsed 的 {cov['有 unparsed 的筆數']} 筆，傷害倍率 {cov['傷害倍率筆數']} 個")
    for kind, c in cov["各來源"].items():
        print(f"  {kind} {c['筆數']} 筆（ingame {c['ingame']}、wiki {c['wiki']}）句子覆蓋率 {c['句子覆蓋率']}%，有 unparsed 的 {c['有 unparsed 的筆數']}")
    print("  各類型：" + "、".join(f"{k} {v}" for k, v in cov["各類型筆數"].items()))


if __name__ == "__main__":
    main()
