import json
import time
from playwright.sync_api import sync_playwright, expect

BASE = 'http://tsb016-e2e-api:5186'
with sync_playwright() as player:
    browser = player.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    def login(name):
        result = context.request.post(BASE + '/api/auth/login', data={'username': name + '@example.test', 'password': 'audit-test-only'}).json()
        assert result['status'] == 'success', result
        return result['accessToken']
    token = login('same')
    headers = {'Authorization': 'Bearer ' + token}
    backups = context.request.get(BASE + '/api/task_backups', headers=headers).json()['data']
    backup = backups[0]['backup_id']
    for role, expected in [('other', 404), ('customer', 403), (None, 401)]:
        auth = {'Authorization': 'Bearer ' + login(role)} if role else {}
        listing = context.request.get(BASE + '/api/task_backups', headers=auth)
        if role == 'other':
            assert listing.json()['total_count'] == 0
        else:
            assert listing.status == expected, listing.text()
        for suffix in ['', '/export.xlsx']:
            result = context.request.get(BASE + f'/api/task_backups/{backup}' + suffix, headers=auth)
            assert result.status == expected, (role, result.status, result.text())
        assert context.request.post(BASE + f'/api/task_backups/{backup}/details', headers=auth, data={}).status == expected
        assert context.request.delete(BASE + f'/api/task_backups/{backup}?confirm_delete=true', headers=auth).status == expected
        result = context.request.post(BASE + '/api/jobs/start', headers=auth, data={'job_type': 'check_backup_recreated', 'params': {'backup_ids': [backup]}})
        assert result.status == expected, (role, result.status, result.text())
    context.set_extra_http_headers(headers)
    context.add_init_script('localStorage.setItem("accessToken",' + json.dumps(token) + ')')
    page = context.new_page()
    page.goto(BASE + '/dashboard/default')
    page.get_by_role('button', name='備援任務', exact=True).click()
    page.get_by_role('checkbox', name=f'選取備援 {backup}', exact=True).check()
    page.get_by_role('button', name='檢查是否重建', exact=True).click()
    with page.expect_response(lambda response: '/api/jobs/start' in response.url) as admitted:
        page.get_by_role('button', name='確認檢查所選備援', exact=True).click()
    identifier = admitted.value.json()['job_id']
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = next(row for row in context.request.get(BASE + '/api/jobs').json() if row['job_id'] == identifier)
        if job['status'] == 'completed':
            break
    assert job['status'] == 'completed', job
    expect(page.get_by_text('來源存在', exact=True)).to_be_visible(timeout=30000)
    assert context.request.get(BASE + f'/api/task_backups/{backup}').json()['data']['recreated_detected_at']
    print('PASS actual login identity matrix on backup APIs + same-org UI reconstruction check and refresh')
    browser.close()