import test from 'node:test';
import assert from 'node:assert/strict';
import { detailSource, detailRequest, backupHeader, detailRows } from './taskDetailSource.js';

test('同 UUID 的備援與現行版本具有不同識別', () => {
  const keys = [detailSource({ source: 'backup', backup_id: 'a' }), detailSource({ source: 'backup', backup_id: 'b' }),
    detailSource({ sendtask_uuid: 'same', local_generation_id: 'one' }),
    detailSource({ sendtask_uuid: 'same', local_generation_id: 'two' })].map(source => source.key);
  assert.equal(new Set(keys).size, 4);
  assert.throws(() => detailSource({ source: 'backup' }));
  assert.throws(() => detailSource({ sendtask_uuid: 'same' }));
});

test('備援請求只使用 backup_id 並正規化空日期', () => {
  const task = { source: 'backup', backup_id: 'a/b', sendtask_uuid: 'live' };
  const request = detailRequest(detailSource(task), task, 2, { dateFrom: '', dateTo: '', rowsPerPage: 20 });
  assert.equal(request.url, '/api/task_backups/a%2Fb/details');
  assert.equal(request.body.page, 3);
  assert.equal(request.body.dateFrom, null);
  assert.equal('sendtask_uuid' in request.body, false);
  assert.deepEqual(request.body.acctControl, [true, true, true, true, true]);
});

test('備援標頭錯誤、不同副本或不完整快照不得降級', () => {
  const response = { status: 'success', data: { backup_id: 'a', task_snapshot: {}, stats_snapshot: null,
    mail_template_snapshot: { old: { mtmpl_uuid: 'old', mtmpl_title: '歷史主旨' }, deleted: null } } };
  assert.equal(backupHeader(response, 'a').backup_id, 'a');
  assert.equal(backupHeader(response, 'a').templates[0].mtmpl_title, '歷史主旨');
  assert.throws(() => backupHeader(response, 'b'));
  assert.throws(() => backupHeader({ status: 'error' }, 'a'));
});

test('備援顯示採後端投影，保留事件次數與空資料', () => {
  const result = detailRows({ status: 'success', total_count: 1, data: [{ access_time: [1, 2], display: { access_time: 2, access_count: 2 } }] }, true);
  assert.equal(result.rows[0].access_time, 2);
  assert.equal(result.rows[0].access_count, 2);
  assert.deepEqual(detailRows({ status: 'success', data: [], total_count: 0 }, true), { rows: [], total: 0 });
  assert.throws(() => detailRows({ status: 'success', data: [{}], total_count: 1 }, true));
});