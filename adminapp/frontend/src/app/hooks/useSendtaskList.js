import { useEffect, useState } from "react";
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
    const { createController } = useAbortOnUnmount();  //控制網頁關閉時結束api

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

    useEffect(() => {
        setLoading(true);
        refresh();
    }, []);

    const todayTasks = tasksData.filter(row => {
        const stats = statsData[row.sendtask_uuid];
        const hasStats = stats && stats.today_earliest_plan_time > 0;
        return hasStats;
    });

    console.log("useSendtaskList - final todayTasks:", todayTasks);
    console.log("useSendtaskList - final todayTasks.length:", todayTasks.length);

    return { loading, statsData, tasksData, todayTasks, refresh };
    // statsData: { [sendtask_uuid]: stats, ... }
    // tasksData: [{ sendtask_id, ... }, ...]
    // todayTasks: [{ sendtask_id, ... }, ...] 只包含今日有計畫的任務

}