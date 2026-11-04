"""Balanced mosaic, on Printing jobs: one large open stage, the other stages in a compact grid on the right, sized
and arranged by their job counts. Job distributions are produced by rewriting the host's real active-jobs
response in the browser (cloned jobs of the right statuses), so every layout is drawn by the real page.
Read-only against the workflow fixture:
    uv run --no-project --python 3.12 --with-requirements backend/requirements.txt python scripts/workflow_preview.py
    uv run --no-project --python 3.12 --with playwright python tests/mosaic_board_browser.py OUTPUT_DIR [BASE_URL]"""
import copy, os, re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
BASE = sys.argv[2] if len(sys.argv) > 2 else 'http://127.0.0.1:18102'
CHROME = os.environ.get('CHROME') or os.path.expanduser('~/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome')
STAGES = ['available', 'in-production', 'ready', 'shipped']
checks, errors = [], []
def ok(cond, msg):
    checks.append(bool(cond)); print(('PASS ' if cond else 'FAIL ') + msg, flush=True)
def tier(n): return 'xs' if n == 0 else 's' if n <= 2 else 'm' if n <= 5 else 'l' if n <= 10 else 'xl'

# Counts per stage, in workflow order: Available, In production, Ready to ship, Awaiting buyer.
DISTRIBUTIONS = {'all-empty': [0, 0, 0, 0], 'one-heavy': [14, 0, 0, 0], 'even': [3, 3, 3, 3],
                 'several-zero': [0, 1, 0, 8], 'mixed': [2, 3, 1, 8], 'small': [1, 2, 2, 1], 'diagram': [2, 8, 1, 1], 'capped': [40, 12, 1, 7]}

def session(browser, counts, w=1440, h=900, theme='light', motion='no-preference'):
    ctx = browser.new_context(viewport={'width': w, 'height': h}, color_scheme=theme, reduced_motion=motion)
    assert ctx.request.post(BASE + '/api/auth/login', data={'email': 'host@example.org', 'password': 'TestPassword2026'}).ok
    def rewrite(route):
        response = route.fetch(); data = response.json(); groups = data['scopes']['active']['groups']
        templates = {g['key']: next(j for j in data['items'] if j['status'] in g['statuses']) for g in groups}
        items, next_id = [], 900000
        for g, n in zip(groups, counts):
            g['count'] = n
            for _ in range(n):
                item = copy.deepcopy(templates[g['key']]); item['id'] = next_id; next_id += 1; items.append(item)
        data['items'] = items; data['total'] = data['per_page'] = len(items); data['scopes']['active']['total'] = len(items)
        route.fulfill(response=response, json=data)
    ctx.route(re.compile(r'/api/host/jobs\?scope=active$'), rewrite)
    page = ctx.new_page()
    page.on('pageerror', lambda e: errors.append(f'{w} {counts}: {e}'))
    page.on('console', lambda m: m.type == 'error' and errors.append(f'{w} {counts}: {m.text}'))
    page.requests = []
    page.on('request', lambda r: r.resource_type in ('fetch', 'xhr', 'document') and page.requests.append(r.url))
    return ctx, page

def load(page, stage=''):
    page.goto(BASE + '/#host/jobs' + (f'?group={stage}' if stage else ''))
    page.wait_for_selector('#host-jobs-board, .ws-main .empty-state'); page.wait_for_function("!document.querySelector('.ws-main[aria-busy]')")

STATE = """() => {
  const b = document.querySelector('#host-jobs-board'), main = b.querySelector('.sb-main'), mosaic = b.querySelector('.sb-mosaic'), r = e => e.getBoundingClientRect();
  const open = [...b.querySelectorAll('.sb-col.is-open')], mr = r(mosaic), tr = r(b.querySelector('.sb-track'));
  const clipped = e => e.scrollWidth > e.clientWidth + 1 || e.scrollHeight > e.clientHeight + 1;
  const boxes = [...mosaic.children].map(p => { const x = r(p), t = p.querySelector('.sb-title'), more = p.querySelector('.sb-peek-more'); return {
    stage:p.dataset.stage, count:+p.dataset.count, size:p.dataset.size, span:+p.dataset.span, x:x.left, y:x.top, w:x.width, h:x.height, right:x.right, bottom:x.bottom,
    clipped:clipped(p) || clipped(p.querySelector('.sb-head')), titleFits:t.checkVisibility() && t.scrollWidth <= t.clientWidth + 1,
    titleBroken:[...t.textContent.split(' ')].some(word => word.length > 3 && (() => { const range = document.createRange(); const node = t.firstChild; const start = t.textContent.indexOf(word); range.setStart(node, start); range.setEnd(node, start + word.length); return range.getClientRects().length > 1; })()),
    count:+p.dataset.count, shown:p.querySelector('.sb-head [data-sb-count]').textContent, countVisible:p.querySelector('.sb-head .segment-count').checkVisibility(),
    hint:p.querySelector('.sb-hint')?.checkVisibility() || false, thumbs:[...p.querySelectorAll('.sb-peek-item')].filter(e => e.checkVisibility()).length,
    more:more?.checkVisibility() ? +more.textContent.slice(1) : 0, transform:getComputedStyle(p).transform,
    peekRows:new Set([...p.querySelectorAll('.sb-peek > *')].filter(e => e.checkVisibility()).map(e => { const q = e.getBoundingClientRect(); return Math.round(q.top + q.height / 2); })).size}; });
  return {open:open.map(o => o.dataset.stage), openInMain:open.length === 1 && open[0].parentElement === main, order:[...mosaic.children].map(p => +p.dataset.index),
    share:r(main).width / tr.width, mainRight:r(main).right, main:{y:r(main).top, bottom:r(main).bottom}, mosaic:{x:mr.left, y:mr.top, w:mr.width, h:mr.height, right:mr.right, bottom:mr.bottom, visible:mosaic.checkVisibility()},
    maxHeight:parseFloat(getComputedStyle(mosaic).maxHeight),
    columns:getComputedStyle(mosaic).gridTemplateColumns.split(' ').length, boxes, boardOpen:b.dataset.open,
    expanded:Object.fromEntries([...b.querySelectorAll('.sb-head')].map(h => [h.dataset.sbOpen, h.getAttribute('aria-expanded')])),
    overflow:document.documentElement.scrollWidth - innerWidth, running:document.getAnimations().filter(a => a.playState === 'running').length};
}"""

def check_layout(page, counts, label):
    s = page.evaluate(STATE); boxes = s['boxes']
    open_key = s['open'][0] if s['open'] else None
    ok(len(s['open']) == 1 and s['openInMain'] and s['boardOpen'] == open_key, f'{label}: one open stage, in the main area')
    ok(s['order'] == sorted(s['order']) and len(boxes) == 3, f'{label}: the other three stages in workflow order {[b["stage"] for b in boxes]}')
    ok(.65 <= s['share'] <= .75, f'{label}: the open stage takes {s["share"]:.0%} of the board')
    ok(s['mosaic']['visible'] and s['mosaic']['x'] >= s['mainRight'], f'{label}: the mosaic sits on the right')
    ok(all(b['size'] == tier(counts[STAGES.index(b['stage'])]) for b in boxes), f'{label}: sizes follow the counts {[(b["stage"], b["count"], b["size"]) for b in boxes]}')
    ok(all(b['shown'] == str(b['count']) and b['countVisible'] for b in boxes), f'{label}: every panel shows its count')
    ok(all(b['titleFits'] and not b['titleBroken'] and not b['clipped'] for b in boxes), f'{label}: no clipped text, no word broken across lines')
    overlap = [(a['stage'], b['stage']) for i, a in enumerate(boxes) for b in boxes[i + 1:] if min(a['right'], b['right']) - max(a['x'], b['x']) > 1 and min(a['y'] + a['h'], b['y'] + b['h']) - max(a['y'], b['y']) > 1]
    inside = all(b['x'] >= s['mosaic']['x'] - .5 and b['right'] <= s['mosaic']['right'] + .5 and b['bottom'] <= s['mosaic']['bottom'] + .5 for b in boxes)
    ok(not overlap and inside, f'{label}: panels never overlap and stay inside the mosaic {overlap}')
    # Rows are always full: one panel across the grid, or two side by side of the same height.
    rows = {}
    for b in boxes: rows.setdefault(round(b['y']), []).append(b)
    full = all(abs(sum(b['w'] for b in row) + 8 * (len(row) - 1) - s['mosaic']['w']) < 2 and len({round(b['h']) for b in row}) == 1 for row in rows.values())
    ok(full, f'{label}: every mosaic row is filled, without holes ({s["columns"]} column{"s" if s["columns"] > 1 else ""})')
    small = [b['h'] for b in boxes if b['size'] == 'xs']; rest = [b['h'] for b in boxes if b['size'] != 'xs']
    ok(all(h <= 50 for h in small) and (not small or not rest or max(small) < min(rest)) and all(b['h'] >= 110 for b in boxes if b['size'] in ('l', 'xl')), f'{label}: empty stages are slim bars, 6+ jobs a large panel {[(b["size"], round(b["h"])) for b in boxes]}')
    # More work never means less room, and the scale is bounded: 40 jobs get less than 3× the room of 3.
    area = {b['stage']: b['w'] * b['h'] for b in boxes if b['size'] != 'xs'}
    ok(all(area[a['stage']] >= area[b['stage']] * .94 for a in boxes for b in boxes if a['size'] != 'xs' and b['size'] != 'xs' and a['count'] >= b['count'] + 3) and (len(area) < 2 or max(area.values()) / min(area.values()) < 3.2), f'{label}: busier stages take more of the mosaic, within bounds { {k: round(v) for k, v in area.items()} }')
    tops, bottoms = s['mosaic']['y'] - s['main']['y'], s['main']['bottom'] - s['mosaic']['bottom']
    ok(abs(tops) < 1.5 and (abs(bottoms) < 1.5 or s['mosaic']['h'] >= s['maxHeight'] - 1 or all(b['size'] == 'xs' for b in boxes)), f'{label}: the mosaic lines up with the open stage (top {tops:.0f}, bottom {bottoms:.0f}, height {s["mosaic"]["h"]:.0f} of at most {s["maxHeight"]:.0f})')
    limit = lambda b: 0 if b['size'] == 'xs' else 3 if b['span'] == 1 else 5
    ok(all(b['thumbs'] <= limit(b) and b['peekRows'] <= 1 and (b['size'] == 'xs' or b['thumbs'] + b['more'] == b['count']) for b in boxes), f'{label}: previews fit one row of their panel, “+n” counts the rest {[(b["thumbs"], b["more"], b["peekRows"]) for b in boxes]}')
    ok(all((b['hint'] == (b['size'] in ('l', 'xl') and (b['span'] == 2 or s['columns'] == 1))) for b in boxes), f'{label}: hints only on large panels: collapsed stages stay minimal')
    ok(s['overflow'] <= 0, f'{label}: no page overflow')
    return s

with sync_playwright() as pw:
    browser = pw.chromium.launch(executable_path=CHROME)

    # ---------- All stages empty: the empty state, no board ----------
    ctx, page = session(browser, DISTRIBUTIONS['all-empty']); load(page)
    ok(page.locator('#host-jobs-board').count() == 0 and "You're all caught up" in page.locator('.ws-main .empty-state').inner_text(), 'all empty: “You’re all caught up”, no board')
    ok(page.evaluate('document.documentElement.scrollWidth - innerWidth') <= 0, 'all empty: no page overflow')
    page.screenshot(path=str(OUT / 'mosaic-all-empty-1440.png')); ctx.close()

    # ---------- Every distribution, every stage open, 1440 Bright ----------
    for name, counts in DISTRIBUTIONS.items():
        if not any(counts): continue
        ctx, page = session(browser, counts)
        for stage in STAGES:
            load(page, stage); page.wait_for_timeout(150)
            check_layout(page, counts, f'{name} {counts}, {stage} open')
            if stage in ('available', 'in-production'): page.screenshot(path=str(OUT / f'mosaic-{name}-{stage}-1440.png'))
        ctx.close()

    # Arrangements decided by the counts (least empty space, workflow order kept).
    expect = {('diagram', 'in-production'): (['s', 's', 's'], [2, 1, 1]), ('even', 'available'): (['m', 'm', 'm'], [2, 1, 1]), ('several-zero', 'in-production'): (['xs', 'xs', 'l'], [2, 2, 2]),
              ('mixed', 'available'): (['m', 's', 'l'], [1, 1, 2]), ('small', 'shipped'): (['s', 's', 's'], [1, 1, 2]), ('capped', 'ready'): (['xl', 'xl', 'l'], [2, 2, 2]),
              ('one-heavy', 'in-production'): (['xl', 'xs', 'xs'], [2, 2, 2]), ('mixed', 'shipped'): (['s', 'm', 's'], [2, 1, 1])}
    for (name, stage), (sizes, spans) in expect.items():
        ctx, page = session(browser, DISTRIBUTIONS[name]); load(page, stage)
        boxes = page.evaluate(STATE)['boxes']
        ok([b['size'] for b in boxes] == sizes and [b['span'] for b in boxes] == spans, f'{name}, {stage} open: arranged {[(b["stage"], b["size"], b["span"]) for b in boxes]}')
        ctx.close()

    # ---------- Switching: in place, smooth, consistent under rapid clicks ----------
    counts = DISTRIBUTIONS['mixed']
    ctx, page = session(browser, counts); load(page, 'available'); page.evaluate('window.__same = 1'); page.requests.clear()
    started = page.evaluate("() => { document.querySelector('.sb-mosaic [data-sb-open=\"shipped\"]').click(); return document.getAnimations().length; }")
    ok(started > 0, f'a switch slides the panels ({started} animations)')
    page.wait_for_timeout(450)
    s = check_layout(page, counts, 'after a click on Awaiting buyer')
    ok(s['open'] == ['shipped'] and s['running'] == 0 and all(b['transform'] == 'none' for b in s['boxes']), 'the clicked stage opens; the animation ends cleanly')
    ok('available' in [b['stage'] for b in s['boxes']], 'the stage that was open joins the mosaic')
    ok(page.url.endswith('#host/jobs?group=shipped'), 'the address keeps the open stage')
    sequence = ['ready', 'available', 'in-production', 'ready', 'shipped', 'available', 'in-production', 'ready']
    for delay in (60, 5, 0):
        page.evaluate("async ([keys, delay]) => { for (const k of keys) { document.querySelector(`#host-jobs-board .sb-head[data-sb-open=\"${k}\"]`).click(); if (delay) await new Promise(r => setTimeout(r, delay)); } }", [sequence, delay])
        page.wait_for_timeout(600)
        s = check_layout(page, counts, f'rapid switching ({len(sequence)} clicks, {delay} ms apart)')
        ok(s['open'] == ['ready'] and s['expanded'] == {k: str(k == 'ready').lower() for k in STAGES} and s['running'] == 0 and all(b['transform'] == 'none' for b in s['boxes']),
           f'rapid switching ({delay} ms): ends on the last stage clicked, settled, aria-expanded right')
    ok(page.evaluate('window.__same') == 1 and not [u for u in page.requests if '/api/' in u], f'switching never reloads or calls the server ({len(page.requests)} requests)')
    # Keyboard: Enter on a mosaic panel opens it and keeps focus on it.
    page.evaluate("document.querySelector('.sb-mosaic [data-sb-open=\"in-production\"]').focus()"); page.keyboard.press('Enter'); page.wait_for_timeout(450)
    ok(page.evaluate("document.activeElement.matches('.sb-main .sb-head[data-sb-open=\"in-production\"]')"), 'keyboard: Enter opens the stage; focus stays on it')
    page.reload(); page.wait_for_selector('#host-jobs-board'); page.wait_for_function("!document.querySelector('.ws-main[aria-busy]')")
    ok(page.evaluate(STATE)['open'] == ['in-production'], 'a reload keeps the selected stage')
    ctx.close()
    ctx, page = session(browser, counts, motion='reduce'); load(page, 'available')
    ok(page.evaluate("() => { document.querySelector('.sb-mosaic [data-sb-open=\"ready\"]').click(); return document.getAnimations().filter(a => a.effect?.target?.matches?.('.sb-col')).length; }") == 0, 'reduced motion: the switch is instant')
    ctx.close()

    # ---------- A search re-balances the mosaic by what each stage still matches ----------
    ctx, page = session(browser, DISTRIBUTIONS['mixed']); load(page, 'available')
    before = {b['stage']: b['size'] for b in page.evaluate(STATE)['boxes']}
    page.fill('[data-filter-list="host-jobs-search"]', 'no such product')
    s = page.evaluate(STATE)
    ok(before == {'in-production': 'm', 'ready': 's', 'shipped': 'l'} and all(b['size'] == 'xs' and b['shown'] == '0' for b in s['boxes']), f'search with no match: every panel becomes a slim bar with 0 {[(b["stage"], b["size"], b["shown"]) for b in s["boxes"]]}')
    page.fill('[data-filter-list="host-jobs-search"]', '')
    s = page.evaluate(STATE)
    ok({b['stage']: b['size'] for b in s['boxes']} == before and {b['stage']: b['shown'] for b in s['boxes']} == {'in-production': '3', 'ready': '1', 'shipped': '8'} and all(b['thumbs'] + b['more'] == b['count'] for b in s['boxes']), 'clearing the search restores sizes, counts and previews')
    ctx.close()

    # ---------- Widths and themes ----------
    for w, theme in ((1920, 'dark'), (1440, 'dark'), (1280, 'light'), (1280, 'dark'), (1024, 'light'), (1024, 'dark'), (900, 'light'), (900, 'dark'), (768, 'light'), (768, 'dark')):
        for name in ('even', 'several-zero', 'mixed'):
            ctx, page = session(browser, DISTRIBUTIONS[name], w, 900, theme); load(page, 'available')
            s = check_layout(page, DISTRIBUTIONS[name], f'{w} {theme} {name}')
            ok(s['columns'] == (1 if w <= 1024 and w != 900 else 2), f'{w}: {s["columns"]}-column mosaic')
            if name == 'mixed': page.screenshot(path=str(OUT / f'mosaic-mixed-{w}-{theme}.png'))
            ctx.close()
    for w, theme in ((600, 'light'), (390, 'dark'), (390, 'light'), (320, 'light'), (320, 'dark')):
        ctx, page = session(browser, DISTRIBUTIONS['mixed'], w, 860, theme); load(page, 'available')
        state = page.evaluate("() => ({mosaic:document.querySelector('.sb-mosaic').checkVisibility(), pills:[...document.querySelectorAll('.sb-pills .chip')].filter(c => c.checkVisibility()).length, shown:[...document.querySelectorAll('.sb-col')].filter(c => c.checkVisibility()).map(c => c.dataset.stage), overflow:document.documentElement.scrollWidth - innerWidth})")
        ok(not state['mosaic'] and state['pills'] == 4 and state['shown'] == ['available'] and state['overflow'] <= 0, f'{w} {theme}: too narrow for the mosaic, the stage pills instead {state}')
        page.locator('.sb-pills [data-sb-open="shipped"]').click(); page.wait_for_timeout(300)
        ok(page.evaluate("[...document.querySelectorAll('.sb-col')].filter(c => c.checkVisibility()).map(c => c.dataset.stage)") == ['shipped'], f'{w}: a pill switches the stage')
        page.screenshot(path=str(OUT / f'mosaic-pills-{w}-{theme}.png'))
        ctx.close()

    ok(not errors, 'no page errors: ' + '; '.join(errors[:5]))
    browser.close()

print(f'{sum(checks)}/{len(checks)} checks passed')
sys.exit(0 if all(checks) else 1)
