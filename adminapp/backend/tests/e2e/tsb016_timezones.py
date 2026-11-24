import base64
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = 'http://tsb016-e2e-api:5186'
source = Path('/app/frontend/src/app/utils/todayTaskFilter.js').read_text()
module = 'data:text/javascript;base64,' + base64.b64encode(source.encode()).decode()
with sync_playwright() as player:
    browser = player.chromium.launch(headless=True)
    for zone in ['UTC', 'Asia/Taipei', 'America/New_York']:
        context = browser.new_context(timezone_id=zone, viewport={'width': 390, 'height': 844})
        login = context.request.post(BASE + '/api/auth/login', data={'username': 'same@example.test', 'password': 'audit-test-only'}).json()
        token = login['accessToken']
        context.set_extra_http_headers({'Authorization': 'Bearer ' + token})
        import json
        context.add_init_script('localStorage.setItem("accessToken",' + json.dumps(token) + ')')
        page = context.new_page()
        page.goto(BASE + '/dashboard/default')
        result = page.evaluate('''async url => {
          const tools = await import(url);
          const before = tools.getTaipeiDayBounds(Date.parse('2026-11-17T15:59:59Z'));
          const after = tools.getTaipeiDayBounds(Date.parse('2026-11-17T16:00:00Z'));
          const task = {is_archived:false};
          return {
            zone:Intl.DateTimeFormat().resolvedOptions().timeZone,
            before:before.start, after:after.start,
            start:tools.isTodayTask(task,{today_earliest_plan_time:after.start/1000},after),
            end:tools.isTodayTask(task,{today_earliest_plan_time:after.end/1000},after),
            tomorrow:tools.matchesTaskFilters({test_start_ut:after.end/1000},{},{showNotStartedOnly:true},after)
          };
        }''', module)
        assert result['zone'] == zone, result
        assert result['after'] - result['before'] == 86400000, result
        assert result['start'] and not result['end'] and result['tomorrow'], result
        page.get_by_role('button', name='備援任務', exact=True).click()
        backup = context.request.get(BASE + '/api/task_backups').json()['data'][0]
        page.get_by_role('button', name=f"備援明細 {backup['backup_id']}", exact=True).click()
        expect(page.get_by_text('總信件數: 5', exact=True)).to_be_visible()
        expect(page.get_by_text('v200-4@example.test', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='關閉明細', exact=True)).to_be_in_viewport()
        context.close()
        print('PASS Chromium timezone', zone, 'Taipei midnight/inclusive start/exclusive end/tomorrow + mobile backup')
    browser.close()