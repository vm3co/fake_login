import json
import time
from playwright.sync_api import sync_playwright, expect

BASE = 'http://tsb016-e2e-api:5186'
with sync_playwright() as player:
    browser = player.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 390, 'height': 844}, accept_downloads=True)
    login = context.request.post(BASE + '/api/auth/login', data={'username': 'same@example.test', 'password': 'audit-test-only'}).json()
    token = login['accessToken']
    context.set_extra_http_headers({'Authorization': 'Bearer ' + token})
    context.add_init_script('localStorage.setItem("accessToken",' + json.dumps(token) + ')')
    page = context.new_page()

    def wait_job(identifier):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            jobs = context.request.get(BASE + '/api/jobs').json()
            job = next((row for row in jobs if row['job_id'] == identifier), None)
            if job and job['status'] not in ['queued', 'claiming', 'running', 'cancel_requested']:
                assert job['status'] == 'completed', job
                return job
        raise AssertionError(('job timeout', identifier))

    context.request.post(BASE + '/audit/remote', data={'version': 400, 'count': 2, 'missing': False,
        'wait_uuid': None, 'fail_uuid': None, 'block_after_one': False})
    page.goto(BASE + '/dashboard/default')
    page.get_by_text('Hi', exact=False).first.click()
    page.get_by_text('依名稱更新任務', exact=True).click()
    dialog = page.get_by_role('dialog')
    dialog.get_by_label('任務名稱關鍵字').fill('Mobile')
    dialog.get_by_role('button', name='搜尋', exact=True).click()
    row = dialog.get_by_role('row').filter(has_text='Mobile task')
    expect(row).to_be_visible()
    row.get_by_role('checkbox').check()
    with page.expect_response(lambda response: '/api/jobs/start' in response.url) as started:
        dialog.get_by_role('button', name='更新所選任務', exact=True).click()
    assert started.value.ok
    wait_job(started.value.json()['job_id'])
    page.get_by_role('button', name='全部任務', exact=True).click()
    expect(page.locator('tbody').get_by_text('Mobile task', exact=True)).to_be_visible()
    histories = context.request.get(BASE + '/api/task_backups', params={'search': 'Mobile'}).json()['total_count']
    for version in (range(401, 412) if histories < 11 else []):
        context.request.post(BASE + '/audit/remote', data={'version': version})
        admitted = context.request.post(BASE + '/api/jobs/start', data={
            'job_type': 'refresh_sendlog_stats', 'params': {'uuids': ['mobile-task']}}).json()
        wait_job(admitted['job_id'])
    page.get_by_role('button', name='備援任務', exact=True).click()
    total = context.request.get(BASE + '/api/task_backups', params={'search': 'Mobile'}).json()['total_count']
    assert 10 < total <= 20, total
    page.get_by_label('搜尋備援名稱或來源 UUID').fill('Mobile')
    page.get_by_role('combobox').last.click()
    page.get_by_role('option', name='10', exact=True).click()
    checks = page.get_by_role('checkbox', name='選取備援', exact=False)
    expect(checks).to_have_count(10)
    checks.first.check()
    page.get_by_role('button', name='Go to next page').click()
    expect(checks).to_have_count(total - 10)
    checks.first.check()
    page.get_by_role('button', name='檢查是否重建', exact=True).click()
    expect(dialog).to_contain_text('2 份備援')
    expect(dialog).to_contain_text('1 個來源任務')
    dialog.get_by_role('button', name='取消', exact=True).click()
    page.get_by_role('button', name='檢查是否重建', exact=True).click()
    with page.expect_response(lambda response: '/api/jobs/start' in response.url) as checked:
        dialog.get_by_role('button', name='確認檢查所選備援', exact=True).click()
    wait_job(checked.value.json()['job_id'])
    with page.expect_download() as downloaded:
        page.get_by_role('button', name='匯出備援', exact=False).first.click()
    assert downloaded.value.suggested_filename.endswith('.xlsx')
    page.get_by_role('button', name='刪除備援', exact=False).first.click()
    dialog.get_by_role('button', name='確認永久刪除', exact=True).click()
    expect(checks).to_have_count(10 if total == 11 else total - 11)
    assert context.request.get(BASE + '/api/task_backups', params={'search': 'Mobile'}).json()['total_count'] == total - 1
    print('PASS mobile search UI import -> real jobs -> cross-page selection/check/export/delete and page clamp')
    browser.close()