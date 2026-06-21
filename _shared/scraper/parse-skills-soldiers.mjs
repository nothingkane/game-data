/**
 * 技能（鑄紋）+ 士兵資料解析器
 *
 * Usage:
 *   node parse-skills-soldiers.mjs
 */
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import * as cheerio from 'cheerio';
import * as OpenCC from 'opencc-js';

const RAW_DIR = join(import.meta.dirname, '../../夢幻模擬戰/raw');
const DATA_DIR = join(import.meta.dirname, '../../夢幻模擬戰/data');
const s2t = OpenCC.Converter({ from: 'cn', to: 'twp' });
const toTC = (t) => t ? s2t(t.trim()) : '';

function parseEnchantSkills() {
  const filePath = join(RAW_DIR, 'skills/鑄紋技能.html');
  if (!existsSync(filePath)) {
    console.log('⏭ 鑄紋技能 HTML 不存在');
    return [];
  }

  const html = readFileSync(filePath, 'utf-8');
  const $ = cheerio.load(html);
  const skills = [];

  $('.mw-parser-output table').each((_, table) => {
    const text = $(table).text();
    if (!text.includes('名称') || !text.includes('描述')) return;

    $(table).find('tr').each((_, tr) => {
      const cells = $(tr).find('td');
      if (cells.length < 2) return;
      const cellTexts = cells.map((__, c) => $(c).text().trim()).get();
      const name = cellTexts[1]?.replace(/\s+/g, '');
      const desc = cellTexts[2] || '';
      if (name && name.length >= 2 && desc.length > 10) {
        skills.push({ name: toTC(name), description: toTC(desc) });
      }
    });
  });

  return skills;
}

function parseSoldiers() {
  const filePath = join(RAW_DIR, 'soldiers/士兵圖鑑.html');
  if (!existsSync(filePath)) {
    console.log('⏭ 士兵圖鑑 HTML 不存在');
    return [];
  }

  const html = readFileSync(filePath, 'utf-8');
  const $ = cheerio.load(html);
  const soldiers = [];
  const seen = new Set();

  // 從 HTML 提取士兵卡片
  // 士兵圖鑑通常用類似英雄圖鑑的 grid 結構
  const content = $('.mw-parser-output');

  // 找帶連結的士兵名稱
  content.find('a[href*="/langrisser/"]').each((_, a) => {
    const name = $(a).text().trim();
    const href = $(a).attr('href') || '';
    if (!name || name.length < 2 || name.length > 15 || seen.has(name)) return;

    // 排除導航連結
    const skip = ['首页', '图鉴', '查询', '数据', '编辑', '历史', 'WIKI', '攻略', '装备', '技能', '英雄'];
    if (skip.some(s => name.includes(s))) return;
    if (href.includes('模板') || href.includes('分类') || href.includes('特殊')) return;
    if (href.includes('action=')) return;

    seen.add(name);
    soldiers.push({
      name: toTC(name),
      url: href.startsWith('http') ? href : 'https://wiki.biligame.com' + href,
    });
  });

  return soldiers;
}

function parseSoldierCategories() {
  // 從純文字提取分類資訊
  const filePath = join(RAW_DIR, 'soldiers/士兵圖鑑.txt');
  if (!existsSync(filePath)) return {};

  const text = readFileSync(filePath, 'utf-8');

  // 解析分類統計
  const categories = {};
  const catMatch = text.match(/兵种\s*\n([\s\S]*?)(?:\n\n|\n[^\s])/);
  if (catMatch) {
    const catLine = catMatch[1];
    const pairs = catLine.match(/(\S+)\((\d+)\)/g);
    if (pairs) {
      for (const p of pairs) {
        const m = p.match(/(.+)\((\d+)\)/);
        if (m) categories[toTC(m[1])] = parseInt(m[2]);
      }
    }
  }

  // 解析等級統計
  const levels = {};
  const lvlMatch = text.match(/等级\s*\n([\s\S]*?)(?:\n\n|\n兵种)/);
  if (lvlMatch) {
    const lvlLine = lvlMatch[1];
    const pairs = lvlLine.match(/(\S+)\s*\((\d+)\)/g);
    if (pairs) {
      for (const p of pairs) {
        const m = p.match(/(.+?)\s*\((\d+)\)/);
        if (m) levels[m[1].trim()] = parseInt(m[2]);
      }
    }
  }

  return { categories, levels };
}

function main() {
  mkdirSync(DATA_DIR, { recursive: true });

  // 鑄紋技能
  const enchantSkills = parseEnchantSkills();
  if (enchantSkills.length > 0) {
    const outPath = join(DATA_DIR, 'enchant-skills.json');
    writeFileSync(outPath, JSON.stringify(enchantSkills, null, 2), 'utf-8');
    console.log(`✅ 鑄紋技能：${enchantSkills.length} 個 → enchant-skills.json`);
  }

  // 士兵
  const soldiers = parseSoldiers();
  const soldierMeta = parseSoldierCategories();
  if (soldiers.length > 0) {
    const result = {
      _meta: {
        totalByType: soldierMeta.categories || {},
        totalByLevel: soldierMeta.levels || {},
      },
      soldiers,
    };
    const outPath = join(DATA_DIR, 'soldiers.json');
    writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf-8');
    console.log(`✅ 士兵：${soldiers.length} 個 → soldiers.json`);
    if (Object.keys(soldierMeta.categories || {}).length > 0) {
      console.log('   兵種分佈：', JSON.stringify(soldierMeta.categories));
    }
  }

  console.log('\n完成！');
}

main();
