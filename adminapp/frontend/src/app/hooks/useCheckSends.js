import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";

export function useCheckSends({ refresh, setIsCheckingSends, setUpdatedTodayUuids }) {
    const { createController } = useAbortOnUnmount();

    // 更新寄送任務的狀態
    const fetchCheckSends = async (uuids = []) => {
        setIsCheckingSends(true);

        // 彈出確認視窗
        if (!window.confirm("確定要執行寄送狀態更新嗎？")) {
            return;
        }
        // 建立新的 controller，並中斷前一個請求
        const controller = createController();
        // 只取今日未寄送最早的 plan_time 非0的任務
        if (!uuids || uuids.length === 0) {
            // 如果沒有任務就直接結束
            alert("無任務可更新");
            setIsCheckingSends(false);
            return;
        }

        const chunkSize = Math.ceil(uuids.length / 3); // 將 UUID 分成三等份
        const uuidChunks = [];
        for (let i = 0; i < uuids.length; i += chunkSize) {
            uuidChunks.push(uuids.slice(i, i + chunkSize));
        }
        
        try {
            const fetchPromises = uuidChunks.map(chunk =>
                fetch("/api/refresh_sendlog_stats", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ sendtask_uuids: chunk }),
                    signal: controller.signal,
                }).then(res => res.json())
            );        
            const results = await Promise.all(fetchPromises);

            // 提取所有 "updated" 的 UUID
            const updatedUuids = results.flatMap(json => {
                const stats = json.sendlog_stats_status || {};
                return Object.entries(stats)
                    .filter(([, status]) => status === "changed")
                    .map(([uuid]) => uuid);
            });
            setUpdatedTodayUuids(updatedUuids);
            if (updatedUuids.length === 0) {
                alert("任務已是最新狀態");
            } else {
                alert(`${updatedUuids.length} 筆任務已更新`);
                refresh(); // 重新載入任務列表
            }
        } catch (err) {
            if (err.name === "AbortError") {
                // 請求被中止，不顯示錯誤
            } else {
                console.error("發生錯誤", err);
                alert("伺服器錯誤，請稍後再試");
            }
        } finally {
            setIsCheckingSends(false);
        }
    };

    return { fetchCheckSends };
}