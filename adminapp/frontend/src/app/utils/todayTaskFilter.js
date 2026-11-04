const taipeiDateFormatter = new Intl.DateTimeFormat("en-US", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
});

export function getTaipeiDayBounds(now = Date.now()) {
    const parts = Object.fromEntries(
        taipeiDateFormatter.formatToParts(new Date(now))
            .map(({ type, value }) => [type, value])
    );
    const start = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day))
        - 8 * 60 * 60 * 1000;
    return { start, end: start + 24 * 60 * 60 * 1000 };
}

function positiveNumber(value) {
    if (typeof value !== "number" && typeof value !== "string") return null;
    const number = Number(value);
    return Number.isFinite(number) && number > 0 ? number : null;
}

export function getTaskPeriod(task) {
    return {
        start: positiveNumber(task.pre_test_enable ? task.pre_test_start_ut : task.test_start_ut),
        end: positiveNumber(task.stop_time_new)
            ?? positiveNumber(task.pre_test_enable ? task.pre_test_end_ut : task.test_end_ut),
    };
}

export function matchesTaskFilters(task, stats, filters, dayBounds = getTaipeiDayBounds()) {
    const { start, end } = getTaskPeriod(task);
    const dayStart = dayBounds.start / 1000;
    const dayEnd = dayBounds.end / 1000;
    if (filters.showExpiredOnly && !(end !== null && end <= dayStart)) return false;
    if (filters.showNotStartedOnly && !(start !== null && start >= dayEnd)) return false;
    if (filters.showRunningOnly && !(start !== null && end !== null
        && end > start && start < dayEnd && end > dayStart)) return false;
    if (filters.showFailedOnly && positiveNumber(stats?.totalfailed) === null) return false;
    return true;
}

export function isTodayTask(task, stats, dayBounds = getTaipeiDayBounds()) {
    if (task.is_archived === true) return false;
    const rawTimestamp = stats?.today_earliest_plan_time;
    if (typeof rawTimestamp !== "number" && typeof rawTimestamp !== "string") return false;
    const timestamp = Number(rawTimestamp);
    return Number.isFinite(timestamp) && timestamp > 0
        && timestamp * 1000 >= dayBounds.start
        && timestamp * 1000 < dayBounds.end;
}