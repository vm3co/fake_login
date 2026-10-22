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

export function isTodayTask(task, stats, dayBounds = getTaipeiDayBounds()) {
    if (task.is_archived === true) return false;
    const rawTimestamp = stats?.today_earliest_plan_time;
    if (typeof rawTimestamp !== "number" && typeof rawTimestamp !== "string") return false;
    const timestamp = Number(rawTimestamp);
    return Number.isFinite(timestamp) && timestamp > 0
        && timestamp * 1000 >= dayBounds.start
        && timestamp * 1000 < dayBounds.end;
}