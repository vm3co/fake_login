import test from 'node:test';
import assert from 'node:assert/strict';
import { backupPage, selectBackupPage, backupCheckParams, validateBackupList, backupTime } from './backupList.js';

test('same source versions remain independently selected across pages', () => {
  const first = { backup_id: 'one', source_task_uuid: 'same' };
  const second = { backup_id: 'two', source_task_uuid: 'same' };
  const selected = selectBackupPage(selectBackupPage({}, [first], true), [second], true);
  assert.deepEqual(backupCheckParams(selected), { backup_ids: ['one', 'two'] });
  assert.deepEqual(selectBackupPage(selected, [first], false), { two: second });
});
test('last page is clamped after deletion including empty list', () => {
  assert.equal(backupPage(2, 20, 10), 1);
  assert.equal(backupPage(3, 0, 10), 0);
});
test('errors and malformed lists cannot masquerade as successful empty lists', () => {
  for (const value of [{}, { status: 'error', data: [], total_count: 0 },
    { status: 'success', data: [{ backup_id: 'x' }, { backup_id: 'x' }], total_count: 2 }]) {
    assert.throws(() => validateBackupList(value));
  }
  assert.deepEqual(validateBackupList({ status: 'success', data: [], total_count: 0 }).data, []);
  assert.throws(() => backupCheckParams({}));
});
test('timestamps use Taipei and preserve unknown source version', () => {
  assert.equal(backupTime(null, true), '未知');
  assert.match(backupTime('2026-01-01T00:00:00Z'), /08:00:00/);
});