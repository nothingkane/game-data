/**
 * 兵種數據表解析器
 *
 * Usage:
 *   node parse-soldier-data.mjs
 *   node parse-soldier-data.mjs --debug
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import * as cheerio from 'cheerio';
import * as OpenCC from 'opencc-js';

const RAW_PATH = join(import.meta.dirname, '../../夢幻模擬戰/raw/soldiers/兵種數據表.html');
const DATA_DIR = join(import.meta.dirname, '../../夢幻模擬戰/data');
const s2t = OpenCC.Converter({ from: 'cn', to: 'twp' });
const toTC = (t) => t ? s2t(t.trim()) : '';

function main() {
  const debug = process.argv.includes('--debug');

  if (!existsSync(RAW_PATH)) {
    console.error('兵種數據表 HTML 不存在，請先執行 node fetch-data-pages.mjs --only soldiers');
    process.exit(1);
  }

  const html = readFileSync(RAW_PATH, 'utf-8');
  const $ = cheerio.load(html);
  const soldiers = [];

  // 表格結構（14 cells）：
  // 0: 名稱+技能+所屬英雄(混合) | 1: empty | 2: 技能描述 | 3: 所屬英雄
  // 4: 類型 | 5: 等級 | 6: 射程 | 7: 移動 | 8: 克制 | 9: 弱點
  // 10: 生命 | 11: 攻擊 | 12: 防禦 | 13: 魔防
  $('.mw-parser-output table').each((_, table) => {
    const headerText = $(table).text();
    if (!headerText.includes('克制') || !headerText.includes('弱点')) return;

    $(table).find('tr').each((_, tr) => {
      const cells = $(tr).find('td');
      if (cells.length < 10) return;

      const cellTexts = cells.map((__, c) => $(c).text().trim()).get();

      // 名稱：cell 0 的第一行
      const cell0Lines = cellTexts[0].split('\n').filter(l => l.trim());
      const name = cell0Lines[0]?.trim();
      if (!name || name.length < 2 || name.length > 15) return;

      // 判斷欄位偏移 — 14 cells 時從 cell 4 開始，否則嘗試自適應
      let offset = 4;
      const validTypes = ['步兵', '枪兵', '骑兵', '飞兵', '水兵', '弓兵', '刺客', '僧侣', '法师', '魔物'];
      // 找到類型欄位的偏移
      for (let i = 0; i < cellTexts.length; i++) {
        if (validTypes.includes(cellTexts[i])) { offset = i; break; }
      }

      const type = cellTexts[offset] || '';
      if (!validTypes.includes(type)) return;

      const levelMap = { '一': 'I', '二': 'II', '三': 'III' };
      const level = levelMap[cellTexts[offset + 1]] || cellTexts[offset + 1] || '';

      const soldier = {
        name: toTC(name),
        type: toTC(type),
        level,
        range: parseInt(cellTexts[offset + 2]) || 1,
        move: parseInt(cellTexts[offset + 3]) || 3,
        advantage: toTC(cellTexts[offset + 4] || ''),
        weakness: toTC(cellTexts[offset + 5] || ''),
        stats: {
          hp: parseInt(cellTexts[offset + 6]) || 0,
          atk: parseInt(cellTexts[offset + 7]) || 0,
          def: parseInt(cellTexts[offset + 8]) || 0,
          mdef: parseInt(cellTexts[offset + 9]) || 0,
        },
      };

      // 技能描述（cell 2）
      const skillDesc = cellTexts[2]?.trim();
      if (skillDesc && skillDesc.length > 10) {
        soldier.skillDescription = toTC(skillDesc.substring(0, 500));
      }

      // 所屬英雄（cell 3）
      const heroList = cellTexts[3]?.trim();
      if (heroList && heroList.length > 2) {
        soldier.heroes = heroList.split(/[、，,]/).map(h => toTC(h.trim())).filter(h => h.length >= 2);
      }

      soldiers.push(soldier);
    });
  });

  // 去重
  const seen = new Set();
  const unique = soldiers.filter(s => {
    if (seen.has(s.name)) return false;
    seen.add(s.name);
    return true;
  });

  mkdirSync(DATA_DIR, { recursive: true });
  const outPath = join(DATA_DIR, 'soldiers.json');
  writeFileSync(outPath, JSON.stringify(unique, null, 2), 'utf-8');

  const types = {};
  for (const s of unique) types[s.type] = (types[s.type] || 0) + 1;

  console.log(`解析完成：${unique.length} 個兵種`);
  console.log('類型分佈：', JSON.stringify(types));

  const levels = {};
  for (const s of unique) levels[s.level] = (levels[s.level] || 0) + 1;
  console.log('等級分佈：', JSON.stringify(levels));

  if (debug) {
    console.log('\n=== 範例 ===');
    unique.slice(0, 3).forEach(s => console.log(JSON.stringify(s, null, 2)));
  }

  console.log(`\n已存到 ${outPath}`);
}

main();
