import { useEffect, useState, useRef } from "react";
import { useSnackbar } from 'notistack';
import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";
import useAuth from "app/hooks/useAuth";
import axios from "axios";

export default function useSendtaskList() {
    const { enqueueSnackbar } = useSnackbar();

    const [loading, setLoading] = useState(true);
    const [tasksData, setTasksData] = useState([]);
    const [statsData, setStatsData] = useState({}); // 存所有統計資料
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

    useEffect(() => {
        if (isAuthenticated && !isCustomer) {
            setLoading(true);
            refresh();
        } else {
            setTasksData([]);
            setStatsData({});
            setLoading(false);
        }
    }, [isAuthenticated, isCustomer]);

    const fetchStats = async (uuids) => {
        if (!uuids.length) return;
        // 批次取得所有統計
        const { data: json } = await axios.post("/api/get_sendlog_stats", {
            sendtask_uuids: uuids,
        });

        const statsList = json.data || [];
        // 轉成 { uuid: stats, ... }
        const statsObj = {};
        statsList.forEach(stats => {
            statsObj[stats.sendtask_uuid] = stats;
        });
        setStatsData(statsObj);
    };

    const refreshTasksByUuids = async (uuids) => {
        const uniqueUuids = [...new Set(uuids)].filter(Boolean);
        if (!uniqueUuids.length || isCustomer) return;

        try {
            const [tasksResponse, statsResponse] = await Promise.all([
                axios.post("/api/customer_get_sendtasks", { sendtask_uuids: uniqueUuids }),
                axios.post("/api/get_sendlog_stats", { sendtask_uuids: uniqueUuids }),
            ]);
            const updatedTasks = tasksResponse.data?.data || [];
            const updatedStats = statsResponse.data?.data || [];
            const taskMap = new Map(updatedTasks.map((task) => [task.sendtask_uuid, task]));

            setTasksData((current) => {
                const existingUuids = new Set(current.map((task) => task.sendtask_uuid));
                const merged = current.map((task) => taskMap.get(task.sendtask_uuid) || task);
                updatedTasks.forEach((task) => {
                    if (!existingUuids.has(task.sendtask_uuid)) merged.push(task);
                });
                return merged;
            });
            setStatsData((current) => {
                const next = { ...current };
                updatedStats.forEach((stats) => {
                    next[stats.sendtask_uuid] = stats;
                });
                return next;
            });
        } catch (error) {
            console.error("局部更新 Dashboard 任務失敗", error);
        }
    };
    refreshTasksByUuidsRef.current = refreshTasksByUuids;

    const fetchData = async (controller) => {
        try {
            const { data: json } = await axios.post("/api/get_sendtasks",
                {},
                { signal: controller.signal }
            );

            if (json.status === "success") {
                setTasksData(json.data);

                const uuidsToFetch = json.data.map(task => task.sendtask_uuid);

                if (uuidsToFetch.length === 0) {
                    setLoading(false);
                    setStatsData({});
                    return;
                }

                await fetchStats(uuidsToFetch);
            }
        } catch (error) {
            if (error.name === "AbortError") {
                // 請求被中斷，不需要顯示錯誤
            } else {
                // console.error("取得任務列表失敗", error);
            }
        } finally {
            setLoading(false);
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
        const controller = createController();
        fetchData(controller);
    }

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
        };
    }, []);

    useEffect(() => {
        const handleItemsCompleted = (event) => {
            (event.detail?.uuids || []).forEach((uuid) => pendingRefreshUuidsRef.current.add(uuid));
            if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current);
            refreshTimerRef.current = window.setTimeout(() => {
                const uuids = [...pendingRefreshUuidsRef.current];
                pendingRefreshUuidsRef.current.clear();
                refreshTasksByUuidsRef.current?.(uuids);
            }, 250);
        };

        window.addEventListener('jobItemsCompleted', handleItemsCompleted);
        return () => {
            window.removeEventListener('jobItemsCompleted', handleItemsCompleted);
            if (refreshTimerRef.current) window.clearTimeout(refreshTimerRef.current);
        };
    }, [isAuthenticated, isCustomer]);

    const todayTasks = tasksData.filter(row => {
        const stats = statsData[row.sendtask_uuid];
        const hasStats = stats && stats.today_earliest_plan_time > 0;
        return hasStats;
    });

    return {
        loading,
        statsData,
        tasksData,
        todayTasks,
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