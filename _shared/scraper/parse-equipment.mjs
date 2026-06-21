/**
 * 裝備數據解析器
 * 從裝備數據表 HTML 提取結構化 JSON
 *
 * Usage:
 *   node parse-equipment.mjs
 *   node parse-equipment.mjs --debug
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import * as cheerio from 'cheerio';
import * as OpenCC from 'opencc-js';

const RAW_PATH = join(import.meta.dirname, '../../夢幻模擬戰/raw/equipment/裝備數據表.html');
const DATA_DIR = join(import.meta.dirname, '../../夢幻模擬戰/data');
const s2t = OpenCC.Converter({ from: 'cn', to: 'twp' });
const toTC = (t) => t ? s2t(t.trim()) : '';

function parseStatValue(text) {
  if (!text || !text.trim()) return null;
  const match = text.trim().match(/^(\d+)\/?(\d+)?$/);
  if (!match) return null;
  return { base: parseInt(match[1]), max: match[2] ? parseInt(match[2]) : parseInt(match[1]) };
}

function main() {
  const debug = process.argv.includes('--debug');

  if (!existsSync(RAW_PATH)) {
    console.error('裝備數據表 HTML 不存在，請先執行 node fetch-data-pages.mjs');
    process.exit(1);
  }

  const html = readFileSync(RAW_PATH, 'utf-8');
  const $ = cheerio.load(html);
  const content = $('.mw-parser-output');
  const equipment = [];

  // 表格結構（11 欄）：圖示 | 名稱 | 專屬英雄 | 類型 | 滿級特效 | 生命 | 攻擊 | 智力 | 防禦 | 魔防 | 技巧
  content.find('table').each((_, table) => {
    const headerText = $(table).text();
    if (!headerText.includes('名称') || !headerText.includes('满级特效')) return;

    $(table).find('tr').each((_, tr) => {
      const cells = $(tr).find('td');
      if (cells.length < 10) return;

      const cellTexts = cells.map((__, c) => $(c).text().trim()).get();

      const name = cellTexts[1]?.replace(/\s+/g, '');
      const exclusiveHero = cellTexts[2]?.replace(/\s+/g, '') || '';
      const type = cellTexts[3] || '';
      const effect = cellTexts[4] || '';

      if (!name || name.length < 2) return;
      // 如果沒有類型且不在已知裝備類型列表中，跳過
      const validTypes = ['武器', '防具', '头饰', '饰品'];
      if (type && !validTypes.includes(type)) return;

      const statFields = ['hp', 'atk', 'int', 'def', 'mdef', 'skill'];
      const stats = {};
      for (let i = 0; i < statFields.length; i++) {
        const val = parseStatValue(cellTexts[5 + i]);
        if (val) stats[statFields[i]] = val;
      }

      const item = {
        name: toTC(name),
        type: toTC(type || '未分類'),
        ...(exclusiveHero ? { exclusiveHero: toTC(exclusiveHero) } : {}),
        effect: toTC(effect.substring(0, 200)),
        stats,
      };

      equipment.push(item);
    });
  });

  // 去重
  const seen = new Set();
  const unique = equipment.filter(e => {
    if (seen.has(e.name)) return false;
    seen.add(e.name);
    return true;
  });

  mkdirSync(DATA_DIR, { recursive: true });
  const outPath = join(DATA_DIR, 'equipment.json');
  writeFileSync(outPath, JSON.stringify(unique, null, 2), 'utf-8');

  console.log(`解析完成：${unique.length} 件裝備`);
  const types = {};
  for (const e of unique) types[e.type] = (types[e.type] || 0) + 1;
  console.log('類型分佈：', JSON.stringify(types));
  const excl = unique.filter(e => e.exclusiveHero).length;
  console.log(`專屬裝備：${excl} 件`);

  if (debug) {
    console.log('\n=== 範例 ===');
    unique.slice(0, 5).forEach(e => console.log(JSON.stringify(e, null, 2)));
  }

  console.log(`\n已存到 ${outPath}`);
}

main();
