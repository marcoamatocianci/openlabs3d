// Runs one of the `async (page) => {...}` browser scripts in this folder without the Playwright MCP:
//   PLAYWRIGHT_MODULE=/path/to/node_modules/playwright CHROME=/path/to/chrome node tests/run_playwright_script.js tests/<file>.js
const fs = require('fs');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
(async () => {
  const file = process.argv[2], source = fs.readFileSync(file, 'utf8').trim().replace(/;\s*$/, '');
  const browser = await chromium.launch({executablePath: process.env.CHROME || undefined});
  const page = await (await browser.newContext({viewport: {width: 1366, height: 900}})).newPage();
  const errors = []; page.on('pageerror', e => errors.push(String(e)));
  try {
    const result = await eval('(' + source + '\n)')(page);
    console.log('RESULT', JSON.stringify(result));
    if (errors.length) console.log('PAGE ERRORS', errors);
  } catch (e) { console.log('FAILED', e.message.split('\n').slice(0, 6).join('\n')); process.exitCode = 1; }
  finally { await browser.close(); }
})();
