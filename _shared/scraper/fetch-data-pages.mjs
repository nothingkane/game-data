/**
 * 抓取裝備/技能/士兵的 wiki 數據頁面
 * 這些資料在單一彙總頁面中（不像英雄需要逐個爬）
 *
 * Usage:
 *   node fetch-data-pages.mjs                # 抓取所有
 *   node fetch-data-pages.mjs --only 裝備     # 只抓裝備
 */
import { chromium } from 'playwright';
import { writeFileSync, mkdirSync, existsSync, statSync } from 'fs';
import { join } from 'path';

const BASE_DIR = join(import.meta.dirname, '../../夢幻模擬戰/raw');
const DELAY_MIN = 8000;
const DELAY_MAX = 20000;

const PAGES = [
  // 裝備
  { category: 'equipment', name: '裝備圖鑑', url: 'https://wiki.biligame.com/langrisser/%E8%A3%85%E5%A4%87%E5%9B%BE%E9%89%B4', dir: 'equipment' },
  { category: 'equipment', name: '裝備數據表', url: 'https://wiki.biligame.com/langrisser/%E8%A3%85%E5%A4%87%E6%95%B0%E6%8D%AE%E8%A1%A8', dir: 'equipment' },
  // 技能
  { category: 'skills', name: '技能查詢', url: 'https://wiki.biligame.com/langrisser/%E6%8A%80%E8%83%BD%E6%9F%A5%E8%AF%A2', dir: 'skills' },
  { category: 'skills', name: '技能數據表', url: 'https://wiki.biligame.com/langrisser/%E6%8A%80%E8%83%BD%E6%95%B0%E6%8D%AE%E8%A1%A8', dir: 'skills' },
  { category: 'skills', name: '鑄紋技能', url: 'https://wiki.biligame.com/langrisser/%E9%93%B8%E7%BA%B9%E6%8A%80%E8%83%BD', dir: 'skills' },
  // 士兵
  { category: 'soldiers', name: '士兵圖鑑', url: 'https://wiki.biligame.com/langrisser/%E5%A3%AB%E5%85%B5%E5%9B%BE%E9%89%B4', dir: 'soldiers' },
  { category: 'soldiers', name: '兵種數據', url: 'https://wiki.biligame.com/langrisser/%E5%85%B5%E7%A7%8D%E6%95%B0%E6%8D%AE', dir: 'soldiers' },
];

function randomDelay() {
  return new Promise(r => setTimeout(r, DELAY_MIN + Math.random() * (DELAY_MAX - DELAY_MIN)));
}

async function main() {
  const args = process.argv.slice(2);
  const only = args.includes('--only') ? args[args.indexOf('--only') + 1] : null;

  let targets = PAGES;
  if (only) {
    targets = PAGES.filter(p => p.category.includes(only) || p.name.includes(only));
    console.log(`只抓取：${only}（${targets.length} 頁）\n`);
  }

  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-blink-features=AutomationControlled'],
  });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'zh-TW',
    viewport: { width: 1920, height: 1080 },
  });

  const page = await context.newPage();

  // 暖機
  console.log('暖機中...');
  await page.goto('https://wiki.biligame.com/langrisser/%E9%A6%96%E9%A1%B5', {
    waitUntil: 'domcontentloaded', timeout: 30000,
  });
  await randomDelay();
  console.log('暖機完成\n');

  let success = 0;
  let failed = 0;

  for (let i = 0; i < targets.length; i++) {
    const { name, url, dir } = targets[i];
    const outDir = join(BASE_DIR, dir);
    mkdirSync(outDir, { recursive: true });

    // 跳過已下載的
    const htmlPath = join(outDir, `${name}.html`);
    if (existsSync(htmlPath) && !args.includes('--force')) {
      const size = statSync(htmlPath).size;
      if (size > 10000) {
        console.log(`[${i + 1}/${targets.length}] ⏭ ${name} — 已存在 (${(size / 1024).toFixed(0)}KB)`);
        continue;
      }
    }

    if (i > 0) await randomDelay();

    try {
      console.log(`[${i + 1}/${targets.length}] 抓取 ${name}...`);
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await new Promise(r => setTimeout(r, 3000 + Math.random() * 3000));

      const status = response?.status() ?? 0;
      if (status !== 200) {
        console.log(`  ❌ HTTP ${status}`);
        failed++;
        continue;
      }

      // 存 HTML
      const html = await page.content();
      writeFileSync(join(outDir, `${name}.html`), html, 'utf-8');

      // 存純文字
      const text = await page.evaluate(() => {
        const content = document.querySelector('.mw-parser-output') || document.body;
        return content.innerText;
      });
      writeFileSync(join(outDir, `${name}.txt`), text, 'utf-8');

      const htmlKB = (html.length / 1024).toFixed(0);
      const textKB = (text.length / 1024).toFixed(0);
      console.log(`  ✅ ${htmlKB}KB HTML, ${textKB}KB text`);
      success++;
    } catch (err) {
      console.log(`  ❌ ${err.message.split('\n')[0]}`);
      failed++;
    }
  }

  await browser.close();
  console.log(`\n完成！成功 ${success}，失敗 ${failed}`);
}

main().catch(console.error);
