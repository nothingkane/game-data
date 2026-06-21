/**
 * 從英雄頁面提取所有技能（去重後建立完整技能庫）
 *
 * Usage:
 *   node parse-skills-from-heroes.mjs
 *   node parse-skills-from-heroes.mjs --debug
 */
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'fs';
import { join } from 'path';
import * as cheerio from 'cheerio';
import * as OpenCC from 'opencc-js';

const RAW_DIR = join(import.meta.dirname, '../../夢幻模擬戰/raw/heroes');
const DATA_DIR = join(import.meta.dirname, '../../夢幻模擬戰/data');
const s2t = OpenCC.Converter({ from: 'cn', to: 'twp' });
const toTC = (t) => t ? s2t(t.trim()) : '';

function extractSkillsFromHero(html) {
  const $ = cheerio.load(html);
  const skills = [];

  // 找所有 <th> 包含 "习得技能" 的行
  $('th').filter((_, el) => $(el).text().trim() === '习得技能').each((_, th) => {
    const headerRow = $(th).closest('tr');
    let row = headerRow.next();

    while (row.length) {
      const ths = row.find('th');
      const tds = row.find('td');
      // 技能行：1 個 th（名稱）+ 1 個 td（詳情）
      if (ths.length !== 1 || tds.length !== 1) break;

      const name = ths.eq(0).text().trim().replace(/\s+/g, '');
      const detail = tds.eq(0).text().trim();
      if (!name || name.length > 20 || !detail.includes('类别：')) { row = row.next(); continue; }

      const typeMatch = detail.match(/类别：(.+)/);
      const cdMatch = detail.match(/冷却：(.+)/);
      const rangeMatch = detail.match(/射程：(.+)/);
      const spanMatch = detail.match(/范围：(.+)/);

      let desc = '';
      const spanLine = detail.match(/范围：.+/);
      if (spanLine) {
        const spanEnd = detail.indexOf(spanLine[0]) + spanLine[0].length;
        desc = detail.substring(spanEnd).trim();
      }

      skills.push({
        name,
        type: typeMatch?.[1]?.trim() || '',
        cd: cdMatch?.[1]?.trim() || '',
        range: rangeMatch?.[1]?.trim() || '',
        span: spanMatch?.[1]?.trim() || '',
        description: desc,
      });

      row = row.next();
    }
  });

  return skills;
}

function main() {
  const debug = process.argv.includes('--debug');
  const files = readdirSync(RAW_DIR).filter(f => f.endsWith('.html'));

  console.log(`掃描 ${files.length} 個英雄頁面...\n`);

  const allSkills = new Map(); // name → skill data (去重用最長描述版本)
  const skillHeroes = new Map(); // skillName → Set of hero names

  for (const file of files) {
    const heroName = file.replace('.html', '');
    const html = readFileSync(join(RAW_DIR, file), 'utf-8');
    const skills = extractSkillsFromHero(html);

    for (const skill of skills) {
      const existing = allSkills.get(skill.name);
      if (!existing || skill.description.length > existing.description.length) {
        allSkills.set(skill.name, skill);
      }
      if (!skillHeroes.has(skill.name)) skillHeroes.set(skill.name, new Set());
      skillHeroes.get(skill.name).add(heroName);
    }
  }

  // 轉為陣列 + 簡繁轉換
  const result = [...allSkills.values()].map(s => ({
    name: toTC(s.name),
    type: toTC(s.type),
    cd: s.cd === '-' ? null : s.cd,
    range: s.range === '-' ? null : toTC(s.range),
    span: s.span === '-' ? null : toTC(s.span),
    description: toTC(s.description.substring(0, 500)),
    heroCount: skillHeroes.get(s.name)?.size || 0,
  })).sort((a, b) => a.name.localeCompare(b.name, 'zh'));

  mkdirSync(DATA_DIR, { recursive: true });
  const outPath = join(DATA_DIR, 'skills.json');
  writeFileSync(outPath, JSON.stringify(result, null, 2), 'utf-8');

  // 統計
  const types = {};
  for (const s of result) types[s.type] = (types[s.type] || 0) + 1;

  console.log(`技能總數：${result.length}（去重後）`);
  console.log('類型分佈：', JSON.stringify(types));
  console.log(`已存到 ${outPath}`);

  if (debug) {
    console.log('\n=== 範例 ===');
    result.slice(0, 5).forEach(s => console.log(JSON.stringify(s, null, 2)));
  }
}

main();
