/**
 * 抓取戰鬥公式相關 wiki 頁面
 */
import { chromium } from 'playwright';
import { writeFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const RAW_DIR = join(import.meta.dirname, '../../夢幻模擬戰/raw/battle');

const PAGES = [
  { name: '基礎數據分析', url: 'https://wiki.biligame.com/langrisser/%E6%A2%A6%E6%88%98%E5%9F%BA%E7%A1%80%E6%95%B0%E6%8D%AE%E5%88%86%E6%9E%90' },
  { name: '傷害計算器', url: 'https://wiki.biligame.com/langrisser/%E4%BC%A4%E5%AE%B3%E8%AE%A1%E7%AE%97%E5%99%A8/%E7%AE%80%E6%98%93%E7%89%88' },
  { name: '兵種數據', url: 'https://wiki.biligame.com/langrisser/%E5%85%B5%E7%A7%8D%E6%95%B0%E6%8D%AE' },
  { name: '地形', url: 'https://wiki.biligame.com/langrisser/%E5%9C%B0%E5%BD%A2' },
];

async function main() {
  mkdirSync(RAW_DIR, { recursive: true });

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
  await page.goto('https://wiki.biligame.com/langrisser/%E9%A6%96%E9%A1%B5', {
    waitUntil: 'domcontentloaded', timeout: 30000,
  });
  await new Promise(r => setTimeout(r, 3000));

  for (const { name, url } of PAGES) {
    await new Promise(r => setTimeout(r, 3000 + Math.random() * 5000));
    try {
      const response = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await new Promise(r => setTimeout(r, 2000));
      const status = response?.status() ?? 0;

      if (status === 200) {
        const html = await page.content();
        writeFileSync(join(RAW_DIR, `${name}.html`), html, 'utf-8');

        // 也存純文字方便閱讀
        const text = await page.evaluate(() => {
          const content = document.querySelector('.mw-parser-output') || document.body;
          return content.innerText;
        });
        writeFileSync(join(RAW_DIR, `${name}.txt`), text, 'utf-8');

        console.log(`✅ ${name} — ${(html.length / 1024).toFixed(0)}KB HTML, ${(text.length / 1024).toFixed(0)}KB text`);
      } else {
        console.log(`❌ ${name} — HTTP ${status}`);
      }
    } catch (err) {
      console.log(`❌ ${name} — ${err.message.split('\n')[0]}`);
    }
  }

  await browser.close();
}

main().catch(console.error);
