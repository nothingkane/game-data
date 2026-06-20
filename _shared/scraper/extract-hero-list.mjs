/**
 * 從英雄圖鑑提取英雄列表 v3
 * 直接從 .hero-grid 容器抓取
 */
import { chromium } from 'playwright';
import { writeFileSync } from 'fs';

async function extractHeroList() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'zh-TW',
    viewport: { width: 1920, height: 1080 },
  });

  const page = await context.newPage();
  await page.goto('https://wiki.biligame.com/langrisser/%E8%8B%B1%E9%9B%84%E5%9B%BE%E9%89%B4', {
    waitUntil: 'domcontentloaded',
    timeout: 30000,
  });
  await page.waitForTimeout(5000);

  const heroes = await page.evaluate(() => {
    const grid = document.querySelector('.hero-grid');
    if (!grid) return [];

    const links = grid.querySelectorAll('a');
    const seen = new Set();
    const results = [];

    for (const a of links) {
      const name = a.textContent.trim();
      const href = a.getAttribute('href');
      if (!name || !href || seen.has(name)) continue;
      seen.add(name);

      // 正規化 URL
      const url = href.startsWith('http') ? href : 'https://wiki.biligame.com' + href;
      results.push({ name, url });
    }

    return results;
  });

  console.log(`從 .hero-grid 找到 ${heroes.length} 個英雄\n`);
  heroes.sort((a, b) => a.name.localeCompare(b.name, 'zh'));
  for (let i = 0; i < heroes.length; i++) {
    console.log(`${String(i + 1).padStart(3)}. ${heroes[i].name}`);
  }

  writeFileSync('hero-list.json', JSON.stringify(heroes, null, 2), 'utf-8');
  console.log(`\n已儲存到 hero-list.json`);

  await browser.close();
}

extractHeroList().catch(console.error);
