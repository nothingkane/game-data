# 夢幻模擬戰（Langrisser Mobile）

## 遊戲簡介

夢幻模擬戰是由紫龍遊戲（Zlongame）開發的策略 RPG 手遊，基於經典 Langrisser 系列。玩家收集英雄、組建隊伍，在回合制戰場上進行戰鬥。

## 資料夾怎麼看（2026-10-13 整併）

兩個來源各放各的、原樣保存，另外由程式併出一份合併檢視。

| 位置 | 內容 | 能不能手改 |
|------|------|-----------|
| `sources/ingame/` | 遊戲畫面拍圖解析（2026-10-11～12，繁中版 PC 端）：`heroes/` 英雄 214 份（LLR 6、SP 24、SSR 184）、`exclusive_gear.json` 專屬裝備 164 件、`rune_skills.json` 鑄紋技能、`roster_llr_sp.json` | 由 qa-automation repo 的工具讀寫（`games/langrisser/tools/hero_build.py`、`hero_fill.py`、`gear_fill.py`、`rune_fill.py`） |
| `sources/wiki/` | 2026-06-20 爬的 Biligame Wiki：`data/` 英雄 263、技能 786、裝備 490、士兵 165、鑄紋 161、戰鬥公式；`data/skills-transformed-2026-10-12.json` 是 10/12 補爬的 9 顆替換技能；`raw/` 原始網頁（不進版控）；`cache-manifest.json` | 由 `_shared/scraper/` 的解析器產生 |
| `aliases.json` | 兩邊名字不同的對照，以遊戲畫面的名字為準：英雄 19 對（每一對附對過的證據）、技能 22 對（全文相似度 0.8 以上） | 英雄手改；技能跑 `tools/suggest_skill_aliases.py --write`。改完重跑合併 |
| `merged/` | 合併檢視：`heroes/` 一隻一份 265 份、`index.json` 英雄總表、`skills.json` 技能一顆一筆 916 筆（誰有這顆、兩邊的內容）、`exclusive_gear.json` 專屬裝備 164 件、`diff-report.md` 兩邊內容哪裡不一樣 | **不要手改**，跑 `python 夢幻模擬戰/tools/build_merged.py` 重產 |
| `merged/effects.json` | 技能文字拆成的效果欄位：一段文字一筆 1,587 筆（技能 918、天賦 214、鑄紋技能 137、專屬裝備 164、士兵 154），每筆有傷害倍率 `damage`、強化弱化 `effects`、沒解析到的句子 `unparsed`；覆蓋率在 `_meta.coverage`。欄位定義見 `docs/ADR-002-effect-fields.md` | **不要手改**，`build_merged.py` 跑完會接著跑 `tools/parse_effects.py`；只改了解析規則時可以單獨跑它，改完跑 `tools/test_parse_effects.py`（人工對照組 `tools/effects_golden.json`）|
| `docs/` | `heroes-llr-sp.md`、`heroes-ssr.md`（從英雄檔整理的總覽）、`heroes.md`（10/11 的帳號英雄筆記 251 隻，派人抄的、沒逐隻驗過）、ADR、戰鬥公式 | |
| `analysis/` | 拿資料庫做的分析，一次一個目錄。`2026-10-14-技能規則/`：強化弱化目錄（每種屬性開了哪些檔次）、十章統計版報告、腳本與人工判讀紀錄，給 BxB 技能設計用；先看裡面的 `README.md` | 分析產出，可以手改；重跑方式寫在各目錄的 README |

**兩邊誰準**：遊戲畫面是 2026-10 的現況，天賦、技能、鑄紋技能、專屬裝備以它為準；wiki 是四個月前的、簡轉繁有雜訊，拿來補遊戲畫面沒讀的（陣營、職業、士兵、羈絆、生平、SR 與 R），兩邊都有的欄位 wiki 版留在合併檢視的 `wiki_check` 供對照。每個欄位的來源寫在 `_from`。

**兩邊比出來的結果（2026-10-13，細目在 `merged/diff-report.md`）**

| 類別 | 兩邊都有 | 相同 | 只差數字 | 文字不同 |
|---|---|---|---|---|
| 天賦 | 211 | 126 | 47 | 38 |
| 鑄紋技能 | 51 | 45 | 0 | 6 |
| 專屬裝備 | 163 | 150 | 4 | 9 |
| 技能 | 609 | 510 | 0 | 99 |

- 天賦「只差數字」的 47 隻裡，30 隻是遊戲的數字每一個都比 wiki 最接近的那一版大、沒有一隻是每一個都比較小——看起來是 wiki 那份少了最高星數的版本，不是改過數值；沒有逐隻回原圖證實。
- 技能「文字不同」的 99 顆裡 72 顆相似度 0.95 以上，抽看是簡轉繁的用字或一兩個字的差異；相似度低的才是整段改寫或 wiki 多寫了註解。
- 遊戲畫面有、wiki 找不到對應的技能 130 顆；wiki 有、遊戲畫面沒讀到的 177 顆（含還沒讀的 SR 與 R）。
- 沒有遊戲畫面英雄檔的 51 隻（SR 29、R 10、SSR 12）技能清單取自 wiki 英雄頁的「習得技能」（`sources/wiki/data/skills.json` 每顆的 `heroes`，由本機的原始網頁離線解析）。
- 專屬裝備 wiki 沒有的 1 件：新帝國的重刃（蕾貝爾，wiki 寫「暫無」）。

**英雄檔裡混了三種東西**：遊戲本身的資料、學長帳號當時的養成狀態（星數、等級、戰力、能力值、技能的 `equipped`；合併檢視裡收在 `account`）、CanL 從文字推的判讀（`analysis`，沒在戰鬥裡驗過）。

**原始截圖**（約 6 GB）在 qa-automation 的 `runtime/logs/langrisser/`，只在家機，不進版控；英雄檔 `_meta.screenshots` 的路徑是相對於 qa-automation repo 根目錄。

**不要再連 wiki.biligame.com**：2026-10-12 補爬害學長被站方擋，學長同意前不連。

## 效果欄位怎麼查（2026-10-14）

問倍率、強化弱化的數值、冷卻，直接查 `merged/effects.json` 的欄位，不要再對文字下正規表示式（10/14 用文字判單體範圍，把物理範圍最大倍率算成 1.7，查 `area` 其實是 0.6）。在 repo 根目錄跑，`-X utf8` 是讓 Windows 終端機印得出中文：

```bash
# 強化「屬性提升」的最小、最大（單位 %），附技能名與原文；per 不是 None 的是「每 X」的單位增量
python -X utf8 -c "import json;R=json.load(open('夢幻模擬戰/merged/effects.json',encoding='utf-8'))['records'];E=sorted((e['value'],r['name'],e['raw'],e['per']) for r in R for e in r['effects'] if e['type']=='屬性提升' and e['polarity']=='buff' and e['unit']=='%');print(E[0],E[-1])"
# 冷卻 7 回合以上的技能（cooldown_from 是 wiki 的表示遊戲畫面沒讀到冷卻、由 wiki 補）
python -X utf8 -c "import json;R=json.load(open('夢幻模擬戰/merged/effects.json',encoding='utf-8'))['records'];print(sorted((r['cooldown'],r['name']) for r in R if r['kind']=='技能' and (r['cooldown'] or 0)>=7))"
# 物理範圍倍率最高的技能（scope 照技能的 area 欄判，不看文字）
python -X utf8 -c "import json;R=json.load(open('夢幻模擬戰/merged/effects.json',encoding='utf-8'))['records'];print(max((d['multiplier'],r['name'],d['raw']) for r in R for d in r['damage'] if d['dtype']=='物理' and d['scope']=='範圍'))"
```

- 一筆 = 一段技能文字：`id` 是「來源種類:名字」（同名技能在不同英雄身上寫的不一樣時加 `#2`），`kind` 是 技能／天賦／鑄紋技能／專屬裝備／士兵。
- `effects` 的 `type` 與 `polarity`（buff／debuff／neutral）沿用 10/14 研究喵的分類名；neutral 是施放者自己吃的代價或召喚物的屬性定義。
- 沒解析到的句子在每筆的 `unparsed`，全庫句子覆蓋率約 78%（數字在 `_meta.coverage`）。查不到的不代表沒有，要回原文看。
- 解析是規則判的：人工對照組 43 筆逐欄全對，但那是調規則時對著看的；對照組以外抽查，一筆效果每一欄都對的約七到八成，`target`、`condition`、`timing` 最常錯。重要的數字回 `raw` 看原文。

## 資料來源

| 來源 | 用途 | 網址 |
|------|------|------|
| Biligame Wiki（主要） | 完整遊戲資料 | https://wiki.biligame.com/langrisser/ |
| GitHub combat-calculator | JSON schema 參考 | https://github.com/absnormal/langrisser-combat-calculator |

## 資料分類

### 英雄（heroes）

英雄是遊戲核心單位，每個英雄有：

| 欄位 | 說明 |
|------|------|
| name | 英雄名稱（繁中） |
| rarity | 稀有度：N / R / SR / SSR / SP / LLR |
| faction | 所屬陣營（光輝軍團、帝國之輝、黑暗輪迴等） |
| class | 職業樹（多條路線，每條有多階職業） |
| stats | 屬性：HP / ATK / INT / DEF / MDEF / SKILL |
| talent | 天賦（被動特殊能力） |
| skills | 可學習技能列表 |
| soldiers | 可攜帶兵種列表 |
| bonds | 羈絆關係 |

### 裝備（equipment）

| 欄位 | 說明 |
|------|------|
| name | 裝備名稱 |
| type | 類型：武器 / 防具 / 頭盔 / 飾品 / 專屬裝備 |
| rarity | 稀有度 |
| effect | 效果描述 |
| stats | 數值加成 |

### 技能（skills）

| 欄位 | 說明 |
|------|------|
| name | 技能名稱 |
| type | 類型：主動 / 被動 / 輔助 |
| cost | COST 等級（1-3） |
| cd | 冷卻回合數 |
| range | 射程 |
| span | 影響範圍 |
| description | 效果描述 |

### 士兵（soldiers）

| 欄位 | 說明 |
|------|------|
| name | 兵種名稱 |
| type | 兵種類型（步兵 / 騎兵 / 飛兵 / 弓兵 / 法師 / 刺客 / 聖職） |
| stats | 屬性數值 |
| skills | 兵種技能 |

## 資料語言

所有資料以**繁體中文**儲存。原始來源若為簡中，轉換後儲存。
