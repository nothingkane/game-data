# 夢幻模擬戰（Langrisser Mobile）

## 遊戲簡介

夢幻模擬戰是由紫龍遊戲（Zlongame）開發的策略 RPG 手遊，基於經典 Langrisser 系列。玩家收集英雄、組建隊伍，在回合制戰場上進行戰鬥。

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
