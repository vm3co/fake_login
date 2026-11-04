import test from "node:test";
import assert from "node:assert/strict";
import { getTaipeiDayBounds, getTaskPeriod, isTodayTask, matchesTaskFilters } from "./todayTaskFilter.js";

const now = Date.parse("2026-10-20T12:00:00+08:00");
const bounds = getTaipeiDayBounds(now);
const todayStats = { today_earliest_plan_time: bounds.start / 1000, todayunsend: 0 };

test("Taipei day boundaries are independent of the host timezone", () => {
    assert.equal(bounds.start, Date.parse("2026-10-19T16:00:00Z"));
    assert.equal(bounds.end, Date.parse("2026-10-20T16:00:00Z"));
});

test("only unarchived tasks with today's plans are selected without changing the full list", () => {
    const tasks = [
        { sendtask_uuid: "completed", is_archived: false },
        { sendtask_uuid: "archived", is_archived: true },
        { sendtask_uuid: "legacy-null", is_archived: null },
        { sendtask_uuid: "legacy-missing" },
        { sendtask_uuid: "no-stats" },
    ];
    const stats = Object.fromEntries(tasks.slice(0, 4).map(task => [task.sendtask_uuid, todayStats]));
    const selected = tasks.filter(task => isTodayTask(task, stats[task.sendtask_uuid], bounds));
    assert.deepEqual(selected.map(task => task.sendtask_uuid), ["completed", "legacy-null", "legacy-missing"]);
    assert.equal(tasks.length, 5);
});

test("start is inclusive, next midnight is exclusive, numeric strings are accepted", () => {
    for (const timestamp of [bounds.start / 1000, (bounds.end - 1000) / 1000, String(bounds.start / 1000)]) {
        assert.equal(isTodayTask({}, { today_earliest_plan_time: timestamp }, bounds), true);
    }
    for (const timestamp of [(bounds.start - 1000) / 1000, bounds.end / 1000, 0, -1, NaN, Infinity, "invalid", "", null, undefined, true, []]) {
        assert.equal(isTodayTask({}, { today_earliest_plan_time: timestamp }, bounds), false);
    }
    assert.equal(isTodayTask({}, undefined, bounds), false);
});

test("a persisted snapshot stops qualifying at Taipei midnight", () => {
    assert.equal(isTodayTask({}, todayStats, getTaipeiDayBounds(bounds.end - 1)), true);
    assert.equal(isTodayTask({}, todayStats, getTaipeiDayBounds(bounds.end)), false);
});

const dayStart = bounds.start / 1000;
const dayEnd = bounds.end / 1000;
const period = (start, end) => ({ test_start_ut: start, test_end_ut: end });
const matches = (task, filter, stats) => matchesTaskFilters(task, stats, { [filter]: true }, bounds);

test("task period boundaries use seconds and today's overlap, not the current instant", () => {
    assert.equal(dayEnd - dayStart, 86400);
    for (const task of [
        period(dayStart, dayEnd),
        period(dayStart - 86400, dayEnd + 86400),
        period(dayStart + 18 * 3600, dayEnd),
        period(dayStart, dayStart + 9 * 3600),
    ]) {
        assert.equal(matches(task, "showRunningOnly"), true);
        assert.equal(matches(task, "showNotStartedOnly"), false);
        assert.equal(matches(task, "showExpiredOnly"), false);
    }
    for (const start of [dayEnd, dayEnd + 7 * 86400]) {
        const task = period(start, start + 3600);
        assert.equal(matches(task, "showRunningOnly"), false);
        assert.equal(matches(task, "showNotStartedOnly"), true);
    }
    const ended = period(dayStart - 86400, dayStart);
    assert.equal(matches(ended, "showExpiredOnly"), true);
    assert.equal(matches(ended, "showRunningOnly"), false);
});

test("pretest periods and valid early stop times take precedence", () => {
    const task = {
        ...period(dayEnd, dayEnd + 86400),
        pre_test_enable: true,
        pre_test_start_ut: String(dayStart),
        pre_test_end_ut: String(dayEnd),
    };
    assert.deepEqual(getTaskPeriod(task), { start: dayStart, end: dayEnd });
    assert.equal(matches(task, "showRunningOnly"), true);
    const stopped = { ...task, pre_test_start_ut: dayStart - 86400, stop_time_new: String(dayStart) };
    assert.equal(matches(stopped, "showExpiredOnly"), true);
    assert.equal(matches(stopped, "showRunningOnly"), false);
    for (const stop of [null, undefined, 0, -1, -2, "-1", "invalid", NaN, Infinity, true, []]) {
        assert.equal(getTaskPeriod({ ...task, stop_time_new: stop }).end, dayEnd);
    }
});

test("missing or invalid periods never qualify as running but remain unfiltered", () => {
    for (const value of [null, undefined, 0, -1, "", "invalid", NaN, Infinity, true, []]) {
        for (const task of [period(value, dayEnd), period(dayStart, value)]) {
            assert.equal(matches(task, "showRunningOnly"), false);
            assert.equal(matchesTaskFilters(task, undefined, {}, bounds), true);
        }
        assert.equal(matches(period(value, dayEnd), "showNotStartedOnly"), false);
        assert.equal(matches(period(dayStart, value), "showExpiredOnly"), false);
    }
    assert.equal(matches(period(dayEnd, dayStart), "showRunningOnly"), false);
    assert.equal(matches(period(dayStart, dayStart), "showRunningOnly"), false);
});

test("failed filter requires a valid positive totalfailed and composes with period filters", () => {
    const task = period(dayStart, dayEnd);
    for (const totalfailed of [1, 3, "2"]) {
        assert.equal(matches(task, "showFailedOnly", { totalfailed }), true);
    }
    for (const totalfailed of [0, -1, null, undefined, "", "invalid", NaN, Infinity, true, []]) {
        assert.equal(matches(task, "showFailedOnly", { totalfailed }), false);
    }
    assert.equal(matches(task, "showFailedOnly", undefined), false);
    assert.equal(matches(task, "showFailedOnly", { totalsend: 10, totalsuccess: 8 }), false);
    const filters = { showRunningOnly: true, showFailedOnly: true };
    assert.equal(matchesTaskFilters(task, { totalfailed: 1 }, filters, bounds), true);
    assert.equal(matchesTaskFilters(period(dayEnd, dayEnd + 3600), { totalfailed: 1 }, filters, bounds), false);
    assert.equal(matchesTaskFilters(task, { totalfailed: 0 }, filters, bounds), false);
});

test("period classification moves forward exactly at Taipei midnight", () => {
    const task = period(dayStart, dayEnd);
    const before = getTaipeiDayBounds(bounds.end - 1);
    const after = getTaipeiDayBounds(bounds.end);
    assert.equal(matchesTaskFilters(task, {}, { showRunningOnly: true }, before), true);
    assert.equal(matchesTaskFilters(task, {}, { showRunningOnly: true }, after), false);
    assert.equal(matchesTaskFilters(task, {}, { showExpiredOnly: true }, after), true);
});