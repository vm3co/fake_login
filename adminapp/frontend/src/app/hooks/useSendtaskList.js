import { useEffect, useState, useRef } from "react";
import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";


// 取得 Cookie 函式
function getCookie(name) {
    const value = document.cookie
        .split("; ")
        .find(row => row.startsWith(`${name}=`));
    const valueArr = value ? JSON.parse(decodeURIComponent(value.split("=")[1])) : [];
    return valueArr;
}

export default function useSendtaskList() {
    const [loading, setLoading] = useState(true);
    const [tasksData, setTasksData] = useState([]);
    const [statsData, setStatsData] = useState({}); // 存所有統計資料
    const [isCheckingSends, setIsCheckingSends] = useState(false); // 新增
    const { createController } = useAbortOnUnmount();  //控制網頁關閉時結束api

    // 用於追蹤所有進行中的請求
    const activeRequestsRef = useRef(new Set());

    const fetchStats = async (uuids) => {
        if (!uuids.length) return;
        // 批次取得所有統計
        const res = await fetch("/api/get_sendlog_stats", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ sendtask_uuids: uuids }),
        });

        const json = await res.json();
        const statsList = json.data || [];
        // 轉成 { uuid: stats, ... }
        const statsObj = {};
        statsList.forEach(stats => {
            statsObj[stats.sendtask_uuid] = stats;
        });
        setStatsData(statsObj);
    };

    const fetchData = async (orgsArr, controller) => {
        try {
            const res = await fetch("/api/get_sendtasks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ orgs: orgsArr }),
                signal: controller.signal,
            });

            const json = await res.json();
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
                console.error("取得任務列表失敗", error);
            }
        } finally {
            setLoading(false);
        }
    };

    // 提供 refresh 方法
    function refresh() {
        const controller = createController();
        const orgs = getCookie("orgs");
        fetchData(orgs, controller);
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
        setLoading(true);
        refresh();
    }, []);


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
                console.log('用戶取消離開，任務繼續進行');
            }
        };

        // 監聽頁面可見性變化
        const handleVisibilityChange = () => {
            if (!document.hidden && isCheckingSends) {
                console.log('頁面重新可見，任務繼續進行');
            } else if (document.hidden && isCheckingSends) {
                console.log('頁面已隱藏，但保持請求繼續進行');
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
        isCheckingSends, 
        setIsCheckingSends,
        registerRequest,    // 註冊請求
        abortAllRequests    // 中止所有請求
    };
    // statsData: { [sendtask_uuid]: stats, ... }
    // tasksData: [{ sendtask_id, ... }, ...]
    // todayTasks: [{ sendtask_id, ... }, ...] 只包含今日有計畫的任務

}