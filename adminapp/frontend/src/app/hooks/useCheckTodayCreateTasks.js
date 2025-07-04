import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";

function getCookie(name) {
    const value = document.cookie
        .split("; ")
        .find(row => row.startsWith(`${name}=`));
    const valueArr = value ? JSON.parse(decodeURIComponent(value.split("=")[1])) : [];
    return valueArr;
}

export function useCheckTodayCreateTasks({ refresh, setIsCheckingSends }) {
    const { controllerRef, createController } = useAbortOnUnmount();

    // 檢查新增或移除的任務
    const fetchCheckTodayCreateTasks = () => {
        // 彈出確認視窗
        if (!window.confirm("確定要執行檢查今日建立任務嗎？")) {
            return;
        }
        
        setIsCheckingSends(true);
        // 先中止前一個請求
        if (controllerRef.current) {
            controllerRef.current.abort();
        }
        // 從 Cookie 中取得 orgs
        const orgsArr = getCookie("orgs");
        // 建立新的 controller
        const controller = createController();

        fetch("/api/refresh_today_create_task", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ orgs: orgsArr }),
            signal: controller.signal,
        })
            .then((res) => res.json())
            .then((json) => {
                if (json.status === "success") {
                    const sendlog_stats_status = json.data;
                    // 提取所有 "updated" 的 UUID
                    const updatedUuids = Object.entries(sendlog_stats_status)
                            .filter(([, status]) => status === "changed")
                            .map(([uuid]) => uuid);
                    alert(`更新 ${updatedUuids.length} 筆：\n${updatedUuids.join("\n") || "(無)"}`);
                    // 再次取得最新任務資料
                    refresh();
                } else {
                    alert("檢查任務失敗：" + json.message);
                }
                setIsCheckingSends(false);
            })
            .catch((err) => {
            if (err.name === "AbortError") {
                // 請求被中止，不顯示錯誤
            } else {
                console.error("發生錯誤", err);
                alert("伺服器錯誤，請稍後再試");
            }
            setIsCheckingSends(false);
        });
    };

    return { fetchCheckTodayCreateTasks };
}