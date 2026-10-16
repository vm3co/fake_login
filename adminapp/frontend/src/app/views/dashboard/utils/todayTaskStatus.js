const toCount = (value) => {
  const count = Number(value);
  return Number.isFinite(count) ? Math.max(0, count) : 0;
};

export function getTodayTaskState(stats = {}) {
  const todayUnsend = toCount(stats.todayunsend);
  const todaySend = toCount(stats.todaysend);

  if (todayUnsend === 0) return "done";
  return todaySend > 0 ? "doing" : "notyet";
}

export function isTodayTaskWarning(stats = {}) {
  if (stats.todayfailed != null) {
    return toCount(stats.todayfailed) > 0;
  }

  return toCount(stats.todaysend) - toCount(stats.todaysuccess) > 0;
}

export function matchesTodayTaskState(stats, taskState) {
  if (taskState === "all") return true;
  if (taskState === "warning") return isTodayTaskWarning(stats);
  return getTodayTaskState(stats) === taskState;
}
