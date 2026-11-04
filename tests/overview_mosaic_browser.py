"""The board's three states and its colour hierarchy, against the workflow fixture. Overview: all stages collapsed
into one proportional mosaic, each tile in its stage's colour, more transparent than when open. Focus: one stage
open, the others a neutral mosaic. Popup: Expand section. Job counts
are produced by rewriting the host's real response in the browser, so the real page draws every layout. Read-only.
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/overview_mosaic_browser.py OUTPUT_DIR [BASE_URL]"""
import copy, math, os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
STAGES = ['available', 'in-production', 'ready', 'shipped']
BOARD = '#host-jobs-board'
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
def weight(n): return 1 if n == 0 else min(9, 1.6 + 1.5 * math.log2(n + 1))

DISTRIBUTIONS = {'spread': [30, 10, 3, 1], 'example': [12, 18, 4, 2], 'with-empty': [0, 1, 3, 30], 'sparse': [0, 1, 0, 0], 'even': [3, 3, 3, 3], 'large': [40, 35, 30, 60], 'one-heavy': [0, 0, 0, 30], 'few': [2, 4, 0, 1], 'one-empty': [2, 3, 0, 2]}

def session(browser, counts=None, who='host', w=1440, h=900, theme='light', motion='no-preference', touch=False):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme, reduced_motion=motion, has_touch=touch, is_mobile=touch)
    assert ctx.request.post(BASE + '/api/auth/login', data={'email': who + '@example.org', 'password': 'TestPassword2026'}).ok
    if counts:
        def rewrite(route):
            response = route.fetch(); data = response.json(); groups = data['scopes']['active']['groups']
            templates = {g['key']: next((j for j in data['items'] if j['status'] in g['statuses']), data['items'][0]) for g in groups}
            items, next_id = [], 900000
            for g, n in zip(groups, counts):
                g['count'] = n
                for k in range(n):
                    item = copy.deepcopy(templates[g['key']]); item['id'] = next_id; next_id += 1; item['status'] = g['statuses'][0]
                    item['item']['title'] = f'{g["key"]} rack {k + 1:03d}'; items.append(item)
            data['items'] = items; data['total'] = data['per_page'] = len(items); data['scopes']['active']['total'] = len(items)
            route.fulfill(response=response, json=data)
        ctx.route(re.compile(r'/api/host/jobs\?scope=active$'), rewrite)
    page = ctx.new_page(); page.api = []
    page.on('pageerror', lambda e: errors.append(f'{w} {theme}: {e}'))
    page.on('console', lambda m: m.type == 'error' and errors.append(f'{w} {theme}: {m.text}'))
    page.on('dialog', lambda d: (errors.append('native dialog: ' + d.message), d.dismiss()))
    page.on('request', lambda r: r.resource_type in ('fetch', 'xhr', 'document') and page.api.append(r.url))
    return ctx, page
def settled(page): page.wait_for_function("!document.querySelector('.ws-main[aria-busy], #bo-results[aria-busy=true]')")
def load(page, group='', board=BOARD, base='host/jobs'):
    page.goto(BASE + f'/#{base}' + (('&' if '?' in base else '?') + f'group={group}' if group else '')); page.wait_for_selector(board); settled(page)

OVERVIEW = """(board) => {
  const b = document.querySelector(board), m = b.querySelector('.sb-mosaic'), r = e => e.getBoundingClientRect(), mr = r(m);
  const tiles = [...m.children].map(t => { const x = r(t), title = t.querySelector('.sb-title'), tr = r(title), peek = t.querySelector('.sb-peek'), count = t.querySelector('.sb-head .segment-count'), cr = r(count), s = getComputedStyle(t);
    const broken = title.textContent.split(' ').some(w => { const n = title.firstChild, at = title.textContent.indexOf(w), g = document.createRange(); g.setStart(n, at); g.setEnd(n, at + w.length); return g.getClientRects().length > 1; });
    return {stage:t.dataset.stage, count:+t.dataset.count, shown:+t.querySelector('.sb-head [data-sb-count]').textContent, x:x.left, y:x.top, w:x.width, h:x.height, right:x.right, bottom:x.bottom, broken,
      fits:tr.bottom <= x.bottom + .5 && tr.right <= x.right + .5 && title.scrollWidth <= title.clientWidth + 1 && cr.bottom <= x.bottom + .5 && cr.right <= x.right + .5 && count.checkVisibility(),
      overlap:cr.left < tr.right - 1 && cr.right > tr.left + 1 && cr.top < tr.bottom - 1 && cr.bottom > tr.top + 1,
      peekOk:!peek?.checkVisibility() || r(peek).bottom <= x.bottom + .5, thumbs:[...t.querySelectorAll('.sb-peek-item')].filter(e => e.checkVisibility() && r(e).bottom <= r(peek).bottom + 1 && r(e).right <= x.right).length,
      look:[s.boxShadow, s.borderTopWidth, s.borderTopLeftRadius, getComputedStyle(title).fontSize, getComputedStyle(title).fontWeight, getComputedStyle(count).fontSize].join('|'), expand:t.querySelector('[data-sb-expand]').checkVisibility(), expanded:t.querySelector('.sb-head').getAttribute('aria-expanded'), transform:s.transform}; });
  return {board:b.clientWidth, overview:b.classList.contains('is-overview'), open:b.dataset.open, openCount:b.querySelectorAll('.sb-col.is-open').length, mainCols:b.querySelector('.sb-main').children.length, mosaic:{x:mr.left, y:mr.top, w:mr.width, h:mr.height, right:mr.right, bottom:mr.bottom}, tiles,
    pills:[...b.querySelectorAll('.sb-pills .chip')].filter(c => c.checkVisibility()).length, overflow:document.documentElement.scrollWidth - innerWidth, running:document.getAnimations().filter(a => a.playState === 'running' && !(a instanceof CSSAnimation)).length};
}"""
def check_overview(page, counts, label, board=BOARD):
    s = page.evaluate(OVERVIEW, board); tiles = s['tiles']
    ok(s['overview'] and s['open'] == 'none' and s['openCount'] == 0 and s['mainCols'] == 0 and len(tiles) == len(counts), f'{label}: no stage open; every stage is a tile')
    ok(all(not t['expand'] for t in tiles) and all(t['expanded'] == 'false' for t in tiles), f'{label}: no Expand section on any tile')
    ok([t['stage'] for t in tiles] == STAGES if len(tiles) == 4 else True, f'{label}: tiles keep the workflow order')
    overlap = [(a['stage'], b['stage']) for i, a in enumerate(tiles) for b in tiles[i + 1:] if min(a['right'], b['right']) - max(a['x'], b['x']) > 1 and min(a['bottom'], b['bottom']) - max(a['y'], b['y']) > 1]
    area = sum(t['w'] * t['h'] for t in tiles) / (s['mosaic']['w'] * s['mosaic']['h'])
    inside = all(t['x'] >= s['mosaic']['x'] - .5 and t['right'] <= s['mosaic']['right'] + .5 and t['y'] >= s['mosaic']['y'] - .5 and t['bottom'] <= s['mosaic']['bottom'] + .5 for t in tiles)
    ok(not overlap and inside and area >= .9, f'{label}: one unified grid, no overlap and no holes ({area:.0%} filled) {overlap}')
    sizes = {t['stage']: t['w'] * t['h'] for t in tiles}; total = sum(sizes.values()); weights = {t['stage']: weight(t['shown']) for t in tiles}; all_weight = sum(weights.values())
    smallest = min(sizes.values()); above = [k for k in sizes if sizes[k] > smallest * 1.1]
    ok(not above or max(sizes[k] / weights[k] for k in above) / min(sizes[k] / weights[k] for k in above) < 1.25, f'{label}: above the minimum share, areas follow their bounded weights { {k: round(v / total, 2) for k, v in sizes.items()} }')
    limit = 360 if s['board'] >= 780 else 420 if s['board'] >= 520 else 520
    ok(s['mosaic']['h'] <= limit + 1, f'{label}: compact: {s["mosaic"]["h"]:.0f} px tall, at most {limit}')
    empty_only = all(t['shown'] == 0 for t in tiles)
    ok(empty_only or s['mosaic']['h'] <= max(100, 34 * all_weight), f'{label}: its height follows the workload, so few items never make a tall mosaic ({s["mosaic"]["h"]:.0f} px for weight {all_weight:.1f})')
    ok(all(sizes[a['stage']] >= sizes[b['stage']] * .93 for a in tiles for b in tiles if a['shown'] > b['shown']), f'{label}: more elements, more area')
    ok(max(sizes.values()) / min(sizes.values()) < 10.5, f'{label}: bounded, not linear (largest / smallest {max(sizes.values()) / min(sizes.values()):.1f})')
    ok(all(t['w'] >= 88 and t['h'] >= 72 for t in tiles), f'{label}: every tile keeps a usable minimum { [(round(t["w"]), round(t["h"])) for t in tiles] }')
    ok(all(t['fits'] and not t['overlap'] and not t['broken'] and t['peekOk'] for t in tiles), f'{label}: names, counts and previews fit; no word broken; nothing overlaps')
    ok(len({t['look'] for t in tiles}) == 1, f'{label}: all tiles are at one level: same type, border and no lift')
    ok(s['overflow'] <= 0, f'{label}: no page overflow')
    return s

# Colour measured as drawn: composite over the page, then chroma, difference from the page, and text contrast.
LOOK = """(board) => {
  const parse = v => { const n = v.match(/-?[\\d.]+(?:e-?\\d+)?/g).map(Number); return v.startsWith('color(') ? {c:n.slice(0, 3).map(x => x * 255), a:n[3] ?? 1} : {c:n.slice(0, 3), a:n[3] ?? 1}; };
  const over = (top, under) => { const t = parse(top); return t.c.map((x, i) => x * t.a + under[i] * (1 - t.a)); };
  const lum = c => { const f = c.map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * f[0] + .7152 * f[1] + .0722 * f[2]; };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const chroma = c => Math.max(...c) - Math.min(...c), diff = (a, b) => Math.max(...a.map((v, i) => Math.abs(v - b[i])));
  const pageBg = over(getComputedStyle(document.body).backgroundColor, [255, 255, 255]), b = document.querySelector(board);
  const measure = col => { const s = getComputedStyle(col), bg = over(s.backgroundColor, pageBg), top = col.querySelector('.sb-top'), band = over(getComputedStyle(top).backgroundColor, bg), border = over(s.borderTopColor, pageBg), title = col.querySelector('.sb-title'), count = col.querySelector('.sb-head .segment-count'), icon = col.querySelector('.sb-icon'), hint = col.querySelector('.sb-hint');
    const countBg = over(getComputedStyle(count).backgroundColor, band), thumb = col.querySelector('.sb-peek-item:not([hidden]) .line-thumb');
    return {stage:col.dataset.stage, chroma:chroma(band), fromPage:diff(band, pageBg), bodyFromPage:diff(bg, pageBg), border:diff(border, pageBg), borderChroma:chroma(border), shadow:s.boxShadow !== 'none', title:parseFloat(getComputedStyle(title).fontSize), weight:+getComputedStyle(title).fontWeight, count:parseFloat(getComputedStyle(count).fontSize), icon:icon.getBoundingClientRect().width, iconBg:parse(getComputedStyle(icon).backgroundColor).a, iconColor:chroma(parse(getComputedStyle(icon).color).c),
      titleContrast:contrast(parse(getComputedStyle(title).color).c, band), countContrast:contrast(parse(getComputedStyle(count).color).c, countBg), hintContrast:hint?.checkVisibility() ? contrast(over(getComputedStyle(hint).color, band), band) : 99, thumb:thumb?.checkVisibility() ? thumb.getBoundingClientRect().width : 0,
      dot:(() => { const d = getComputedStyle(icon, '::after'); return d.content === 'none' ? 0 : parseFloat(d.width); })(), dotColor:(() => { const d = getComputedStyle(icon, '::after'); return d.content === 'none' ? '' : d.backgroundColor; })(), tone:getComputedStyle(col).getPropertyValue('--tone-fg').trim()}; };
  return {pageChroma:chroma(pageBg), open:measure(b.querySelector('.sb-col.is-open')), rest:[...b.querySelectorAll('.sb-mosaic > .sb-col')].map(measure), sampleThumb:(() => { const i = b.querySelector('.sb-col.is-open .line-thumb img'); return i ? getComputedStyle(i).filter : ''; })(), panelThumb:(() => { const i = b.querySelector('.sb-mosaic .sb-peek .line-thumb img'); return i ? getComputedStyle(i).filter : ''; })()};
}"""
def check_hierarchy(page, label, board=BOARD):
    s = page.evaluate(LOOK, board); o = s['open']; rest = s['rest']
    # Saturation: a panel may only carry the page's own hue; the stage's colour is reserved for the open header.
    # (Dark surfaces sit about 2/255 above the page's chroma: imperceptible, hence the small allowance.)
    ok(all(r['chroma'] <= max(o['chroma'], s['pageChroma']) + 3 for r in rest), f'{label}: no collapsed panel is more saturated than the open header or the page (open {o["chroma"]:.0f}, page {s["pageChroma"]:.0f}, panels {[round(r["chroma"]) for r in rest]})')
    ok(all(r['bodyFromPage'] < o['bodyFromPage'] for r in rest), f'{label}: the open stage stands out from the page more than any panel (open {o["bodyFromPage"]:.0f}, panels {[round(r["bodyFromPage"]) for r in rest]})')
    ok(all(r['border'] < o['border'] for r in rest), f'{label}: subtler borders ({o["border"]:.0f} vs {[round(r["border"]) for r in rest]})')
    ok(o['shadow'] and not any(r['shadow'] for r in rest), f'{label}: only the open stage is lifted')
    ok(all(r['title'] < o['title'] and r['count'] <= o['count'] + 1 and r['icon'] < o['icon'] for r in rest), f'{label}: bigger title and icon on the open stage ({o["title"]} vs {rest[0]["title"]} px)')
    ok(all(r['iconBg'] == 0 for r in rest) and all(r['dot'] and r['dot'] <= 8 for r in rest), f'{label}: panels carry no tinted icon tile, just one small status dot')
    ok(not o['dot'], f'{label}: the open stage has its colour in the header instead of a dot')
    ok(all(r['thumb'] == 0 or r['thumb'] <= 30 or r['thumb'] <= 40 for r in rest) and (not s['panelThumb'] or 'saturate' in s['panelThumb']) and s['sampleThumb'] in ('none', ''), f'{label}: full-colour previews open, restrained previews collapsed')
    ok(o['titleContrast'] >= 4.5 and o['countContrast'] >= 4.5 and o['hintContrast'] >= 4.5, f'{label}: open stage text contrast {o["titleContrast"]:.1f} / {o["countContrast"]:.1f} / {o["hintContrast"]:.1f}')
    ok(all(r['titleContrast'] >= 4.5 and r['countContrast'] >= 4.5 and r['hintContrast'] >= 4.5 for r in rest), f'{label}: panel text contrast {[round(min(r["titleContrast"], r["countContrast"], r["hintContrast"]), 1) for r in rest]}')
    return s

TONE = """(board) => {
  const parse = v => { const n = v.match(/-?[\\d.]+(?:e-?\\d+)?/g).map(Number); return v.startsWith('color(') ? {c:n.slice(0, 3).map(x => x * 255), a:n[3] ?? 1} : {c:n.slice(0, 3), a:n[3] ?? 1}; };
  const over = (top, under) => { const t = parse(top); return t.c.map((x, i) => x * t.a + under[i] * (1 - t.a)); };
  const lum = c => { const f = c.map(v => { v /= 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }); return .2126 * f[0] + .7152 * f[1] + .0722 * f[2]; };
  const contrast = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + .05) / (Math.min(x, y) + .05); };
  const page = over(getComputedStyle(document.body).backgroundColor, [255, 255, 255]), b = document.querySelector(board);
  return Object.fromEntries([...b.querySelectorAll('.sb-col')].map(col => { const open = col.classList.contains('is-open'), s = getComputedStyle(col), el = open ? col.querySelector('.sb-top') : col, raw = parse(getComputedStyle(el).backgroundColor), bg = over(getComputedStyle(el).backgroundColor, open ? over(s.backgroundColor, page) : page);
    const title = col.querySelector('.sb-title'), count = col.querySelector('.sb-head .segment-count'), hint = col.querySelector('.sb-hint'), icon = col.querySelector('.sb-icon');
    return [col.dataset.stage, {open, alpha:raw.a, bg, fromPage:Math.max(...bg.map((v, i) => Math.abs(v - page[i]))), warm:bg[0] - bg[2], tone:s.getPropertyValue('--tone-bg').trim(), icon:getComputedStyle(icon).color, toneFg:(() => { const e = document.createElement('i'); e.style.color = 'var(--tone-fg)'; col.append(e); const c = getComputedStyle(e).color; e.remove(); return c; })(), dot:getComputedStyle(icon, '::after').content,
      title:contrast(parse(getComputedStyle(title).color).c, bg), count:contrast(parse(getComputedStyle(count).color).c, over(getComputedStyle(count).backgroundColor, bg)), hint:hint?.checkVisibility() ? contrast(over(getComputedStyle(hint).color, bg), bg) : 99}]; }));
}"""
def check_tones(page, label, board=BOARD):
    # The tiles, then each stage's open header: same colour family, the tile clearly more transparent.
    tiles = page.evaluate(TONE, board)
    ok(all(t['title'] >= 4.5 and t['count'] >= 4.5 and t['hint'] >= 4.5 for t in tiles.values()), f'{label}: tile text stays readable { {k: round(min(t["title"], t["count"], t["hint"]), 1) for k, t in tiles.items()} }')
    ok(all(t['icon'] == t['toneFg'] and t['dot'] == 'none' for t in tiles.values()), f'{label}: each icon in its stage colour; no separate dot')
    for key, tile in tiles.items():
        page.locator(f'{board} .sb-mosaic [data-sb-open="{key}"]').click(); page.mouse.move(2, 2); page.wait_for_timeout(420)
        head = page.evaluate(TONE, board)[key]
        ok(head['open'] and head['tone'] == tile['tone'] and tile['alpha'] < head['alpha'], f'{label}, {key}: the tile has the open header’s colour, more transparent (alpha {tile["alpha"]:.2f} vs {head["alpha"]:.2f})')
        page.locator(f'{board} .sb-col.is-open .sb-head').click(); page.mouse.move(2, 2); page.wait_for_timeout(420)
    return tiles

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)

    # ---------- Collapsing, expanding, switching ----------
    counts = DISTRIBUTIONS['example']
    ctx, p = session(browser, counts); load(p, 'in-production'); p.evaluate('window.__same = 1'); p.api.clear()
    search_top = p.evaluate("document.querySelector('[data-filter-list]').getBoundingClientRect().top"); scroll = p.evaluate('scrollY')
    ok(p.locator('.sb-col.is-open .sb-chevron').is_visible() and p.locator('.sb-col.is-open .sb-head').get_attribute('title') == 'Collapse this stage', 'the open header says it collapses')
    p.locator('.sb-col.is-open .sb-head').click(); p.mouse.move(2, 2); p.wait_for_timeout(420)
    s = check_overview(p, counts, 'header click')
    ok(p.url.endswith('#host/jobs?group=none') and p.evaluate("sessionStorage.getItem('openlabs-host-stage')") == 'none', 'all collapsed is remembered in the address and the session')
    ok(p.evaluate("document.activeElement.matches('.sb-mosaic [data-sb-open=\"in-production\"]')"), 'focus stays on the stage that collapsed')
    ok(s['running'] == 0 and all(t['transform'] == 'none' for t in s['tiles']), 'the transition ends cleanly')
    p.screenshot(path=str(OUT / 'overview-example-1440-light.png'))
    p.locator('.sb-mosaic [data-sb-open="ready"]').click(); p.wait_for_timeout(420)
    ok(p.locator('.sb-col.is-open').get_attribute('data-stage') == 'ready' and p.locator('.sb-main .sb-col').count() == 1 and p.locator('.sb-mosaic > .sb-col').count() == 3 and not p.evaluate("document.querySelector('#host-jobs-board').classList.contains('is-overview')"), 'clicking a tile opens that stage')
    ok(not p.evaluate("document.querySelector('#section-dialog')?.open") and p.locator('.sb-col.is-open [data-sb-expand]').is_visible(), 'it opens in the board, not the popup; Expand section is there')
    p.locator('.sb-mosaic [data-sb-open="shipped"]').click(); p.wait_for_timeout(420)
    ok(p.locator('.sb-col.is-open').get_attribute('data-stage') == 'shipped' and p.url.endswith('group=shipped'), 'clicking another section switches the open stage')
    p.locator('.sb-col.is-open [data-sb-expand]').click(); p.wait_for_selector('#section-dialog[open]')
    ok(p.locator('#section-dialog #ss-title').inner_text() == 'Awaiting buyer' and p.locator('#section-dialog [data-job-card]').count() == counts[3], 'Expand section opens the existing popup, with every item')
    p.locator('#section-dialog [data-ss-close]').click(); p.wait_for_selector('#section-dialog', state='hidden')
    ok(p.evaluate('window.__same') == 1 and not [u for u in p.api if '/api/' in u], f'no reload and no request across all of it {p.api}')
    ok(abs(p.evaluate("document.querySelector('[data-filter-list]').getBoundingClientRect().top") - search_top) < 1 and p.evaluate('scrollY') == scroll, 'nothing above the board moved; no scroll jump')

    # Keyboard.
    p.evaluate("document.querySelector('.sb-col.is-open .sb-head').focus()"); p.keyboard.press('Enter'); p.wait_for_timeout(420)
    ok(p.evaluate("document.querySelector('#host-jobs-board').dataset.open") == 'none' and p.evaluate("document.activeElement.matches('.sb-mosaic .sb-head')"), 'keyboard: Enter on the open header collapses; focus kept')
    p.keyboard.press('Space'); p.wait_for_timeout(420)
    ok(p.evaluate("document.querySelector('#host-jobs-board').dataset.open") == 'shipped', 'keyboard: Space on a tile opens it')
    p.keyboard.press('Enter'); p.wait_for_timeout(420)

    # Refresh and return keep the explicit state; nothing reopens by itself.
    p.reload(); p.wait_for_selector(BOARD); settled(p); check_overview(p, counts, 'after a reload')
    p.goto(BASE + '/#host'); p.wait_for_selector('.ho-stats'); p.goto(BASE + '/#host/jobs'); p.wait_for_selector(BOARD); settled(p)
    ok(p.locator(BOARD).get_attribute('data-open') == 'none', 'returning to the page keeps it collapsed')
    p.go_back(); p.wait_for_selector('.ho-stats'); p.go_forward(); p.wait_for_selector(BOARD); settled(p)
    ok(p.locator(BOARD).get_attribute('data-open') == 'none', 'Back and Forward keep it collapsed')
    p.goto(BASE + '/#host/jobs?group=ready'); p.wait_for_selector(BOARD + '[data-open="ready"]')
    ok(True, 'a link to a stage still opens that stage')
    ctx.close()
    ctx, p = session(browser, counts); load(p, 'none')
    ok(p.locator(BOARD).get_attribute('data-open') == 'none', 'a fresh session with the address opens collapsed')
    ctx.close()
    ctx, p = session(browser, counts); load(p)
    ok(p.locator(BOARD).get_attribute('data-open') == 'available', 'a first visit, with nothing remembered, opens the first stage with work')
    ctx.close()

    # ---------- Search: counts and proportions follow; survives switching state ----------
    ctx, p = session(browser, counts); load(p, 'none'); p.evaluate('window.__same = 1'); p.api.clear()
    before = {t['stage']: t['w'] * t['h'] for t in p.evaluate(OVERVIEW, BOARD)['tiles']}
    field = '[data-filter-list="host-jobs-search"]'
    p.fill(field, 'ready rack'); p.wait_for_timeout(120)
    s = p.evaluate(OVERVIEW, BOARD); sizes = {t['stage']: t['w'] * t['h'] for t in s['tiles']}
    ok({t['stage']: t['shown'] for t in s['tiles']} == {'available': 0, 'in-production': 0, 'ready': 4, 'shipped': 0}, f'search: tile counts become matches {[(t["stage"], t["shown"]) for t in s["tiles"]]}')
    ok(sizes['ready'] == max(sizes.values()) and sizes['ready'] / sum(sizes.values()) > before['ready'] / sum(before.values()), 'search: the proportions follow: the only stage with matches now takes the most room')
    p.screenshot(path=str(OUT / 'overview-search-1440-light.png'))
    p.locator('.sb-mosaic [data-sb-open="ready"]').click(); p.wait_for_timeout(420)
    ok(p.input_value(field) == 'ready rack' and p.locator('.sb-col.is-open [data-job-card]:visible').count() == 4, 'expanding keeps the search and its results')
    p.locator('.sb-mosaic [data-sb-open="available"]').click(); p.wait_for_timeout(420)
    ok(p.locator('.sb-col.is-open .sb-nomatch').is_visible(), 'a stage with no match says so')
    p.locator('.sb-col.is-open .sb-head').click(); p.mouse.move(2, 2); p.wait_for_timeout(420); p.fill(field, ''); p.wait_for_timeout(120)
    s = check_overview(p, counts, 'search cleared')
    ok({t['stage']: t['shown'] for t in s['tiles']} == dict(zip(STAGES, counts)) and p.evaluate('window.__same') == 1 and not [u for u in p.api if '/api/' in u], 'clearing restores counts and proportions, with no request')
    ctx.close()

    # ---------- Uneven distributions (0, 1, 3, 10, 30+) ----------
    for name, dist in DISTRIBUTIONS.items():
        ctx, p = session(browser, dist); load(p, 'none'); p.wait_for_timeout(200)
        check_overview(p, dist, name); p.screenshot(path=str(OUT / f'overview-{name}-1440.png'))
        ctx.close()

    # ---------- Hierarchy, Bright and Dark, every tone of Printing jobs ----------
    for theme in ('light', 'dark'):
        ctx, p = session(browser, DISTRIBUTIONS['spread'], theme=theme); load(p, 'available')
        for stage in STAGES:
            if p.locator(BOARD).get_attribute('data-open') != stage: p.locator(f'.sb-mosaic [data-sb-open="{stage}"]').click(); p.wait_for_timeout(420)
            p.mouse.move(2, 2); p.wait_for_timeout(180)
            check_hierarchy(p, f'{theme}, {stage} open')
        p.screenshot(path=str(OUT / f'focus-spread-1440-{theme}.png'))
        ctx.close()

    # ---------- All collapsed: each tile in its stage's colour, more transparent than when open ----------
    for theme in ('light', 'dark'):
        ctx, p = session(browser, DISTRIBUTIONS['spread'], theme=theme); load(p, 'none'); p.mouse.move(2, 2); p.wait_for_timeout(300)
        tiles = check_tones(p, f'{theme} overview')
        if theme == 'light': ok(tiles['available']['warm'] > tiles['in-production']['warm'] + 5, f'light overview: Available is visibly amber, In production blue ({tiles["available"]["warm"]:.0f} vs {tiles["in-production"]["warm"]:.0f})')
        ok(len({t['tone'] for t in tiles.values()}) >= 2, f'{theme} overview: stages keep their different colours')
        # At rest the tile is faint; under the mouse it gains a little colour, still lighter than the open header.
        alpha = lambda key: p.evaluate("k => { const n = getComputedStyle(document.querySelector(`#host-jobs-board .sb-col[data-stage=\"${k}\"]`)).backgroundColor.match(/-?[\\d.]+/g).map(Number); return n[3] ?? 1; }", key)
        rest = alpha('available'); p.locator('.sb-mosaic [data-sb-open="available"]').hover(); p.wait_for_timeout(260); hover = alpha('available'); p.mouse.move(2, 2); p.wait_for_timeout(260)
        ok(hover > rest and alpha('available') == rest, f'{theme} overview: hovering a tile adds a little colour (alpha {rest:.2f} → {hover:.2f}), and it goes back')
        GEOMETRY = "[...document.querySelectorAll('#host-jobs-board .sb-mosaic > .sb-col')].map(t => { const r = t.getBoundingClientRect(); return {stage:t.dataset.stage, x:r.left, y:r.top, right:r.right, bottom:r.bottom, w:r.width, h:r.height, z:getComputedStyle(t).zIndex, shadow:getComputedStyle(t).boxShadow, transform:getComputedStyle(t).transform}; })"
        at_rest = {t['stage']: t for t in p.evaluate(GEOMETRY)}
        for key in STAGES:
            p.locator(f'.sb-mosaic [data-sb-open="{key}"]').hover(); p.wait_for_timeout(260)
            now = {t['stage']: t for t in p.evaluate(GEOMETRY)}; t = now[key]; r = at_rest[key]
            grow = max(t['w'] - r['w'], t['h'] - r['h']); touching = [o for o in now.values() if o['stage'] != key and min(t['right'], o['right']) - max(t['x'], o['x']) > .5 and min(t['bottom'], o['bottom']) - max(t['y'], o['y']) > .5]
            ok(0 < grow <= 11 and t['w'] / r['w'] <= 1.015 and not touching and t['shadow'] != 'none', f'{theme} overview, {key}: the hover is a hint of a pop (+{t["w"] - r["w"]:.1f} × +{t["h"] - r["h"]:.1f} px of {r["w"]:.0f} × {r["h"]:.0f}), lifted, never touching a neighbour')
            ok(all(now[k]['x'] == at_rest[k]['x'] and now[k]['w'] == at_rest[k]['w'] for k in now if k != key), f'{theme} overview, {key}: the other tiles do not move')
        p.locator('.sb-mosaic [data-sb-open="available"]').hover(); p.wait_for_timeout(260); p.screenshot(path=str(OUT / f'overview-hover-{theme}.png')); p.mouse.move(2, 2); p.wait_for_timeout(260)
        ok(all(t['transform'] == 'none' and t['shadow'] == 'none' for t in p.evaluate(GEOMETRY)), f'{theme} overview: moving away settles every tile back')
        # Keyboard focus shows the same pop; clicking with the mouse does not leave a tile raised.
        p.evaluate("document.querySelector('[data-filter-list]').focus()"); p.keyboard.press('Tab'); p.wait_for_timeout(240)
        ok(p.evaluate("(() => { const t = document.activeElement.closest('.sb-col'); return !!t && getComputedStyle(t).transform !== 'none'; })()"), f'{theme} overview: keyboard focus lifts a tile too')
        p.evaluate("document.activeElement.blur()"); p.wait_for_timeout(240)
        p.screenshot(path=str(OUT / f'overview-tones-{theme}.png'))
        p.locator('.sb-mosaic [data-sb-open="in-production"]').click(); p.mouse.move(2, 2); p.wait_for_timeout(420)
        check_hierarchy(p, f'{theme}, opened from the overview')   # the side panels go back to neutral
        ctx.close()

    # ---------- Reduced motion ----------
    ctx, p = session(browser, counts, motion='reduce'); load(p, 'none'); p.locator('.sb-mosaic [data-sb-open="available"]').hover(); p.wait_for_timeout(120)
    ok(p.evaluate("getComputedStyle(document.querySelector('.sb-mosaic [data-stage=\"available\"]')).transform") == 'none', 'reduced motion: no pop on hover')
    p.mouse.move(2, 2); p.locator('.sb-mosaic [data-sb-open="in-production"]').click(); p.wait_for_timeout(120)
    ok(p.evaluate("() => { document.querySelector('.sb-col.is-open .sb-head').click(); return document.getAnimations().filter(a => a.effect?.target?.matches?.('.sb-col')).length; }") == 0, 'reduced motion: the change is instant')
    ctx.close()
    ctx, p = session(browser, counts); load(p, 'in-production')
    ok(p.evaluate("() => { document.querySelector('.sb-col.is-open .sb-head').click(); return document.getAnimations().filter(a => a.effect?.target?.matches?.('.sb-col')).length; }") > 0, 'otherwise the panels slide')
    ctx.close()

    # ---------- Every width, Bright and Dark ----------
    for w, h, touch in ((320, 700, True), (390, 844, True), (768, 1024, True), (1024, 768, False), (1280, 800, False), (1440, 900, False)):
        for theme in ('light', 'dark'):
            for name in ('spread', 'with-empty'):
                ctx, p = session(browser, DISTRIBUTIONS[name], w=w, h=h, theme=theme, touch=touch); load(p, 'none'); p.wait_for_timeout(150)
                s = check_overview(p, DISTRIBUTIONS[name], f'{w} {theme} {name}')
                ok(s['pills'] == 0, f'{w} {theme} {name}: the tiles replace the stage pills')
                ok(all(t['h'] >= 44 and t['w'] >= 44 for t in s['tiles']), f'{w} {theme} {name}: comfortable targets')
                if name == 'spread': p.wait_for_timeout(400); p.screenshot(path=str(OUT / f'overview-{w}-{theme}.png'))
                p.locator(f'{BOARD} .sb-mosaic [data-sb-open="in-production"]').click(); p.wait_for_timeout(420)
                visible = p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-col')].filter(c => c.checkVisibility()).map(c => c.dataset.stage)")
                pills = p.evaluate("[...document.querySelectorAll('#host-jobs-board .sb-pills .chip')].filter(c => c.checkVisibility()).length")
                narrow = w < 700
                ok(pills == (4 if narrow else 0) and (visible == ['in-production'] if narrow else 'in-production' in visible and len(visible) == 4), f'{w} {theme} {name}: {"its details below the stage pills" if narrow else "the open stage beside the mosaic"} {visible}')
                ok(p.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0, f'{w} {theme} {name}: no page overflow when open')
                if not narrow: p.mouse.move(2, 2); p.wait_for_timeout(180); check_hierarchy(p, f'{w} {theme} {name}')
                if name == 'spread': p.wait_for_timeout(400); p.screenshot(path=str(OUT / f'focus-{w}-{theme}.png'))
                if narrow:
                    p.locator(f'{BOARD} .sb-pills [data-sb-open="in-production"]').click(); p.wait_for_timeout(350)
                    ok(p.locator(BOARD).get_attribute('data-open') == 'none' and p.evaluate("document.activeElement.matches('.sb-mosaic [data-sb-open=\"in-production\"]')"), f'{w} {theme} {name}: the pressed pill collapses too; focus kept')
                else:
                    p.locator(f'{BOARD} .sb-col.is-open .sb-head').click(); p.wait_for_timeout(420)
                    ok(p.locator(BOARD).get_attribute('data-open') == 'none', f'{w} {theme} {name}: the header collapses')
                ctx.close()

    # ---------- The same model on the other boards ----------
    for who, base, board, stage in (('buyer', 'orders', '#bo-board', 'in-progress'), ('admin', 'admin/orders', '#admin-orders-board', 'in-progress'), ('admin', 'admin/orders?scope=history', '#admin-orders-board', 'completed'), ('host', 'host/jobs?scope=history', '#job-history-board', 'completed'), ('buyer', 'orders?scope=history', '#bo-history-board', 'completed')):
        for theme in ('light', 'dark'):
            ctx, p = session(browser, who=who, theme=theme); load(p, stage, board, base)
            label = f'{base} {theme}'
            check_hierarchy(p, label, board); p.api.clear()
            p.locator(f'{board} .sb-col.is-open .sb-head').click(); p.mouse.move(2, 2); p.wait_for_timeout(420)
            s = p.evaluate(OVERVIEW, board)
            ok(s['overview'] and s['openCount'] == 0 and all(not t['expand'] and t['fits'] for t in s['tiles']) and len({t['look'] for t in s['tiles']}) == 1 and s['overflow'] <= 0, f'{label}: collapses into one mosaic of equal tiles')
            ok('group=none' in p.url and not [u for u in p.api if '/api/' in u], f'{label}: remembered, with no request')
            if theme == 'light': p.screenshot(path=str(OUT / f'overview-{board[1:]}-{"history" if "history" in base else "active"}.png'))
            p.reload(); p.wait_for_selector(board); settled(p)
            ok(p.locator(board).get_attribute('data-open') == 'none', f'{label}: a reload keeps it')
            p.locator(f'{board} .sb-mosaic [data-sb-open="{stage}"]').click(); p.wait_for_timeout(420)
            ok(p.locator(board).get_attribute('data-open') == stage and p.locator(f'{board} .sb-col.is-open [data-sb-expand]').count() == 1, f'{label}: a tile opens its stage')
            ctx.close()
    ok(not errors, 'no page errors: ' + '; '.join(errors[:5]))
    browser.close()
print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
