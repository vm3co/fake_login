import json
import time
from io import BytesIO
from openpyxl import load_workbook
from playwright.sync_api import sync_playwright, expect

BASE = 'http://tsb016-e2e-api:5186'
with sync_playwright() as player:
    browser = player.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, accept_downloads=True)
    response = context.request.post(BASE + '/api/auth/login', data={'username': 'audit@example.test', 'password': 'audit-test-only'})
    assert response.status == 200, response.text()
    login = response.json()
    assert login['status'] == 'success', login
    token = login['accessToken']
    context.add_init_script('localStorage.setItem("accessToken", ' + json.dumps(token) + ')')
    context.set_extra_http_headers({'Authorization': 'Bearer ' + token})
    page = context.new_page()
    def wait_job(identifier):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            jobs = context.request.get(BASE + '/api/jobs').json()
            job = next((row for row in jobs if row['job_id'] == identifier), None)
            if job and job['status'] not in ['queued', 'running', 'claiming', 'cancel_requested']:
                assert job['status'] == 'completed', job
                return job
        raise AssertionError(('job timeout', identifier, jobs))
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(BASE + '/dashboard/default')
    page.get_by_role('button', name='全部任務', exact=True).click()
    expect(page.get_by_text('E2E task', exact=True)).to_be_visible()
    page.get_by_text('E2E task', exact=True).click()
    expect(page.get_by_text('總信件數: 3', exact=True)).to_be_visible()
    expect(page.get_by_text('v100-0@example.test', exact=True)).to_be_visible()
    page.get_by_role('button', name='關閉明細', exact=True).click()
    page.on('dialog', lambda dialog: dialog.accept())
    with page.expect_response(lambda response: '/api/jobs/start' in response.url) as started:
        page.get_by_role('button', name='更新', exact=True).click()
    assert started.value.status == 200, started.value.text()
    wait_job(started.value.json()['job_id'])
    remote = context.request.post(BASE + '/audit/remote', data={'missing': True})
    assert remote.ok
    with page.expect_response(lambda response: '/api/jobs/start' in response.url) as deleted:
        page.get_by_role('button', name='更新', exact=True).click()
    assert deleted.value.ok
    wait_job(deleted.value.json()['job_id'])
    expect(page.locator('tbody').get_by_text('E2E task', exact=True)).to_have_count(0, timeout=30000)
    page.get_by_role('button', name='備援任務', exact=True).click()
    expect(page.locator('tbody').get_by_text('E2E task', exact=True)).to_be_visible()
    data = context.request.get(BASE + '/api/task_backups').json()
    assert data['total_count'] == 1, data
    backup_id = data['data'][0]['backup_id']
    page.get_by_role('button', name=f'備援明細 {backup_id}', exact=True).click()
    expect(page.get_by_text('v100-0@example.test', exact=True)).to_be_visible()
    expect(page.get_by_text('總信件數: 3', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='重置', exact=True)).to_have_count(0)
    page.get_by_role('button', name='關閉明細', exact=True).click()
    with page.expect_download() as download:
        page.get_by_role('button', name=f'匯出備援 {backup_id}', exact=True).click()
    with open(download.value.path(), 'rb') as exported:
        book = load_workbook(BytesIO(exported.read()))
    assert book['details'].max_row == 4
    assert 'v100-0@example.test' in str(list(book['details'].values))
    context.request.post(BASE + '/audit/remote', data={'missing': False, 'version': 200, 'count': 5})
    admitted = context.request.post(BASE + '/api/jobs/start', data={'job_type': 'upsert_selected_sendtasks', 'params': {'uuids': ['e2e-task']}})
    assert admitted.ok, admitted.text()
    wait_job(admitted.json()['job_id'])
    page.get_by_role('button', name='全部任務', exact=True).click()
    page.locator('tbody').get_by_text('E2E task', exact=True).click()
    expect(page.get_by_text('總信件數: 5', exact=True)).to_be_visible()
    expect(page.get_by_text('v200-4@example.test', exact=True)).to_be_visible()
    expect(page.get_by_text('v100-0@example.test', exact=True)).to_have_count(0)
    page.get_by_role('button', name='關閉明細', exact=True).click()
    context.request.post(BASE + '/audit/remote', data={'version': 300, 'count': 2})
    with page.expect_response(lambda response: '/api/jobs/start' in response.url) as rebuilt:
        page.get_by_role('button', name='更新', exact=True).click()
    wait_job(rebuilt.value.json()['job_id'])
    expect(page.locator('tbody tr').filter(has=page.get_by_text('E2E task', exact=True)).get_by_role('cell', name='2', exact=True).first).to_be_visible(timeout=30000)
    page.locator('tbody').get_by_text('E2E task', exact=True).click()
    expect(page.get_by_text('總信件數: 2', exact=True)).to_be_visible(timeout=30000)
    expect(page.get_by_text('v300-0@example.test', exact=True)).to_be_visible()
    page.get_by_role('button', name='關閉明細', exact=True).click()
    page.get_by_role('button', name='備援任務', exact=True).click()
    backups = context.request.get(BASE + '/api/task_backups').json()['data']
    assert len(backups) == 2
    second = next(row['backup_id'] for row in backups if row['source_create_ut'] == 200)
    other_login = context.request.post(BASE + '/api/auth/login', data={'username': 'other@example.test', 'password': 'audit-test-only'}).json()
    other_headers = {'Authorization': 'Bearer ' + other_login['accessToken']}
    assert context.request.get(BASE + '/api/task_backups', headers=other_headers).json()['total_count'] == 0
    assert context.request.get(BASE + f'/api/task_backups/{backup_id}', headers=other_headers).status == 404
    assert context.request.post(BASE + '/api/jobs/start', headers=other_headers, data={'job_type': 'check_backup_recreated', 'params': {'backup_ids': [backup_id]}}).status == 404
    same_login = context.request.post(BASE + '/api/auth/login', data={'username': 'same@example.test', 'password': 'audit-test-only'}).json()
    assert same_login['user']['admin_role'] is False
    for identifier, count, email in [(backup_id, 3, 'v100-0@example.test'), (second, 5, 'v200-4@example.test')]:
        page.get_by_role('button', name=f'備援明細 {identifier}', exact=True).click()
        expect(page.get_by_text(f'總信件數: {count}', exact=True)).to_be_visible()
        expect(page.get_by_text(email, exact=True)).to_be_visible()
        page.get_by_role('button', name='關閉明細', exact=True).click()
    page.screenshot(path='/audit/tsb016-desktop.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_role('button', name=f'備援明細 {second}', exact=True).click()
    expect(page.get_by_role('button', name='關閉明細', exact=True)).to_be_in_viewport()
    expect(page.get_by_text('總信件數: 5', exact=True)).to_be_visible()
    page.screenshot(path='/audit/tsb016-mobile.png')
    page.get_by_role('button', name='關閉明細', exact=True).click()
    context.set_extra_http_headers({'Authorization': 'Bearer ' + same_login['accessToken']})
    page.evaluate('(token) => localStorage.setItem("accessToken", token)', same_login['accessToken'])
    page.reload()
    page.get_by_role('button', name='備援任務', exact=True).click()
    page.get_by_role('button', name=f'刪除備援 {backup_id}', exact=True).click()
    page.get_by_role('button', name='確認永久刪除', exact=True).click()
    expect(page.get_by_role('button', name=f'備援明細 {backup_id}', exact=True)).to_have_count(0)
    assert context.request.get(BASE + '/api/task_backups').json()['total_count'] == 1
    page.get_by_role('button', name='全部任務', exact=True).click()
    page.locator('tbody').get_by_text('E2E task', exact=True).click()
    expect(page.get_by_text('總信件數: 2', exact=True)).to_be_visible()
    assert not errors, errors
    print('PASS real login/JWT -> UI -> JobQueue -> sync core -> SQL/Redis -> invalidation -> A/B backups + C current -> XLSX -> delete A preserves B/C, desktop/mobile')
    browser.close()