/**
 * 批次下載英雄頁面 v2
 * 反反爬策略：長延遲 + 分批暫停 + 定期刷新 context + 隨機順序
 *
 * Usage:
 *   node batch-download-heroes.mjs              # 全部下載（跳過已存在）
 *   node batch-download-heroes.mjs --limit 10   # 只下載 10 個
 *   node batch-download-heroes.mjs --force       # 強制重新下載
 *   node batch-download-heroes.mjs --batch 5     # 每批 5 個（預設 8）
 */
import { chromium } from 'playwright';
import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';

const HERO_LIST = join(import.meta.dirname, 'hero-list.json');
const RAW_DIR = join(import.meta.dirname, '../../夢幻模擬戰/raw/heroes');
const MANIFEST_PATH = join(import.meta.dirname, '../../夢幻模擬戰/cache-manifest.json');

const DELAY_MIN = 5000;
const DELAY_MAX = 15000;
const BATCH_SIZE_DEFAULT = 8;
const BATCH_PAUSE_MIN = 20000;
const BATCH_PAUSE_MAX = 45000;
const CONTEXT_REFRESH_EVERY = 25;

function parseArgs() {
  const args = process.argv.slice(2);
  return {
    limit: args.includes('--limit') ? parseInt(args[args.indexOf('--limit') + 1]) : Infinity,
    force: args.includes('--force'),
    batch: args.includes('--batch') ? parseInt(args[args.indexOf('--batch') + 1]) : BATCH_SIZE_DEFAULT,
  };
}

function loadManifest() {
  if (existsSync(MANIFEST_PATH)) return JSON.parse(readFileSync(MANIFEST_PATH, 'utf-8'));
  return { heroes: {} };
}

function saveManifest(manifest) {
  writeFileSync(MANIFEST_PATH, JSON.stringify(manifest, null, 2), 'utf-8');
}

function randomDelay(min, max) {
  return new Promise(r => setTimeout(r, min + Math.random() * (max - min)));
}

function shuffle(arr) {
  const result = [...arr];
  for (let i = result.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
}

async function createContext(browser) {
  return browser.newContext({
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'zh-TW',
    viewport: { width: 1920, height: 1080 },
    extraHTTPHeaders: {
      'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
      'Accept-Language': 'zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7',
      'Accept-Encoding': 'gzip, deflate, br',
    },
  });
}

async function warmupContext(page) {
  // 先訪問首頁建立正常的瀏覽 session
  try {
    await page.goto('https://wiki.biligame.com/langrisser/%E9%A6%96%E9%A1%B5', {
      waitUntil: 'domcontentloaded', timeout: 20000,
    });
    await randomDelay(2000, 4000);
  } catch { /* ignore */ }
}

async function main() {
  const { limit, force, batch: batchSize } = parseArgs();
  const heroes = JSON.parse(readFileSync(HERO_LIST, 'utf-8'));
  const manifest = loadManifest();
  mkdirSync(RAW_DIR, { recursive: true });

  let toDownload = heroes.filter(h => {
    if (force) return true;
    return !existsSync(join(RAW_DIR, `${h.name}.html`));
  }).slice(0, limit);

  // 隨機排序，避免 URL 模式太規律
  toDownload = shuffle(toDownload);

  console.log(`英雄總數：${heroes.length}`);
  console.log(`待下載：${toDownload.length}（已跳過 ${heroes.length - toDownload.length} 個已存在）`);
  console.log(`批次大小：${batchSize}，預估時間：${Math.ceil(toDownload.length / batchSize * 0.5)} 分鐘`);
  console.log('');

  if (toDownload.length === 0) {
    console.log('全部已下載完成！');
    return;
  }

  const browser = await chromium.launch({
    headless: false,
    args: ['--disable-blink-features=AutomationControlled'],
  });
  let context = await createContext(browser);
  let page = await context.newPage();

  // 暖機：先訪問首頁 + 英雄圖鑑（模擬正常瀏覽）
  console.log('暖機中（首頁 → 英雄圖鑑 → 等待）...');
  await warmupContext(page);
  try {
    await page.goto('https://wiki.biligame.com/langrisser/%E8%8B%B1%E9%9B%84%E5%9B%BE%E9%89%B4', {
      waitUntil: 'domcontentloaded', timeout: 20000,
    });
    await randomDelay(3000, 5000);
  } catch { /* ignore */ }
  console.log('暖機完成，開始下載...\n');

  let success = 0;
  let failed = 0;
  let consecutiveFails = 0;

  for (let i = 0; i < toDownload.length; i++) {
    const hero = toDownload[i];
    const progress = `[${i + 1}/${toDownload.length}]`;

    // 每 N 個刷新 context
    if (i > 0 && i % CONTEXT_REFRESH_EVERY === 0) {
      console.log(`\n🔄 刷新瀏覽器 context...`);
      await page.close();
      await context.close();
      context = await createContext(browser);
      page = await context.newPage();
      await warmupContext(page);
      consecutiveFails = 0;
    }

    // 批次暫停
    if (i > 0 && i % batchSize === 0) {
      const pause = BATCH_PAUSE_MIN + Math.random() * (BATCH_PAUSE_MAX - BATCH_PAUSE_MIN);
      console.log(`\n⏸ 批次暫停 ${(pause / 1000).toFixed(0)}s (已完成 ${success}/${i})...\n`);
      await new Promise(r => setTimeout(r, pause));
    }

    // 連續失敗太多次，長暫停
    if (consecutiveFails >= 5) {
      console.log(`\n⚠️ 連續 ${consecutiveFails} 次失敗，長暫停 60s + 刷新 context...`);
      await page.close();
      await context.close();
      await new Promise(r => setTimeout(r, 60000));
      context = await createContext(browser);
      page = await context.newPage();
      await warmupContext(page);
      consecutiveFails = 0;
    }

    try {
      const response = await page.goto(hero.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
      await randomDelay(1500, 3000);

      const status = response?.status() ?? 0;
      if (status !== 200) {
        console.log(`${progress} ❌ ${hero.name} — HTTP ${status}`);
        failed++;
        consecutiveFails++;
        continue;
      }

      const html = await page.content();
      writeFileSync(join(RAW_DIR, `${hero.name}.html`), html, 'utf-8');

      manifest.heroes[hero.name] = {
        url: hero.url,
        downloadedAt: new Date().toISOString(),
        fileSize: html.length,
        filePath: `raw/heroes/${hero.name}.html`,
      };
      saveManifest(manifest);

      const sizeKB = (html.length / 1024).toFixed(0);
      console.log(`${progress} ✅ ${hero.name} — ${sizeKB}KB`);
      success++;
      consecutiveFails = 0;
    } catch (err) {
      console.log(`${progress} ❌ ${hero.name} — ${err.message.split('\n')[0]}`);
      failed++;
      consecutiveFails++;
    }

    // 隨機延遲
    if (i < toDownload.length - 1) {
      await randomDelay(DELAY_MIN, DELAY_MAX);
    }
  }

  await browser.close();
  console.log(`\n完成！成功 ${success}，失敗 ${failed}`);
}

main().catch(console.error);
