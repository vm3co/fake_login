import { useEffect, useState, useRef } from "react";
import { useSnackbar } from 'notistack';
import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";
import useAuth from "app/hooks/useAuth";
import { getTaipeiDayBounds, isTodayTask } from "app/utils/todayTaskFilter";
import axios from "axios";
import { assertStableTasks, mergeTaskSnapshot, validatedRows } from "app/utils/taskRefresh";

export default function useSendtaskList() {
    const { enqueueSnackbar } = useSnackbar();

    const [loading, setLoading] = useState(true);
    const [snapshot, setSnapshot] = useState({ tasks: [], stats: {} });
    const { tasks: tasksData, stats: statsData } = snapshot;
    const [isCheckingSends, setIsCheckingSends] = useState(false); // 新增
    const { createController } = useAbortOnUnmount();  //控制網頁關閉時結束api
    const { isAuthenticated, user } = useAuth();

    // 客戶帳號使用 useCustomer hook，不走此處的管理員 API
    const isCustomer = user?.user_type === "customer";

    // 用於追蹤所有進行中的請求
    const activeRequestsRef = useRef(new Set());
    const pendingRefreshUuidsRef = useRef(new Set());
    const refreshTimerRef = useRef(null);
    const refreshTasksByUuidsRef = useRef(null);
    const refreshRef = useRef(null);
    const sequenceRef = useRef(0);
    const pendingFullRef = useRef(false);
    const fullInFlightRef = useRef(false);
    const partialInFlightRef = useRef(false);
    const scheduleRef = useRef(null);
    const snapshotRef = useRef(snapshot);
    snapshotRef.current = snapshot;
    const [todayBounds, setTodayBounds] = useState(() => getTaipeiDayBounds());

    useEffect(() => {
        if (!isAuthenticated || isCustomer) return undefined;

        let currentDay = getTaipeiDayBounds();
        let midnightTimer;
        setTodayBounds(currentDay);

        const checkDay = () => {
            const now = Date.now();
            const nextDay = getTaipeiDayBounds(now);
            if (nextDay.start !== currentDay.start) {
                currentDay = nextDay;
                setTodayBounds(nextDay);
                refreshRef.current?.();
            }
            window.clearTimeout(midnightTimer);
            midnightTimer = window.setTimeout(checkDay, nextDay.end - now);
        };
        const handleVisibility = () => {
            if (!document.hidden) {
                checkDay();
                scheduleRef.current?.([], true);
            }
        };

        checkDay();
        window.addEventListener("focus", handleVisibility);
        document.addEventListener("visibilitychange", handleVisibility);
        return () => {
            window.clearTimeout(midnightTimer);
            window.removeEventListener("focus", handleVisibility);
            document.removeEventListener("visibilitychange", handleVisibility);
        };
    }, [isAuthenticated, isCustomer]);

    useEffect(() => {
        if (isAuthenticated && !isCustomer) {
            setLoading(true);
            refreshRef.current?.();
        } else {
            sequenceRef.current += 1;
            setSnapshot({ tasks: [], stats: {} });
            setLoading(false);
        }
    }, [isAuthenticated, isCustomer, user?.name]);

    const refreshTasksByUuids = async (uuids) => {
        const uniqueUuids = [...new Set(uuids)].filter(Boolean);
        if (!uniqueUuids.length || isCustomer) return;
        if (fullInFlightRef.current || partialInFlightRef.current) {
            scheduleRef.current?.([], true);
            return;
        }

        const sequence = ++sequenceRef.current;
        partialInFlightRef.current = true;
        try {
            const tasksResponse = await axios.post('/api/customer_get_sendtasks', { sendtask_uuids: uniqueUuids });
            validatedRows(tasksResponse.data);
            const statsResponse = await axios.post('/api/get_sendlog_stats', { sendtask_uuids: uniqueUuids });
            const verified = await axios.post('/api/customer_get_sendtasks', { sendtask_uuids: uniqueUuids });
            assertStableTasks(tasksResponse.data, verified.data);
            const next = mergeTaskSnapshot(snapshotRef.current.tasks, snapshotRef.current.stats,
                tasksResponse.data, statsResponse.data, uniqueUuids);
            if (sequence === sequenceRef.current) setSnapshot(next);
        } catch (error) {
            console.error("局部更新 Dashboard 任務失敗", error);
            if (sequence === sequenceRef.current) enqueueSnackbar(`任務刷新失敗：${error.message}`, { variant: 'error' });
        } finally {
            partialInFlightRef.current = false;
        }
    };
    refreshTasksByUuidsRef.current = refreshTasksByUuids;

    const fetchData = async (controller) => {
        const sequence = ++sequenceRef.current;
        fullInFlightRef.current = true;
        try {
            const { data: json } = await axios.post("/api/get_sendtasks",
                {},
                { signal: controller.signal }
            );

            const tasks = validatedRows(json);
            const stats = tasks.length ? (await axios.post('/api/get_sendlog_stats', {
                sendtask_uuids: tasks.map(task => task.sendtask_uuid),
            }, { signal: controller.signal })).data : { status: 'success', data: [] };
            const verified = (await axios.post('/api/get_sendtasks', {}, { signal: controller.signal })).data;
            assertStableTasks(json, verified);
            const next = mergeTaskSnapshot([], {}, json, stats);
            if (sequence === sequenceRef.current) setSnapshot(next);
        } catch (error) {
            if (error.name === "AbortError") {
                // 請求被中斷，不需要顯示錯誤
            } else {
                if (!axios.isCancel(error) && sequence === sequenceRef.current) {
                    enqueueSnackbar(`任務刷新失敗：${error.message}`, { variant: 'error' });
                }
            }
        } finally {
            if (sequence === sequenceRef.current) {
                fullInFlightRef.current = false;
                setLoading(false);
            }
        }
    };

    const exportCsv = async (sendtasks, { onDownloadProgress } = {}) => {
        try {
            // sendtasks 格式: { sendtask_id1: [sendtask_uuid1, pre_test_enable1], sendtask_id2: [sendtask_uuid2, pre_test_enable2], ... }
            const response = await axios.post(
                "/api/export_xlsx",
                { sendtasks },
                {
                    responseType: "blob", // 重要！讓 axios 以二進位方式處理回應
                    onDownloadProgress, // 傳遞進度更新回呼函式
                }
            );
            // 取得檔名
            const disposition = response.headers["content-disposition"];
            let filename = "sendtasks_export.zip";
            if (disposition) {
                const match = disposition.match(/filename="?([^"]+)"?/);
                if (match) filename = decodeURIComponent(match[1]);
            }
            // 下載檔案
            const url = window.URL.createObjectURL(new Blob([response.data]));
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", filename);
            document.body.appendChild(link);
            link.click();
            link.remove();
            window.URL.revokeObjectURL(url);
        } catch (error) {
            enqueueSnackbar(`匯出失敗：${(error?.message || "未知錯誤")}`, { variant: 'warning' });
        }
    };

    // 提供 refresh 方法
    function refresh() {
        if (!isAuthenticated || isCustomer) return;
        if (partialInFlightRef.current || fullInFlightRef.current) {
            scheduleRef.current?.([], true);
            return;
        }
        const controller = createController();
        return fetchData(controller);
    }
    refreshRef.current = refresh;

    function scheduleRefresh(uuids, full = false) {
        if (!isAuthenticated || isCustomer) return;
        uuids.forEach(uuid => pendingRefreshUuidsRef.current.add(uuid));
        pendingFullRef.current ||= full;
        if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current);
        refreshTimerRef.current = window.setTimeout(() => {
            const requested = [...pendingRefreshUuidsRef.current];
            const reload = pendingFullRef.current;
            pendingRefreshUuidsRef.current.clear();
            pendingFullRef.current = false;
            if (reload) refreshRef.current?.();
            else refreshTasksByUuidsRef.current?.(requested);
        }, 250);
    }
    scheduleRef.current = scheduleRefresh;

    // 註冊請求控制器
    const registerRequest = (controller) => {
        activeRequestsRef.current.add(controller);
        return () => {
            activeRequestsRef.current.delete(controller);
        };
    };

    // 中止所有進行中的請求
    const abortAllRequests = () => {
        activeRequestsRef.current.forEach(controller => {
            try {
                controller.abort();
            } catch (error) {
                console.log(error)
                // 忽略已經中止的請求
            }
        });
        activeRequestsRef.current.clear();
        setIsCheckingSends(false);
    };


    useEffect(() => {
        // 監聽頁面重新整理和關閉事件
        const handleBeforeUnload = (event) => {
            if (isCheckingSends) {
                event.preventDefault();
                event.returnValue = '有正在進行的更新任務，確定要離開嗎？';
                return event.returnValue;
            }
        };

        // 監聽頁面實際卸載事件
        const handleUnload = () => {
            if (isCheckingSends) {
                abortAllRequests();
            }
        };

        // 監聽頁面獲得焦點（用戶取消離開後回到頁面）
        const handleFocus = () => {
            if (isCheckingSends) {
                // console.log('用戶取消離開，任務繼續進行');
            }
        };

        // 監聽頁面可見性變化
        const handleVisibilityChange = () => {
            if (!document.hidden && isCheckingSends) {
                // console.log('頁面重新可見，任務繼續進行');
            } else if (document.hidden && isCheckingSends) {
                // console.log('頁面已隱藏，但保持請求繼續進行');
            }
        };

        window.addEventListener('beforeunload', handleBeforeUnload);
        window.addEventListener('unload', handleUnload);
        window.addEventListener('focus', handleFocus);
        document.addEventListener('visibilitychange', handleVisibilityChange);

        return () => {
            window.removeEventListener('beforeunload', handleBeforeUnload);
            window.removeEventListener('unload', handleUnload);
            window.removeEventListener('focus', handleFocus);
            document.removeEventListener('visibilitychange', handleVisibilityChange);
        };
    }, [isCheckingSends]);

    useEffect(() => {
        return () => {
            // 組件卸載時中止所有請求
            abortAllRequests();
            sequenceRef.current += 1;
            fullInFlightRef.current = false;
            partialInFlightRef.current = false;
        };
    }, []);

    useEffect(() => {
        const handleItemsCompleted = (event) => {
            scheduleRef.current?.(event.detail?.uuids || [], event.detail?.reloadList === true);
        };

        window.addEventListener('taskDataInvalidated', handleItemsCompleted);
        return () => {
            window.removeEventListener('taskDataInvalidated', handleItemsCompleted);
            if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current);
        };
    }, [isAuthenticated, isCustomer]);

    const todayTasks = tasksData.filter(row =>
        isTodayTask(row, statsData[row.sendtask_uuid], todayBounds)
    );

    return {
        loading,
        statsData,
        tasksData,
        todayTasks,
        todayBounds,
        refresh,
        refreshTasksByUuids,
        isCheckingSends,
        setIsCheckingSends,
        registerRequest,    // 註冊請求
        abortAllRequests,    // 中止所有請求
        exportCsv
    };
    // statsData: { [sendtask_uuid]: stats, ... }
    // tasksData: [{ sendtask_id, ... }, ...]
    // todayTasks: [{ sendtask_id, ... }, ...] 只包含今日有計畫的任務

}