import { chromium } from 'playwright';
import { mkdirSync } from 'fs';
import { join } from 'path';

const BASE = 'http://127.0.0.1:4000';
const DIR = './test-screenshots';
try {
  mkdirSync(DIR, { recursive: true });
} catch {
  // Directory creation failures are surfaced later by screenshot writes.
}

const wait = (ms) => new Promise(r => setTimeout(r, ms));

async function run() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));

  console.log('1. Loading dashboard...');
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await wait(2000);
  await page.screenshot({ path: join(DIR, '01-dashboard.png'), fullPage: true });
  console.log('   Screenshot: 01-dashboard.png');

  console.log('2. Click Field Ops...');
  const fieldOps = page.locator('button:has-text("Field Ops"), button:has-text("野外调查")').first();
  if (await fieldOps.isVisible()) {
    await fieldOps.click();
    await wait(1500);
    await page.screenshot({ path: join(DIR, '02-fieldops.png'), fullPage: true });
    console.log('   Screenshot: 02-fieldops.png');
  } else {
    console.log('   Field Ops button not found');
  }

  console.log('3. Click Species...');
  const species = page.locator('button:has-text("Species"), button:has-text("物种")').first();
  if (await species.isVisible()) {
    await species.click();
    await wait(1500);
    await page.screenshot({ path: join(DIR, '03-species.png'), fullPage: true });
    console.log('   Screenshot: 03-species.png');
  }

  console.log('4. Click Settings...');
  const settings = page.locator('button:has-text("Settings"), button:has-text("设置")').first();
  if (await settings.isVisible()) {
    await settings.click();
    await wait(1500);
    await page.screenshot({ path: join(DIR, '04-settings.png'), fullPage: true });
    console.log('   Screenshot: 04-settings.png');
  }

  console.log('5. Click SDM...');
  const sdm = page.locator('button:has-text("Sites"), button:has-text("分布")').first();
  if (await sdm.isVisible()) {
    await sdm.click();
    await wait(1500);
    await page.screenshot({ path: join(DIR, '05-sdm.png'), fullPage: true });
    console.log('   Screenshot: 05-sdm.png');
  }

  console.log('6. Collapse sidebar...');
  const collapse = page.locator('button:has-text("Collapse"), button:has-text("收起")').first();
  if (await collapse.isVisible()) {
    await collapse.click();
    await wait(800);
    await page.screenshot({ path: join(DIR, '06-collapsed.png'), fullPage: true });
    console.log('   Screenshot: 06-collapsed.png');
    await collapse.click();
    await wait(500);
  }

  console.log('7. Mobile view (375px)...');
  await page.setViewportSize({ width: 375, height: 812 });
  await wait(1000);
  // Go back to dashboard
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await wait(2000);
  await page.screenshot({ path: join(DIR, '07-mobile.png'), fullPage: true });
  console.log('   Screenshot: 07-mobile.png');

  console.log('\n--- Console errors ---');
  if (errors.length === 0) {
    console.log('None!');
  } else {
    errors.forEach((e, i) => console.log(`  ${i+1}. ${e.slice(0, 200)}`));
  }

  await browser.close();
  console.log('\nDone! Screenshots in ./test-screenshots/');
}

run().catch(console.error);
