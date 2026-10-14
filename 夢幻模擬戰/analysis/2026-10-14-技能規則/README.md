# 夢戰技能規則分析（2026-10-14）

學長要設計 BxB 第一批 60 顆技能，先請 CanL 收集、分析夢幻模擬戰的技能規則，特別是強化與弱化。這個目錄存這次分析的產出、腳本與人工判讀紀錄。

## 產出

| 檔案 | 內容 |
|------|------|
| `強化弱化目錄.html` | **學長要的版本**：每種強化、弱化（攻擊、智力、防禦、魔防……拆開）開了哪些檔次，每檔附次數與兩個例子。線上版：https://claude.ai/artifact/DVxfM19brAGGe9dwn7asvu |
| `統計版報告.html` | 第一版的十章統計（分類、冷卻、射程、倍率、觸發時機、疊加規則、驅散、光環、文字模板、對 BxB 的借鏡），加上目錄。學長看完說統計占比不是他要的，線上版已改成只留目錄；這份留作參考 |

學長的原話（2026-10-14 17:32）：要的是「buff 有什麼，有加攻擊、智力、物防、魔防等等，各有幾個檔次的增幅」，「不是統計什麼檔次佔比多少%」。

## 怎麼來的

1. `scripts/build_corpus.py`：五種來源攤平成 1,555 段文字（技能、天賦、鑄紋、專屬裝備、士兵）
2. `scripts/analyze.py`：關鍵字與正規表示式分類統計，產出 `data/stats.json`、`data/tables.md`。分類抽查三輪，每輪每類 20 筆，紀錄在 `data/review_round*.json`、`data/samples_round*.json`；最終誤判率強化 5%、弱化 10%、時機 0/20
3. `scripts/value_ranges.py`、`scripts/extremes.py`：每類的上下限與兩端點名，產出 `data/vr_tables.md`、`data/ex_tables.md`；`data/vr_exclusions.json` 是讀原文後人工排除的 21 筆解析錯誤（每筆附理由）
4. `scripts/catalog.py`：目錄。讀 `merged/effects.json`（ADR-002 的效果欄位），套用 `vr_exclusions.json`，產出 `data/catalog_frag.json`

重跑（在本目錄）：

```
python scripts/build_corpus.py "D:/Work/遊戲資料/夢幻模擬戰" corpus.json
python scripts/analyze.py corpus.json data data/review_round1.json data/review_round2.json data/review_round3.json
python scripts/value_ranges.py corpus.json data/stats.json data/vr_exclusions.json
python scripts/extremes.py corpus.json data/stats.json
python scripts/catalog.py "D:/Work/遊戲資料/夢幻模擬戰/merged/effects.json" data/vr_exclusions.json data/catalog_frag.json
```

`corpus.json`（約 0.7 MB）與逐筆數值紀錄 `vr_events.json`（約 0.9 MB）可以重產，沒有存。

## 已知的錯與更正

- **倍率表的單體與範圍**：第一版用文字判斷，物理範圍最大值錯寫成 1.7、魔法單體最小值錯寫成 0.3。改用 `area` 欄位後是 0.6（閃煌）與 1.1（破滅之矛）
- **屬性降低最大值**：研究版漏抓「降低敵方100%的魔防」這種倒裝寫法（蕾恩·殲滅，只限這一擊），寫成 50%
- **效果欄位的錯**：「攻擊射程+1」被解析成攻擊提升 1%（5 筆）；聚元「士兵生命降低90%」是自身代價卻被判成弱化；12 筆單位被解析成「點」。目錄已排除
- 同名、同屬性效果怎麼疊加，技能文字沒有通則，報告裡的說法是從例外寫法反推的，沒在遊戲裡驗證
- 所有數字都是腳本統計；CanL 沒有通讀技能文字，只抽查兩端與部分原文

## BxB 規則框架草案（還沒跟學長討論，不是定案）

CanL 2026-10-14 從統計版提出的九個決定點。學長當時喊停，先改做目錄，所以下面全部待討論：

- D1 持續回合：強化、弱化預設 2 回合，最長 3；大招型強化 4
- D2 百分比檔位：只用 5 的倍數；小 5%、中 10～15%、大 20%、特 30%；50% 以上只給一次性、有條件的效果
- D3 傷害倍率：單體 1.3～1.8 倍，範圍 0.3～0.6 倍；BxB 威力欄填 13000～18000、3000～6000
- D4 冷卻：2～5 回合，預設 3；治療可 1
- D5 疊加：同名只刷新回合（BxB 現行「新覆舊」）；要疊層須寫明上限，上限 3 或 5
- D6 驅散三層：主動施加的可驅散、天賦被動常駐的不可驅散；一次驅 1～2 個，重型 5 個只驅敵方強化；清己方弱化可全清
- D7 天賦是身份規則、常用行動結束觸發；兵種被動池每種 3 顆、小或中檔
- D8 先補程式：「造成／遭受傷害 %」屬性與「行動結束時」觸發點
- D9 技能說明照夢戰三副骨架（傷害技、輔助技、被動天賦）

下一步建議：拿 `強化弱化目錄.html` 直接討論 BxB 每種屬性開幾檔、開哪幾檔。
