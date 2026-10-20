import test from "node:test";
import assert from "node:assert/strict";
import { getTaipeiDayBounds, isTodayTask } from "./todayTaskFilter.js";

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