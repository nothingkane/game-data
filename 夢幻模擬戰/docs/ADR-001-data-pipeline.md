# ADR-001：夢幻模擬戰資料整理管線

- **狀態**：已通過
- **日期**：2026-06-20
- **決策者**：學長 + CanL

---

## 背景

需要從夢幻模擬戰（Langrisser Mobile）的 wiki 抓取英雄、裝備、技能、士兵等遊戲資料，結構化為 JSON 存放於本地，供後續遊戲素材整理使用。

### 資料來源偵察結果

| 來源 | 資料量 | 更新狀態 | 可存取 | 備註 |
|------|--------|---------|--------|------|
| Biligame Wiki | 300+ 英雄、數百技能/裝備 | 持續更新 | ❌ HTTP 567 WAF | 最完整的中文來源 |
| GitHub combat-calculator | 80 英雄、96 技能、128 裝備 | 2020/10 停更 | ✅ | JSON schema 可參考 |
| Tier List (GitHub Pages) | 200+ 英雄評級 | 2026/05 | ✅ | 只有評級，無詳細資料 |
| Fandom Wiki / langrisser.wiki | 未知 | 未知 | ❌ 403 | 英文為主 |
| 官方百科 (zlongame) | 未知 | 2019/03 停更 | ✅ | 極度過時 |

**核心問題**：唯一完整且持續更新的來源（Biligame Wiki）有嚴格的 WAF 防護，curl / WebFetch / API 全部回 HTTP 567，只有首頁和裝備圖鑑頁例外。

---

## 決策

### 採用方案 C：混合策略

```
階段 1：Playwright 自動化爬蟲（主攻）
  ↓ 成功 → 全自動批次抓取
  ↓ 失敗（WAF 擋住）
階段 2：退守油猴腳本（Tampermonkey）
  → 學長在瀏覽器手動觸發，批量匯出資料
```

### 資料範圍與優先順序

1. **英雄**（最優先）
2. **裝備**
3. **技能**
4. **士兵/兵種**

### 資料語言

- **繁體中文**
- 原始資料若為簡中，轉譯為繁中後儲存

### 快取與增量更新機制

- 原始網頁存入 `raw/` 目錄（HTML 格式）
- `cache-manifest.json` 記錄每個 URL 的抓取時間、本地路徑
- 增量更新：比對 manifest 時間戳，只抓取過期或新增的頁面
- 快取過期策略：待定（初期手動觸發更新）

### JSON Schema 參考

以 GitHub `absnormal/langrisser-combat-calculator` 的結構為骨架，欄位包含：

**英雄**：名稱、稀有度、陣營、職業樹、屬性（HP/ATK/INT/DEF/MDEF/SKILL）、天賦、可用技能、可用士兵、羈絆

**裝備**：名稱、類型（武器/防具/頭盔/飾品）、稀有度、效果描述、數值條件

**技能**：名稱、類型（主動/被動/輔助）、COST、CD、射程、範圍、效果描述

**士兵**：名稱、兵種類型、屬性、技能

---

## 資料夾結構

```
e:\WorkSpace\遊戲資料\
├── _shared/                     # 跨遊戲共用
│   ├── scraper/                 # 爬蟲腳本
│   └── schemas/                 # 共用 JSON schema
│
├── 夢幻模擬戰/
│   ├── CONTEXT.md               # 遊戲背景、欄位說明
│   ├── raw/                     # 原始網頁快取
│   │   ├── heroes/
│   │   ├── equipment/
│   │   ├── skills/
│   │   └── soldiers/
│   ├── data/                    # 結構化 JSON（最終產物）
│   │   ├── heroes.json
│   │   ├── equipment.json
│   │   ├── skills.json
│   │   └── soldiers.json
│   ├── cache-manifest.json
│   └── docs/
│       └── ADR-001-data-pipeline.md（本文件）
│
├── (未來遊戲)/
```

---

## 執行計畫

### Phase 1：環境與骨架 ✅
- [x] 建立資料夾結構
- [x] 撰寫 ADR-001
- [x] 撰寫 CONTEXT.md

### Phase 2：爬蟲開發 ✅
- [x] 安裝 Playwright + Chromium
- [x] 撰寫 Biligame Wiki 爬蟲腳本
- [x] 測試突破 WAF — headless 被擋，**headless: false（可見瀏覽器）成功突破**
- [ ] ~~若失敗，開發油猴腳本（退守方案）~~ — 不需要

### Phase 3：英雄資料抓取與轉換（進行中）
- [x] 提取英雄清單（263 個）
- [x] 批次下載英雄頁面 → 存 raw/heroes/（196/263 已完成）
- [x] 解析 HTML → 結構化 JSON（parse-heroes.mjs，15-18 欄位，99% 覆蓋率）
- [x] 簡中 → 繁中轉換（OpenCC）
- [ ] 補完剩餘英雄（IP 冷卻後重跑即可）
- [ ] 解析器品質迭代（鑄紋技能名稱分割、職業名稱提取）

### Phase 4：裝備 / 技能 / 士兵
- [ ] 下載裝備圖鑑 / 技能查詢 / 士兵圖鑑頁面
- [ ] 撰寫對應解析器
- [ ] 輸出 equipment.json / skills.json / soldiers.json

### Phase 5：戰鬥公式與機制
- [ ] 從 wiki 抓取「夢戰基礎數據分析」「傷害計算器」頁面
- [ ] 從反編譯原始碼（Langrisser repo）提取 BattleFormula.cs
- [ ] 交叉驗證 wiki 公式 vs 原始碼邏輯
- [ ] 整理為結構化的戰鬥機制文件

---

## 額外資料來源：反編譯客戶端

| 項目 | 說明 |
|------|------|
| 倉庫 | E:\WorkSpace\ReferProject\Langrisser |
| 來源 | github.com/leinlin/Langrisser — dnSpy 反編譯 Unity DLL |
| 版本 | 2018/10 快照（Unity 2017.4.2f2） |
| 價值 | BattleFormula.cs（戰鬥公式）、324 個 ConfigData 類別定義 |
| 計畫 | 未來反編譯最新版 APK 取得 2026 版公式 |

---

## 技術發現

### WAF 突破

Biligame Wiki 的 WAF（HTTP 567）行為：

| 模式 | 結果 |
|------|------|
| curl / WebFetch | ❌ 567 |
| Playwright headless: true | ❌ 567（WAF 偵測無頭瀏覽器） |
| **Playwright headless: false** | **✅ 200** |
| 連續請求 ~120 個後 | ❌ IP 級別封鎖（30-60 分鐘自動解除） |

**最佳策略**：可見瀏覽器模式 + 批次暫停 + 60s 失敗冷卻 + 增量下載（重跑跳過已存在）

---

## 風險

| 風險 | 影響 | 緩解措施 |
|------|------|---------|
| IP 被 ban（已發生） | 暫時無法存取 wiki | 增量下載，30-60 分鐘後重跑 |
| Wiki 頁面結構變動 | 解析器失效 | 模組化解析、版本化 schema |
| 簡繁轉換遺漏遊戲專有名詞 | 資料品質下降 | 建立遊戲術語對照表 |
| 反編譯版本過舊 | 公式可能已更新 | 未來反編譯最新 APK |

---

## 備註

- headless: false 是關鍵突破 — WAF 專門偵測無頭瀏覽器特徵
- 增量下載設計正確 — 被 ban 後重跑不會重複下載
- 反編譯原始碼 + wiki 數據的組合比單一來源更可靠
- 未來新增遊戲時，`_shared/scraper` 的爬蟲框架可複用
