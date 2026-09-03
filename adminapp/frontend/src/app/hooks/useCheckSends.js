import { useSnackbar } from 'notistack';
import { useJob } from "app/contexts/JobContext";


export function useCheckSends({ setIsCheckingSends, setUpdatedTodayUuids }) {
    const { enqueueSnackbar } = useSnackbar();
    const { startJob } = useJob();

    // 更新寄送任務的狀態
    const fetchCheckSends = async (uuids = []) => {
        // 彈出確認視窗
        if (!window.confirm("確定要執行寄送狀態更新嗎？")) {
            return false;
        }

        setIsCheckingSends(true);
        // 只取今日未寄送最早的 plan_time 非0的任務
        if (!uuids || uuids.length === 0) {
            // 如果沒有任務就直接結束
            enqueueSnackbar("無任務可更新", { variant: 'info' });
            setIsCheckingSends(false);
            return false;
        }

        try {
            const admission = await startJob("refresh_sendlog_stats", {
                uuids,
                ignore_archived: true,
            });
            if (!admission) return false;
            if (setUpdatedTodayUuids) setUpdatedTodayUuids(admission.accepted?.map((item) => item.sendtask_uuid) || []);
        } catch (err) {
            if (err.name === "AbortError") {
                // 請求被中止，不顯示錯誤
            } else {
                console.error("發生錯誤", err);
                enqueueSnackbar("伺服器錯誤，請稍後再試", { variant: 'error' });
            }
        } finally {
            setIsCheckingSends(false);
        }
        return true;
    };

    return { fetchCheckSends };
}