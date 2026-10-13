# -*- coding: utf-8 -*-
"""
夢幻模擬戰：找出兩邊名字不同、內容其實是同一顆的技能，列成 aliases.json 的 skills 候選（離線）

用法: python 夢幻模擬戰/tools/suggest_skill_aliases.py [--write]
前置條件: sources/ingame/heroes/ 與 sources/wiki/data/skills.json 都在。
預期結果: 印出遊戲畫面有、wiki 沒有同名的每一顆技能，跟 wiki 那邊「還沒被同名對走的」技能裡全文最像的是哪一顆、幾分。
          加 --write 才把相似度 SIMILARITY_MIN 以上的寫進 aliases.json 的 skills（整段覆寫）；讀了新英雄之後重跑一次。
"""
import difflib
import glob
import json
import os
import sys

from build_merged import BASE, INGAME, WIKI, load, norm

SIMILARITY_MIN = 0.8   # 2026-10-13 量的：22 對在 0.89 以上，下一名掉到 0.76 而且看內容不是同一顆


def main():
    wiki = {s["name"]: s for s in load(os.path.join(WIKI, "skills.json"))}
    ingame = {}
    for path in glob.glob(os.path.join(INGAME, "heroes", "*.json")):
        for skill in load(path)["skills"]:
            ingame.setdefault(skill["name"], skill)
    wiki_left = {name: norm(s.get("description")) for name, s in wiki.items() if name not in ingame}

    pairs = []
    for name, skill in sorted(ingame.items()):
        if name in wiki:
            continue
        text = norm(skill.get("text"))
        score, best = max((difflib.SequenceMatcher(None, text, t, autojunk=False).ratio(), w) for w, t in wiki_left.items())
        pairs.append({"ingame": name, "wiki": best, "similarity": round(score, 2)})
    pairs.sort(key=lambda p: -p["similarity"])
    for p in pairs:
        print(f"{p['similarity']:.2f}  {p['ingame']}  ↔  {p['wiki']}")
    keep = sorted((p for p in pairs if p["similarity"] >= SIMILARITY_MIN), key=lambda p: p["ingame"])
    print(f"遊戲畫面有、wiki 沒有同名的 {len(pairs)} 顆；相似度 {SIMILARITY_MIN} 以上的 {len(keep)} 對")
    if len({p["wiki"] for p in keep}) != len(keep):
        raise SystemExit("有兩顆遊戲技能對到同一顆 wiki 技能，要人看")

    if "--write" in sys.argv[1:]:
        path = os.path.join(BASE, "aliases.json")
        aliases = load(path)
        aliases["skills"] = keep
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(dump_compact(aliases))
        print(f"已寫進 {os.path.normpath(path)}")


def dump_compact(aliases):
    """一對一行，方便人看與比對差異。"""
    lines = ["{", ' "_meta": ' + json.dumps(aliases["_meta"], ensure_ascii=False, indent=1).replace("\n", "\n ") + ","]
    keys = [k for k in aliases if k != "_meta"]
    for i, key in enumerate(keys):
        value = aliases[key]
        tail = "," if i < len(keys) - 1 else ""
        if value and isinstance(value[0], dict):
            rows = ",\n".join("  " + json.dumps(row, ensure_ascii=False) for row in value)
            lines.append(f' "{key}": [\n{rows}\n ]{tail}')
        else:
            lines.append(f' "{key}": {json.dumps(value, ensure_ascii=False)}{tail}')
    lines.append("}")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
