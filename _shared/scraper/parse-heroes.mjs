/**
 * 英雄資料離線解析器
 * 從已下載的 HTML 檔案提取結構化 JSON
 *
 * Usage:
 *   node parse-heroes.mjs                    # 解析所有已下載的英雄
 *   node parse-heroes.mjs --hero 利昂        # 只解析指定英雄
 *   node parse-heroes.mjs --limit 5          # 解析前 5 個
 *   node parse-heroes.mjs --debug            # 除錯模式（顯示詳細資訊）
 */
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'fs';
import { join, basename } from 'path';
import * as cheerio from 'cheerio';
import * as OpenCC from 'opencc-js';

const RAW_DIR = join(import.meta.dirname, '../../夢幻模擬戰/raw/heroes');
const DATA_DIR = join(import.meta.dirname, '../../夢幻模擬戰/data');

const s2t = OpenCC.Converter({ from: 'cn', to: 'twp' });

function toTC(text) {
  if (!text) return '';
  return s2t(text.trim());
}

function parseArgs() {
  const args = process.argv.slice(2);
  return {
    hero: args.includes('--hero') ? args[args.indexOf('--hero') + 1] : null,
    limit: args.includes('--limit') ? parseInt(args[args.indexOf('--limit') + 1]) : Infinity,
    debug: args.includes('--debug'),
  };
}

function parseHeroHtml(htmlContent, heroFileName, debug = false) {
  const $ = cheerio.load(htmlContent);
  const content = $('.mw-parser-output');
  const hero = {};

  // === 名稱 ===
  const title = $('h1').first().text().trim() || heroFileName.replace('.html', '');
  hero.name = toTC(title);

  // === 稀有度 ===
  const rarityImg = content.find('img[alt*="级别"]').first();
  if (rarityImg.length) {
    const alt = rarityImg.attr('alt') || '';
    const match = alt.match(/级别\s*(LLR|SP|SSR|SR|R|N)/i);
    hero.rarity = match ? match[1].toUpperCase() : '';
  }

  // === 基礎資訊表格（身高/體重/出典/陣營/CV）===
  content.find('table').each((_, table) => {
    const tableText = $(table).text();
    if (tableText.includes('出典') && tableText.includes('阵营')) {
      $(table).find('tr').each((_, tr) => {
        const cells = $(tr).find('td, th').map((__, c) => $(c).text().trim()).get();
        for (let i = 0; i < cells.length - 1; i++) {
          switch (cells[i]) {
            case '出典': hero.origin = toTC(cells[i + 1]); break;
            case '阵营': hero.faction = toTC(cells[i + 1]); break;
            case 'CV': hero.cv = cells[i + 1]; break;
            case '身高': hero.height = cells[i + 1]; break;
            case '体重': hero.weight = cells[i + 1]; break;
          }
        }
      });
    }
  });

  // === 兵修數據 ===
  const trainingDiv = content.find('*').filter((_, el) => {
    const t = $(el).text().trim();
    return t.includes('生命兵修') && !t.includes('铸纹') && $(el).children().length < 30 && t.length < 500;
  }).first();

  if (trainingDiv.length) {
    const tText = trainingDiv.text();
    const parseTraining = (label) => {
      const regex = new RegExp(`${label}\\s*([\\d.]+%)\\s*([\\d.]+%)\\s*([\\d.]+%)`);
      const m = tText.match(regex);
      return m ? [m[1], m[2], m[3]] : [];
    };
    hero.soldierTraining = {
      hp: parseTraining('生命兵修'),
      atk: parseTraining('攻击兵修'),
      def: parseTraining('防御兵修'),
      mdef: parseTraining('魔防兵修'),
    };
  }

  // === 鑄紋技能 ===
  const enchantSection = content.find('*').filter((_, el) => {
    const t = $(el).text().trim();
    return t.startsWith('铸纹技能') && $(el).children().length < 15;
  }).first();

  if (enchantSection.length) {
    const eText = enchantSection.text().replace('铸纹技能', '').trim();
    if (eText) {
      // 鑄紋技能名稱 = 開頭 2-8 字的專有名詞，之後是屬性加成或技能描述
      const splitMatch = eText.match(
        /^(.{2,8}?)((?:攻击|防御|智力|魔防|生命|技巧|攻擊|防禦)[+、，]|全属性|暴击|治疗|行动结束|\[|"|主动|使用|周围|进入|携带|持续|死亡|施加|造成|被攻|触发|释放|当[自敌]|每移|移动|远程|拥有|自身|全场|对[友敌处]|天赋|与[克剋枪]|["“]|身上|技能|部队)/
      );
      if (splitMatch) {
        hero.enchantSkill = {
          name: toTC(splitMatch[1]),
          description: toTC(eText.substring(splitMatch[1].length).trim()),
        };
      } else {
        hero.enchantSkill = {
          name: toTC(eText.substring(0, 20)),
          description: toTC(eText.substring(20).trim()),
        };
      }
    }
  }

  // === 專屬裝備 ===
  const exclusiveSection = content.find('*').filter((_, el) => {
    const t = $(el).text().trim();
    return t.startsWith('专属装备') && $(el).children().length < 15 && t.length < 500;
  }).first();

  if (exclusiveSection.length) {
    const eqText = exclusiveSection.text().replace('专属装备', '').trim();
    const lines = eqText.split('\n').filter(l => l.trim());
    if (lines.length >= 1) {
      hero.exclusiveEquipment = {
        name: toTC(lines[0]?.replace(/\s+/g, ' ')),
        rawText: toTC(lines.join(' ').substring(0, 300)),
      };
    }
  }

  // === 天賦 ===
  const talents = [];
  const talentTabs = content.find('.resp-tab-content');
  talentTabs.each((i, tab) => {
    const tabText = $(tab).text().trim();
    if ((tabText.includes('英雄天赋') || tabText.includes('天赋')) && i < 2) {
      // 提取天賦名和描述
      const lines = tabText.split('\n').filter(l => l.trim());
      // 跳過 "英雄天赋展/折" 等標題
      const contentLines = lines.filter(l =>
        !l.includes('展/折') && !l.includes('英雄天赋') && !l.includes('SP天赋')
        && !l.includes('天赋说明') && l.trim().length > 0
      );
      if (contentLines.length >= 2) {
        const isSpTab = tabText.includes('SP职业天赋');
        // 天賦有多個等級描述（用空行分隔），取最後一段（最高級）
        const descText = contentLines.slice(1).join('\n');
        // 用空行或重複模式分段，取最後一段有實質內容的
        const segments = descText.split(/\n{2,}/).filter(s => s.trim().length > 10);
        const maxDesc = segments.length > 0 ? segments[segments.length - 1] : descText;
        talents.push({
          type: isSpTab ? 'SP' : '基礎',
          name: toTC(contentLines[0]),
          description: toTC(maxDesc.replace(/\n/g, '').substring(0, 500)),
        });
      }
    }
  });
  if (talents.length) hero.talents = talents;

  // === 羈絆 ===
  const bonds = [];
  content.find('table').each((_, table) => {
    const tableText = $(table).text();
    if (tableText.includes('羁绊解锁条件') && !tableText.includes('心之羁绊')) {
      $(table).find('tr').each((_, tr) => {
        const th = $(tr).find('th').first();
        const thText = th.text().trim();
        if (thText.includes('解锁条件') && thText !== '羁绊解锁条件') {
          const tds = $(tr).find('td').map((__, c) => $(c).text().trim()).get();
          bonds.push({
            type: toTC(thText.replace('解锁条件', '').trim()),
            conditions: tds.filter(c => c).map(toTC),
          });
        }
      });
    }
  });

  // 可幫助解鎖羈絆的英雄
  const bondHelpers = [];
  content.find('table').each((_, table) => {
    const tableText = $(table).text();
    if (tableText.includes('可帮助解锁羁绊')) {
      $(table).find('a').each((_, a) => {
        const name = $(a).text().trim();
        if (name && name.length > 1 && name.length < 15) {
          const tcName = toTC(name);
          if (!bondHelpers.includes(tcName)) bondHelpers.push(tcName);
        }
      });
    }
  });

  if (bonds.length) hero.bondConditions = bonds;
  if (bondHelpers.length) hero.bondHelpers = bondHelpers;

  // === 心之羈絆 ===
  const heartBonds = [];
  content.find('table').each((_, table) => {
    const tableText = $(table).text();
    if (tableText.includes('心之羁绊Lv')) {
      $(table).find('tr').each((_, tr) => {
        const th = $(tr).find('th').first();
        const thText = th.text().trim();
        const lvMatch = thText.match(/心之羁绊Lv(\d+)/);
        if (lvMatch) {
          const td = $(tr).find('td').first();
          const effect = td.text().trim();
          heartBonds.push({ level: parseInt(lvMatch[1]), effect: toTC(effect) });
        }
      });
    }
  });
  if (heartBonds.length) hero.heartBonds = heartBonds;

  // === 科技兵種 ===
  const soldiers = [];
  const soldierSkipWords = ['扩展', '重塑', '展开', '折叠', '练兵场', '科技兵种', '扩充套件'];
  content.find('.SoldierList50, .SoldierList').each((_, el) => {
    const text = $(el).text().trim();
    const lines = text.split('\n').filter(l => l.trim());
    for (const line of lines) {
      const name = line.trim();
      if (!name || name.length < 2 || name.length > 15) continue;
      if (soldierSkipWords.some(w => name.includes(w))) continue;
      const tcName = toTC(name);
      if (!soldiers.includes(tcName) && !soldierSkipWords.some(w => tcName.includes(w))) {
        soldiers.push(tcName);
      }
    }
  });
  if (soldiers.length) hero.soldiers = [...new Set(soldiers)];

  // === 職業屬性（從 resp-tab-content 內的 table 提取）===
  const classes = [];
  talentTabs.each((i, tab) => {
    const tabText = $(tab).text().trim();
    if (!tabText.includes('移动') || !tabText.includes('生命') || !tabText.includes('攻击')) return;

    // 每個職業 tab 內有 stats table，找最後一個（較乾淨的）
    const tables = $(tab).find('table');
    let statsTable = null;
    tables.each((_, t) => {
      const tText = $(t).text();
      if (tText.includes('移动') && tText.includes('生命') && !tText.includes('习得技能')) {
        statsTable = $(t);
      }
    });
    // 退守：找包含 stats 的第一個 table
    if (!statsTable) {
      tables.each((_, t) => {
        const tText = $(t).text();
        if (tText.includes('移动') && tText.includes('生命')) {
          statsTable = $(t);
          return false;
        }
      });
    }
    if (!statsTable) return;

    // 職業名稱：取 tab 文字的第一個有意義的行（在 "职业" 之前）
    const lines = tabText.split('\n').filter(l => l.trim());
    let className = '';
    for (const line of lines) {
      const t = line.trim();
      if (t === '职业' || t === '移动' || t === '习得技能') break;
      if (t.length >= 2 && t.length <= 15 && !t.includes('展/折') && !t.includes('天赋')) {
        className = t;
        break;
      }
    }

    // 從 table rows 提取 stats
    const stats = {};
    statsTable.find('tr').each((_, tr) => {
      const cells = $(tr).find('td, th').map((__, c) => $(c).text().trim()).get();
      if (cells.length === 2) {
        const key = cells[0];
        const val = cells[1];
        if (['移动', '射程', '生命', '攻击', '智力', '防御', '魔防', '技巧'].includes(key)) {
          stats[key] = val ? parseInt(val) : 0;
        }
      }
    });

    // 修正移動/射程黏連問題：如果移動 > 9 且射程為 0，拆開
    if (stats['移动'] > 9 && (!stats['射程'] || stats['射程'] === 0)) {
      const combined = String(stats['移动']);
      stats['移动'] = parseInt(combined[0]);
      stats['射程'] = parseInt(combined.substring(1)) || 1;
    }

    if (Object.keys(stats).length >= 4) {
      classes.push({
        name: toTC(className || `職業${classes.length + 1}`),
        stats: {
          hp: stats['生命'] || 0,
          atk: stats['攻击'] || 0,
          int: stats['智力'] || 0,
          def: stats['防御'] || 0,
          mdef: stats['魔防'] || 0,
          skill: stats['技巧'] || 0,
          move: stats['移动'] || 0,
          range: stats['射程'] || 0,
        },
      });
    }
  });
  if (classes.length) hero.classes = classes;

  // === 傳記（簡要提取）===
  const bioSection = content.find('*').filter((_, el) => {
    const t = $(el).text().trim();
    return t.startsWith('传记一') && t.length < 2000;
  }).first();
  if (bioSection.length) {
    const bioText = bioSection.text().replace(/传记[一二三四五六七八九十SP]+/g, '').trim();
    if (bioText) hero.biography = toTC(bioText.substring(0, 500));
  }

  // === UP 次數 ===
  const upMatch = content.text().match(/UP次数：(\d+)/);
  if (upMatch) hero.upCount = parseInt(upMatch[1]);
  const pickMatch = content.text().match(/精选次数：(\d+)/);
  if (pickMatch) hero.featuredCount = parseInt(pickMatch[1]);

  // 清理 undefined 欄位
  for (const key of Object.keys(hero)) {
    if (hero[key] === undefined || hero[key] === '') delete hero[key];
  }

  return hero;
}

function main() {
  const { hero: targetHero, limit, debug } = parseArgs();
  mkdirSync(DATA_DIR, { recursive: true });

  let files;
  if (targetHero) {
    const filePath = join(RAW_DIR, `${targetHero}.html`);
    if (!existsSync(filePath)) {
      console.error(`找不到 ${filePath}`);
      process.exit(1);
    }
    files = [`${targetHero}.html`];
  } else {
    files = readdirSync(RAW_DIR).filter(f => f.endsWith('.html')).slice(0, limit);
  }

  console.log(`準備解析 ${files.length} 個英雄...\n`);

  const allHeroes = [];
  let success = 0;
  let failed = 0;

  for (const file of files) {
    try {
      const html = readFileSync(join(RAW_DIR, file), 'utf-8');
      const hero = parseHeroHtml(html, file, debug);
      allHeroes.push(hero);

      const fields = Object.keys(hero).filter(k => k !== 'name').length;
      if (debug) {
        console.log(`✅ ${hero.name} — ${fields} 欄位`);
        console.log(JSON.stringify(hero, null, 2));
        console.log('---');
      } else {
        console.log(`✅ ${hero.name} — ${fields} 欄位`);
      }
      success++;
    } catch (err) {
      console.log(`❌ ${file} — ${err.message}`);
      failed++;
    }
  }

  // 輸出結果
  if (targetHero && allHeroes.length === 1) {
    const outPath = join(DATA_DIR, `hero_${targetHero}.json`);
    writeFileSync(outPath, JSON.stringify(allHeroes[0], null, 2), 'utf-8');
    console.log(`\n已存到 ${outPath}`);
  }

  if (!targetHero && allHeroes.length > 0) {
    const outPath = join(DATA_DIR, 'heroes.json');
    writeFileSync(outPath, JSON.stringify(allHeroes, null, 2), 'utf-8');
    console.log(`\n已存到 ${outPath}`);
  }

  console.log(`\n完成！成功 ${success}，失敗 ${failed}`);
}

main();
