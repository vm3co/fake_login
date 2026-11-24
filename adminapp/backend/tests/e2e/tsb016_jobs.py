import json
import time
from playwright.sync_api import sync_playwright, expect

BASE = 'http://tsb016-e2e-api:5186'
with sync_playwright() as player:
    browser = player.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    login = context.request.post(BASE + '/api/auth/login', data={'username': 'audit@example.test', 'password': 'audit-test-only'}).json()
    token = login['accessToken']
    context.set_extra_http_headers({'Authorization': 'Bearer ' + token})
    context.add_init_script('localStorage.setItem("accessToken",' + json.dumps(token) + ')')
    page = context.new_page()
    def wait_job(identifier, predicate):
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            jobs = context.request.get(BASE + '/api/jobs').json()
            job = next((row for row in jobs if row['job_id'] == identifier), None)
            if job and predicate(job):
                return job
        raise AssertionError(('job timeout', identifier, jobs))
    page.goto(BASE + '/dashboard/default')
    page.get_by_role('button', name='全部任務', exact=True).click()
    expect(page.locator('tbody').get_by_text('E2E task', exact=True).first).to_be_visible()
    page.evaluate("() => { window.auditEvents=[]; window.addEventListener('taskDataInvalidated', event=>window.auditEvents.push(event.detail)); }")
    context.request.post(BASE + '/audit/remote', data={'version': 300, 'count': 2, 'missing': False, 'fail_uuid': None, 'wait_uuid': None, 'block_after_one': False})
    admission = context.request.post(BASE + '/api/jobs/start', data={'job_type': 'upsert_selected_sendtasks', 'params': {'uuids': ['second-task']}}).json()
    assert admission['status'] == 'success', admission
    wait_job(admission['job_id'], lambda job: job['status'] == 'completed')
    context.request.post(BASE + '/audit/remote', data={'fail_uuid': 'second-task'})
    partial = context.request.post(BASE + '/api/jobs/start', data={'job_type': 'refresh_sendlog_stats', 'params': {'uuids': ['e2e-task','second-task']}}).json()
    assert partial['status'] == 'success', partial
    print('PARTIAL', partial, flush=True)
    wait_job(partial['job_id'], lambda job: job['status'] == 'partial')
    page.wait_for_function("() => window.auditEvents.some(event=>event.uuids.includes('e2e-task'))")
    result = next(job for job in context.request.get(BASE + '/api/jobs').json() if job['job_id'] == partial['job_id'])
    assert result['result']['changed_uuids'] == ['e2e-task'], result
    context.request.post(BASE + '/audit/remote', data={'fail_uuid': None, 'wait_uuid': None, 'block_after_one': True, 'read_count': 0})
    page.evaluate('() => { window.auditEvents=[]; }')
    cancelled = context.request.post(BASE + '/api/jobs/start', data={'job_type': 'refresh_sendlog_stats', 'params': {'uuids': ['e2e-task','second-task']}}).json()
    assert cancelled['status'] == 'success', cancelled
    print('CANCEL', cancelled, flush=True)
    before = wait_job(cancelled['job_id'], lambda job: job['status'] == 'running' and len((job['result'] or {}).get('changed_uuids', [])) == 1)
    print('BEFORE CANCEL', before, flush=True)
    assert context.request.post(BASE + '/api/jobs/' + cancelled['job_id'] + '/cancel').ok
    result = wait_job(cancelled['job_id'], lambda job: job['status'] == 'cancelled')
    assert result['result']['changed_uuids'] == before['result']['changed_uuids'], result
    assert result['result']['unfinished_tasks'], result
    page.wait_for_function('(uuid) => window.auditEvents.some(event=>event.uuids.includes(uuid))', arg=before['result']['changed_uuids'][0])
    context.request.post(BASE + '/audit/remote', data={'wait_uuid': None, 'block_after_one': False})
    print('PASS real JobQueue partial/cancel: prior SQL commits and changed_uuids survive; browser observes invalidation')
    browser.close()