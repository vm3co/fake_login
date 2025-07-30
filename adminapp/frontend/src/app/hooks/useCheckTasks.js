import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";
import axios from "axios";


function getCookie(name) {
    const value = document.cookie
        .split("; ")
        .find(row => row.startsWith(`${name}=`));
    const valueArr = value ? JSON.parse(decodeURIComponent(value.split("=")[1])) : [];
    return valueArr;
}

export function useCheckTasks({ refresh, setIsCheckingSends }) {
    const { controllerRef, createController } = useAbortOnUnmount();

    // 檢查新增或移除的任務
    const fetchCheckTasks = async () => {
        // 彈出確認視窗
        if (!window.confirm("確定要執行任務列表更新嗎？")) {
            return;
        }

        // 先中止前一個請求
        if (controllerRef.current) {
            controllerRef.current.abort();
        }

        setIsCheckingSends(true);
        // 從 Cookie 中取得 orgs
        const orgsArr = getCookie("orgs");
        // 建立新的 controller
        const controller = createController();

        await axios.post("/api/check_sendtasks", 
            { orgs: orgsArr },
            { signal: controller.signal }
        )
            .then((res) => res.data)
            .then((json) => {
                if (json.status === "success") {
                    const { added, removed } = json.data;
                    // 取出 sendtask_id 並格式化成多行文字
                    const addedIds = added.map(item => `- ${item.sendtask_id}`).join("\n");
                    const removedIds = removed.map(item => `- ${item.sendtask_id}`).join("\n");
                    const message =
                        `新增 ${added.length} 筆：\n${addedIds || "(無)"}\n\n` +
                        `移除 ${removed.length} 筆：\n${removedIds || "(無)"}`;
                    alert(message);
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

    return { fetchCheckTasks };
}