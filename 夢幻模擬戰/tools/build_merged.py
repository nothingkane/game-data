# -*- coding: utf-8 -*-
"""
夢幻模擬戰：把兩個來源併成一隻英雄一份的合併檢視（離線，只用標準函式庫）

用法: python 夢幻模擬戰/tools/build_merged.py
前置條件: sources/ingame/（遊戲畫面拍圖解析）與 sources/wiki/data/（Biligame Wiki 爬的）都在；
          兩邊名字不同的英雄記在 aliases.json。
預期結果: merged/heroes/<名字>.json 每隻一份、merged/index.json 一份總表；印出各來源的筆數與對不上的名字。
          merged/ 整個是產物，重跑會整個重寫，不要手改——要改去改來源。

合併規則:
- 名字以遊戲畫面為準（aliases.json）；只有 wiki 有的英雄用 wiki 的名字。
- 兩邊都有的欄位用遊戲畫面的（天賦、鑄紋技能、專屬裝備），wiki 的版本留在 wiki_check 供對照。
- 只有 wiki 有的欄位（陣營、職業、士兵、羈絆、生平）由 wiki 補。
- 每個欄位的來源寫在 _from。
"""
import glob
import json
import os
import shutil

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INGAME = os.path.join(BASE, "sources", "ingame")
WIKI = os.path.join(BASE, "sources", "wiki", "data")
OUT = os.path.join(BASE, "merged")

WIKI_LABEL = "wiki 2026-06-20"
# 遊戲畫面的欄位：遊戲本身的資料
INGAME_FACTS = ["unit_type", "keywords", "name_color", "gender", "cost_cap", "talent", "skills", "transformed_skills", "rune_skill"]
# 遊戲畫面的欄位：學長帳號當時的養成狀態
INGAME_ACCOUNT = ["stars", "level", "power", "stats"]
# 只有 wiki 有的欄位
WIKI_ONLY = ["faction", "origin", "cv", "height", "weight", "biography", "classes", "soldiers", "soldierTraining",
             "bondConditions", "bondHelpers", "heartBonds"]
# 兩邊都有、wiki 版留著對照的欄位（wiki 的欄位名 → 對照區的欄位名）
WIKI_CHECK = {"talents": "talents", "enchantSkill": "rune_skill", "exclusiveEquipment": "exclusive_gear"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def merge(name, game, wiki, gear, gear_label):
    """game、wiki、gear 任一個可以是 None；回傳合併後的一份。"""
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
            put("wiki_check", check, WIKI_LABEL)
        else:
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


def main():
    aliases = load(os.path.join(BASE, "aliases.json"))
    to_wiki = {a["ingame"]: a["wiki"] for a in aliases["heroes"]}

    games = {}
    for path in glob.glob(os.path.join(INGAME, "heroes", "*.json")):
        hero = load(path)
        games[hero["name"]] = hero
    wikis = {h["name"]: h for h in load(os.path.join(WIKI, "heroes.json"))}
    gear_file = load(os.path.join(INGAME, "exclusive_gear.json"))
    gears = {g["owner"]: g for g in gear_file["items"]}

    gear_label = f"ingame {gear_file['_meta']['captured']}"
    to_ingame = {v: k for k, v in to_wiki.items()}
    bad_alias = [a for a in aliases["heroes"]
                 if (a["ingame"] not in games and a["ingame"] not in gears) or a["wiki"] not in wikis]
    if bad_alias:
        raise SystemExit(f"aliases.json 有對不到來源的名字：{bad_alias}")

    merged, used_wiki = [], set()
    for name, game in sorted(games.items()):
        wiki_name = to_wiki.get(name, name)
        wiki = wikis.get(wiki_name)
        if wiki:
            used_wiki.add(wiki_name)
        merged.append(merge(name, game, wiki, gears.get(name), gear_label))
    for name, wiki in sorted(wikis.items()):
        if name not in used_wiki:
            ingame_name = to_ingame.get(name, name)
            merged.append(merge(ingame_name, None, wiki, gears.get(ingame_name), gear_label))

    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(os.path.join(OUT, "heroes"))
    for hero in merged:
        with open(os.path.join(OUT, "heroes", hero["name"] + ".json"), "w", encoding="utf-8") as f:
            json.dump(hero, f, ensure_ascii=False, indent=1)

    both = [h["name"] for h in merged if h["sources"] == ["ingame", "wiki"]]
    only_game = [h["name"] for h in merged if h["sources"] == ["ingame"]]
    only_wiki = [h["name"] for h in merged if h["sources"] == ["wiki"]]
    gear_only = [h["name"] for h in merged if h["sources"] == ["ingame(gear)", "wiki"]]
    gear_no_file = sorted(set(gears) - {h["name"] for h in merged})
    index = {
        "_meta": {"note": "build_merged.py 產生，不要手改", "counts": {
            "合計": len(merged), "兩邊都有": len(both), "只有遊戲畫面": len(only_game), "只有 wiki": len(only_wiki),
            "wiki 加遊戲畫面的專屬裝備": len(gear_only)}},
        "only_ingame": only_game,
        "exclusive_gear_owner_unmatched": gear_no_file,
        "heroes": [{"name": h["name"], "rarity": h.get("rarity"), "sources": h["sources"],
                    **({"wiki_name": h["wiki_name"]} if "wiki_name" in h else {})} for h in merged],
    }
    with open(os.path.join(OUT, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)

    print(f"遊戲畫面 {len(games)} 隻、wiki {len(wikis)} 隻 → 合併 {len(merged)} 隻")
    print(f"  兩邊都有 {len(both)}（其中靠對照表的 {sum(1 for h in merged if 'wiki_name' in h)}）")
    print(f"  只有遊戲畫面 {len(only_game)}：{'、'.join(only_game)}")
    print(f"  只有 wiki {len(only_wiki)}")
    print(f"  wiki 的英雄資料加上遊戲畫面拍到的專屬裝備 {len(gear_only)}：{'、'.join(gear_only)}")
    print(f"  專屬裝備的主人兩邊都找不到的 {len(gear_no_file)}：{'、'.join(gear_no_file)}")


if __name__ == "__main__":
    main()
