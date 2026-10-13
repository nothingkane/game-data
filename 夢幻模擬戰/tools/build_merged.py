# -*- coding: utf-8 -*-
"""
夢幻模擬戰：把兩個來源併成合併檢視，並比出兩邊內容哪裡不一樣（離線，只用標準函式庫）

用法: python 夢幻模擬戰/tools/build_merged.py
前置條件: sources/ingame/（遊戲畫面拍圖解析）與 sources/wiki/data/（Biligame Wiki 爬的）都在；
          兩邊名字不同的英雄與技能記在 aliases.json。
預期結果: merged/heroes/<名字>.json 每隻一份、merged/index.json 英雄總表、merged/skills.json 技能一顆一筆、
          merged/exclusive_gear.json 專屬裝備一件一筆、merged/diff-report.md 兩邊內容哪裡不一樣；印出各來源的筆數。
          merged/ 整個是產物，重跑會整個重寫，不要手改——要改去改來源。

合併規則:
- 名字以遊戲畫面為準（aliases.json）；只有 wiki 有的用 wiki 的名字。
- 兩邊都有的欄位用遊戲畫面的（天賦、鑄紋技能、專屬裝備），wiki 的版本留在 wiki_check 供對照。
- 只有 wiki 有的欄位（陣營、職業、士兵、羈絆、生平）由 wiki 補。
- 每個欄位的來源寫在 _from。
- 技能照名字對（名字不同的記在 aliases.json 的 skills）；專屬裝備照主人對（一隻英雄只有一件），
  名字不同的自動記成 wiki_name。
- 內容比對：先去掉標點與空白。「相同」「只差數字」（把數字遮掉之後相同，多半是改過數值）「文字不同」。
"""
import difflib
import glob
import json
import os
import re
import shutil

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INGAME = os.path.join(BASE, "sources", "ingame")
WIKI = os.path.join(BASE, "sources", "wiki", "data")
OUT = os.path.join(BASE, "merged")

WIKI_LABEL = "wiki 2026-06-20"
GENERATED = {"note": "build_merged.py 產生，不要手改"}
# 遊戲畫面的欄位：遊戲本身的資料
INGAME_FACTS = ["unit_type", "keywords", "name_color", "gender", "cost_cap", "talent", "skills", "transformed_skills", "rune_skill"]
# 遊戲畫面的欄位：學長帳號當時的養成狀態
INGAME_ACCOUNT = ["stars", "level", "power", "stats"]
# 只有 wiki 有的欄位
WIKI_ONLY = ["faction", "origin", "cv", "height", "weight", "biography", "classes", "soldiers", "soldierTraining",
             "bondConditions", "bondHelpers", "heartBonds"]
# 兩邊都有、wiki 版留著對照的欄位（wiki 的欄位名 → 對照區的欄位名）
WIKI_CHECK = {"talents": "talents", "enchantSkill": "rune_skill", "exclusiveEquipment": "exclusive_gear"}

PUNCT = re.compile("[\\s“”\"「」『』\\[\\]【】（）()，,。.:：；;、·‘’'！!]")
# 專屬裝備開頭那句能力加成：商店是 Lv.1、wiki 是滿級，不比
GEAR_STAT_PREFIX = re.compile(r"^(生命|攻擊|智力|防禦|魔防|技巧)+\+\d+%")
# wiki 簡轉繁時被 OpenCC 換成台灣電腦用語的詞，比之前換回來（左邊 wiki、右邊遊戲的寫法）
WIKI_FOLD = {"記憶體": "內存", "重新整理": "刷新"}
KINDS = ["天賦", "鑄紋技能", "專屬裝備", "技能"]


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump(name, data):
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def norm(text):
    text = PUNCT.sub("", text or "")
    for wiki_word, game_word in WIKI_FOLD.items():
        text = text.replace(wiki_word, game_word)
    return text


def number_diff(a, b):
    """a 把數字遮掉後出現在 b 裡：回傳 b 裡最接近的那一版跟 a 差在哪幾個數字，[(遊戲的, wiki 的), ...]。"""
    pattern = re.compile(r"(\d+)".join(re.escape(part) for part in re.split(r"\d+", a)))
    mine = re.findall(r"\d+", a)
    versions = [[(x, y) for x, y in zip(mine, m.groups()) if x != y] for m in pattern.finditer(b)]
    return min(reversed(versions), key=len) if versions else []   # 一樣接近時取後面那一版（星數高的）


def compare(game_text, wiki_text, contains=False):
    """回傳 (結果, 相似度或差在哪幾個數字)。contains=True 用在 wiki 那段比較長的時候（例：天賦把每個星數的版本接在一起），
    遊戲的出現在裡面就算相同。"""
    a, b = norm(game_text), norm(wiki_text)
    if not a or not b:
        return None, None
    if a == b or (contains and a in b):
        return "相同", 1.0
    masked_a, masked_b = re.sub(r"\d+", "#", a), re.sub(r"\d+", "#", b)
    if masked_a == masked_b or (contains and masked_a in masked_b):
        return "只差數字", number_diff(a, b)
    matcher = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if contains:
        return "文字不同", round(sum(m.size for m in matcher.get_matching_blocks()) / len(a), 2)
    return "文字不同", round(matcher.ratio(), 2)


def tally(rows):
    out = {}
    for row in rows:
        out[row["compare"]] = out.get(row["compare"], 0) + 1
    return out


def merge(name, game, wiki, gear, gear_label, wiki_skills):
    """一隻英雄的合併。game、wiki、gear 任一個可以是 None。"""
    out = {"name": name, "sources": [], "_from": {}}

    def put(key, value, label):
        if value in (None, "", [], {}):
            return
        out[key] = value
        out["_from"][key] = label

    if game:
        label = f"ingame {game['_meta']['captured']}"
        out["sources"].append("ingame")
        put("rarity", game.get("rarity"), label)
        for key in INGAME_FACTS:
            put(key, game.get(key), label)
        put("exclusive_gear", gear or game.get("exclusive_gear"), label)
        put("account", {k: game[k] for k in INGAME_ACCOUNT if k in game}, label)
        put("analysis", game.get("analysis"), label + "（CanL 的判讀，不是遊戲寫的）")
        out["ingame_meta"] = game["_meta"]
    if wiki:
        out["sources"].append("wiki")
        if wiki["name"] != name:
            out["wiki_name"] = wiki["name"]
        if "rarity" not in out:
            put("rarity", wiki.get("rarity"), WIKI_LABEL)
        for key in WIKI_ONLY:
            put(key, wiki.get(key), WIKI_LABEL)
        check = {dst: wiki[src] for src, dst in WIKI_CHECK.items() if wiki.get(src)}
        if game:
            if wiki_skills:
                check["skills"] = [s["name"] for s in wiki_skills]    # wiki 英雄頁「習得技能」列的，只留名字
            put("wiki_check", check, WIKI_LABEL)
        else:
            put("skills", [{k: v for k, v in s.items() if k not in ("heroes", "heroCount")} for s in wiki_skills], WIKI_LABEL)
            # 沒有遊戲畫面的版本，wiki 的就是唯一一份
            put("talents", check.get("talents"), WIKI_LABEL)
            put("rune_skill", check.get("rune_skill"), WIKI_LABEL)
            if gear:
                # 英雄檔還沒讀，但秘境商店拍到了他的專屬裝備
                out["sources"].insert(0, "ingame(gear)")
                put("exclusive_gear", gear, gear_label)
                put("wiki_check", {"exclusive_gear": check.get("exclusive_gear")}, WIKI_LABEL)
            else:
                put("exclusive_gear", check.get("exclusive_gear"), WIKI_LABEL)
    return out


def build_heroes(games, wikis, gear_file, to_wiki):
    skills_of = {}      # wiki 的英雄名 → 他英雄頁上列的技能
    for skill in load(os.path.join(WIKI, "skills.json")):
        for hero in skill.get("heroes", []):
            skills_of.setdefault(hero, []).append(skill)
    unknown = sorted(set(skills_of) - set(wikis))
    if unknown:
        raise SystemExit(f"skills.json 的 heroes 有 heroes.json 沒有的名字：{unknown}")
    gears = {g["owner"]: g for g in gear_file["items"]}
    gear_label = f"ingame {gear_file['_meta']['captured']}"
    to_ingame = {v: k for k, v in to_wiki.items()}

    merged, used_wiki = [], set()
    for name, game in sorted(games.items()):
        wiki_name = to_wiki.get(name, name)
        wiki = wikis.get(wiki_name)
        if wiki:
            used_wiki.add(wiki_name)
        merged.append(merge(name, game, wiki, gears.get(name), gear_label, skills_of.get(wiki_name, [])))
    for name, wiki in sorted(wikis.items()):
        if name not in used_wiki:
            ingame_name = to_ingame.get(name, name)
            merged.append(merge(ingame_name, None, wiki, gears.get(ingame_name), gear_label, skills_of.get(name, [])))

    for hero in merged:
        dump(os.path.join("heroes", hero["name"] + ".json"), hero)

    both = [h["name"] for h in merged if h["sources"] == ["ingame", "wiki"]]
    only_game = [h["name"] for h in merged if h["sources"] == ["ingame"]]
    only_wiki = [h["name"] for h in merged if h["sources"] == ["wiki"]]
    gear_only = [h["name"] for h in merged if h["sources"] == ["ingame(gear)", "wiki"]]
    gear_unmatched = sorted(set(gears) - {h["name"] for h in merged})
    dump("index.json", {
        "_meta": dict(GENERATED, counts={
            "合計": len(merged), "兩邊都有": len(both), "只有遊戲畫面": len(only_game), "只有 wiki": len(only_wiki),
            "wiki 加遊戲畫面的專屬裝備": len(gear_only)}),
        "only_ingame": only_game,
        "exclusive_gear_owner_unmatched": gear_unmatched,
        "heroes": [{"name": h["name"], "rarity": h.get("rarity"), "sources": h["sources"],
                    **({"wiki_name": h["wiki_name"]} if "wiki_name" in h else {})} for h in merged],
    })
    print(f"英雄：遊戲畫面 {len(games)} 隻、wiki {len(wikis)} 隻 → 合併 {len(merged)} 隻")
    print(f"  兩邊都有 {len(both)}（其中靠對照表的 {sum(1 for h in merged if 'wiki_name' in h and 'ingame' in h['sources'])}）")
    print(f"  只有遊戲畫面 {len(only_game)}：{'、'.join(only_game)}")
    print(f"  只有 wiki {len(only_wiki)}")
    print(f"  wiki 的英雄資料加上遊戲畫面拍到的專屬裝備 {len(gear_only)}：{'、'.join(gear_only)}")
    no_skill = [h["name"] for h in merged if "ingame" not in h["sources"] and "skills" not in h]
    print(f"  沒有遊戲畫面英雄檔的 {len(only_wiki) + len(gear_only)} 隻裡，wiki 也沒列技能的 {len(no_skill)}：{'、'.join(no_skill)}")
    print(f"  專屬裝備的主人兩邊都找不到的 {len(gear_unmatched)}：{'、'.join(gear_unmatched)}")
    return merged


def build_skills(games, aliases):
    """技能一顆一筆：遊戲畫面的照名字收攏（誰有這顆），wiki 的照名字或對照表接上。"""
    to_wiki = {a["ingame"]: a["wiki"] for a in aliases.get("skills", [])}
    wiki = {s["name"]: s for s in load(os.path.join(WIKI, "skills.json"))}

    ingame = {}
    for hero in games.values():
        for skill in hero["skills"]:
            entry = ingame.setdefault(skill["name"], {"heroes": [], "variants": []})
            entry["heroes"].append(hero["name"])
            facts = {k: skill.get(k) for k in ("cost", "category", "cooldown", "range", "area", "text")}
            if facts not in entry["variants"]:
                entry["variants"].append(facts)
    bad = [a for a in aliases.get("skills", []) if a["ingame"] not in ingame or a["wiki"] not in wiki]
    if bad:
        raise SystemExit(f"aliases.json 的 skills 有對不到來源的名字：{bad}")

    rows, used = [], set()
    for name, entry in sorted(ingame.items()):
        row = {"name": name, "sources": ["ingame"], "heroes": sorted(entry["heroes"]), **entry["variants"][0]}
        if len(entry["variants"]) > 1:
            row["variants"] = entry["variants"]     # 同名但不同英雄身上寫的不一樣
        wiki_name = to_wiki.get(name, name)
        if wiki_name in wiki:
            used.add(wiki_name)
            row["sources"].append("wiki")
            if wiki_name != name:
                row["wiki_name"] = wiki_name
            row["wiki"] = wiki[wiki_name]
            row["compare"], row["similarity"] = compare(row["text"], wiki[wiki_name].get("description"))
        rows.append(row)
    for name, skill in sorted(wiki.items()):
        if name not in used:
            rows.append({"name": name, "sources": ["wiki"], "heroes_wiki": skill.get("heroes", []), "wiki": skill})
    dump("skills.json", {"_meta": GENERATED, "skills": rows})

    both = [r for r in rows if len(r["sources"]) == 2]
    print(f"技能：遊戲畫面 {len(ingame)} 顆、wiki {len(wiki)} 顆 → 合併 {len(rows)} 筆")
    print(f"  兩邊都有 {len(both)}（其中靠對照表的 {sum(1 for r in rows if 'wiki_name' in r)}）{tally(both)}")
    print(f"  只有遊戲畫面 {sum(1 for r in rows if r['sources'] == ['ingame'])}、只有 wiki {sum(1 for r in rows if r['sources'] == ['wiki'])}")
    return rows


def build_gear(gear_file, hero_to_wiki, wiki_heroes):
    """專屬裝備一件一筆，照主人對：先找 wiki 裝備表，沒有再找 wiki 英雄頁上那一段。"""
    table = {e["exclusiveHero"]: e for e in load(os.path.join(WIKI, "equipment.json")) if e.get("exclusiveHero")}
    rows = []
    for item in gear_file["items"]:
        row = dict(item, sources=["ingame"])
        rows.append(row)
        owner = hero_to_wiki.get(item["owner"], item["owner"])
        page = (wiki_heroes.get(owner) or {}).get("exclusiveEquipment") or {}
        text = GEAR_STAT_PREFIX.sub("", norm(item["skill"]["text"]))
        if owner in table:
            wiki, row["wiki_from"] = table[owner], "裝備表"
            result = compare(text, GEAR_STAT_PREFIX.sub("", norm(wiki.get("effect"))))
        elif page.get("rawText") and page.get("name") != "暫無":
            wiki, row["wiki_from"] = page, "英雄頁"
            result = compare(text, page["rawText"], contains=True)
        else:
            continue
        row["sources"].append("wiki")
        row["wiki"] = wiki
        row["compare"], row["similarity"] = result
        if wiki["name"] != item["name"]:
            row["wiki_name"] = wiki["name"]
    dump("exclusive_gear.json", {"_meta": GENERATED, "items": rows})

    both = [r for r in rows if len(r["sources"]) == 2]
    missing = [r["name"] for r in rows if len(r["sources"]) == 1]
    print(f"專屬裝備：遊戲畫面 {len(rows)} 件")
    print(f"  wiki 找得到 {len(both)}（其中名字不同的 {sum(1 for r in rows if 'wiki_name' in r)}）{tally(both)}")
    print(f"  wiki 沒有 {len(missing)}：{'、'.join(missing)}")
    return rows


def hero_diffs(merged):
    """兩邊都有的英雄，逐隻比天賦與鑄紋技能。"""
    rows = []
    for hero in merged:
        check = hero.get("wiki_check") or {}
        if "talent" in hero and check.get("talents"):
            same_name = [t for t in check["talents"] if t.get("name") == hero["talent"].get("name")]
            wiki_text = "".join(t.get("description", "") for t in (same_name or check["talents"]))
            result, sim = compare(hero["talent"].get("text"), wiki_text, contains=True)
            rows.append({"kind": "天賦", "hero": hero["name"], "name": hero["talent"].get("name"), "compare": result,
                         "similarity": sim, "ingame": hero["talent"].get("text"), "wiki": wiki_text})
        rune = hero.get("rune_skill") or {}
        wiki_rune = check.get("rune_skill") or {}
        if rune.get("text") and wiki_rune.get("description"):
            result, sim = compare(rune["text"], wiki_rune["description"])
            rows.append({"kind": "鑄紋技能", "hero": hero["name"], "name": rune.get("name"), "compare": result,
                         "similarity": sim, "ingame": rune["text"], "wiki": wiki_rune["description"]})
    rows = [r for r in rows if r["compare"]]
    for kind in ("天賦", "鑄紋技能"):
        part = [r for r in rows if r["kind"] == kind]
        print(f"{kind}：兩邊都有 {len(part)} {tally(part)}")
    return rows


def write_report(diffs, skills, gear_items):
    """merged/diff-report.md：只列內容不一樣的，每一類裡數字不同的排前面。"""
    rows = list(diffs)
    rows += [{"kind": "技能", "hero": "、".join(s["heroes"][:3]), "name": s["name"], "compare": s["compare"],
              "similarity": s["similarity"], "ingame": s["text"], "wiki": s["wiki"].get("description")}
             for s in skills if s.get("compare")]
    rows += [{"kind": "專屬裝備", "hero": g["owner"], "name": g["name"], "compare": g["compare"],
              "similarity": g["similarity"], "ingame": g["skill"]["text"],
              "wiki": g["wiki"].get("effect") or g["wiki"].get("rawText")}
             for g in gear_items if g.get("compare")]
    lines = ["# 兩個來源的內容差異", "",
             "`build_merged.py` 產生，不要手改。遊戲畫面是 2026-10 拍的，wiki 是 2026-06-20 爬的（簡轉繁）。", "",
             "- 比之前先去掉標點與空白。",
             "- **只差數字**：把數字遮掉之後一樣，標題列出差在哪幾個數字（wiki 有好幾版時取最接近的那一版）。"
             "可能是這四個月改過數值、wiki 寫的是別的等級，也可能是抄錯，要回原圖才分得出來。",
             "- **文字不同**：後面的相似度越接近 1 越像簡轉繁的用字差異，越低越像整段改寫。",
             "- 天賦在 wiki 是把每個星數的版本接在一起，遊戲畫面那一版出現在裡面就算相同。",
             "- 專屬裝備開頭那句能力加成（商店是 Lv.1、wiki 是滿級）不比。", "",
             "| 類別 | 兩邊都有 | 相同 | 只差數字 | 文字不同 |", "|---|---|---|---|---|"]
    for kind in KINDS:
        count = tally([r for r in rows if r["kind"] == kind])
        lines.append(f"| {kind} | {sum(count.values())} | {count.get('相同', 0)} | {count.get('只差數字', 0)} | {count.get('文字不同', 0)} |")
    for kind in KINDS:
        for result in ("只差數字", "文字不同"):
            part = sorted((r for r in rows if r["kind"] == kind and r["compare"] == result), key=lambda r: str(r["similarity"]))
            if not part:
                continue
            lines += ["", f"## {kind}：{result}（{len(part)}）", ""]
            for r in part:
                if result == "只差數字":
                    sim = "（遊戲 → wiki：" + "、".join(f"{x} → {y}" for x, y in r["similarity"]) + "）"
                else:
                    sim = f"（相似度 {r['similarity']}）"
                lines += [f"### {r['name']}｜{r['hero']}{sim}", "", f"- 遊戲：{r['ingame']}", f"- wiki：{r['wiki']}", ""]
    with open(os.path.join(OUT, "diff-report.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def main():
    aliases = load(os.path.join(BASE, "aliases.json"))
    to_wiki = {a["ingame"]: a["wiki"] for a in aliases["heroes"]}

    games = {}
    for path in glob.glob(os.path.join(INGAME, "heroes", "*.json")):
        hero = load(path)
        games[hero["name"]] = hero
    wikis = {h["name"]: h for h in load(os.path.join(WIKI, "heroes.json"))}
    gear_file = load(os.path.join(INGAME, "exclusive_gear.json"))

    owners = {g["owner"] for g in gear_file["items"]}
    bad_alias = [a for a in aliases["heroes"]
                 if (a["ingame"] not in games and a["ingame"] not in owners) or a["wiki"] not in wikis]
    if bad_alias:
        raise SystemExit(f"aliases.json 的 heroes 有對不到來源的名字：{bad_alias}")

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "heroes"))
    merged = build_heroes(games, wikis, gear_file, to_wiki)
    skills = build_skills(games, aliases)
    gear_items = build_gear(gear_file, to_wiki, wikis)
    write_report(hero_diffs(merged), skills, gear_items)


if __name__ == "__main__":
    main()
