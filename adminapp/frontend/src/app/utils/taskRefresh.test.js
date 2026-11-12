import test from 'node:test';
import assert from 'node:assert/strict';
import { assertStableTasks, mergeTaskSnapshot, jobInvalidation, combineInvalidations, invalidationSignature, pollInvalidations } from './taskRefresh.js';

const success = data => ({ status: 'success', data });
test('authoritative empty removes only requested tasks and statistics', () => {
  const result = mergeTaskSnapshot([{ sendtask_uuid: 'old' }, { sendtask_uuid: 'keep' }], { old: {}, keep: {} }, success([]), success([]), ['old']);
  assert.deepEqual(result, { tasks: [{ sendtask_uuid: 'keep' }], stats: { keep: {} } });
});
test('errors, malformed and inconsistent responses cannot produce a snapshot', () => {
  for (const response of [{ status: 'error', data: [] }, {}, success([{}])]) {
    assert.throws(() => mergeTaskSnapshot([], {}, response, success([])));
  }
  assert.throws(() => mergeTaskSnapshot([], {}, success([{ sendtask_uuid: 'one' }]), success([])));
});
test('cancelled and item-less jobs retain committed invalidation and coalesce', () => {
  const job = { status: 'cancelled', result: { changed_uuids: ['old'], backups_changed: true, reload_list: true,
    sync_results: { old: { committed: true, generation: null, revision: null, status: 'backed_up' } } } };
  const event = jobInvalidation(job);
  assert.deepEqual(combineInvalidations([event, event]).uuids, ['old']);
  assert.equal(event.versions.old.status, 'backed_up');
  assert.equal(combineInvalidations([event]).backupsChanged, true);
  assert.notEqual(invalidationSignature(job), invalidationSignature({ ...job, result: {} }));
});
test('version verification rejects same UUID with changed generation or revision', () => {
  const first = success([{ sendtask_uuid: 'one', local_generation_id: 'old', sync_revision: 1 }]);
  assertStableTasks(first, first);
  assert.throws(() => assertStableTasks(first, success([{ sendtask_uuid: 'one', local_generation_id: 'new', sync_revision: 0 }])));
  assert.throws(() => assertStableTasks(first, success([])));
});

test('first poll establishes history baseline while later commits and unseen terminal jobs invalidate once', () => {
  const historical = { job_id: 'historical', status: 'completed', result: { changed_uuids: ['old'] } };
  assert.deepEqual(pollInvalidations([historical], new Map(), false), []);
  const baseline = new Map([[historical.job_id, invalidationSignature(historical)]]);
  assert.deepEqual(pollInvalidations([historical], baseline, true), []);
  const cancelled = { job_id: 'new-between-polls', status: 'cancelled', result: {
    changed_uuids: ['one'], sync_results: { one: { committed: true, generation: 'gen', revision: 1 } },
  } };
  assert.equal(pollInvalidations([historical, cancelled], baseline, true).length, 1);
  baseline.set(cancelled.job_id, invalidationSignature(cancelled));
  assert.deepEqual(pollInvalidations([historical, cancelled], baseline, true), []);
  const revised = { ...cancelled, result: { ...cancelled.result,
    sync_results: { one: { committed: true, generation: 'gen', revision: 2 } } } };
  assert.equal(pollInvalidations([revised], baseline, true)[0].versions.one.revision, 2);
});