import { useState, useRef } from 'react';
import useAbortOnUnmount from 'app/hooks/useAbortOnUnmount';
import axios from "axios";


function getCookie(name) {
    const value = document.cookie
        .split("; ")
        .find(row => row.startsWith(`${name}=`));
    const valueArr = value ? JSON.parse(decodeURIComponent(value.split("=")[1])) : [];
    return valueArr;
}

export default function useCustomer() {
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);
    const [sendtasksData, setSendtasksData] = useState([]);

    // 用於追蹤進行中的請求
    const activeRequestsRef = useRef(new Set());
    const { createController } = useAbortOnUnmount();

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
                // 忽略已經中止的請求
                console.log(error);
            }
        });
        activeRequestsRef.current.clear();
    };

    // 清除狀態訊息
    const clearMessages = () => {
        setError(null);
        setSuccess(null);
    };

    // 根據 sendtask_uuids 批次獲取多個任務的統整資料
    const fetchCustomerSendtasksData = async () => {
        const sendtaskUuids = getCookie("sendtask_uuids") || "";
        if (!Array.isArray(sendtaskUuids) || sendtaskUuids.length === 0) {
            return [];
        }
        const controller = createController();
        const cleanup = registerRequest(controller);

        try {
            setLoading(true);
            setError(null);

            // 同時獲取所有任務的資料
            const [sendtasksResponse, sendlogStatsResponse] = await Promise.all([
                // 獲取 sendtasks 資料
                axios.post("/api/customer_get_sendtasks", 
                    { sendtask_uuids: sendtaskUuids },
                    { signal: controller.signal }
                ),
                // 獲取 sendlog_stats 資料
                axios.post("/api/get_sendlog_stats", 
                    { sendtask_uuids: sendtaskUuids },
                    { signal: controller.signal }
                )
            ]);

            const sendtasksResult = sendtasksResponse.data;
            const sendlogStatsResult = sendlogStatsResponse.data;

            if (sendtasksResult.status !== "success" || sendlogStatsResult.status !== "success") {
                throw new Error("獲取任務資料失敗");
            }

            // 建立統計資料的查找表
            const statsMap = {};
            (sendlogStatsResult.data || []).forEach(stats => {
                statsMap[stats.sendtask_uuid] = stats;
            });

            // 統整資料
            const combinedDataList = (sendtasksResult.data || [])
                .map(sendtaskData => {
                    const statsData = statsMap[sendtaskData.sendtask_uuid] || {};
                    const end_ut = (sendtaskData.stop_time_new && sendtaskData.stop_time_new !== -1)
                                    ? sendtaskData.stop_time_new
                                    : sendtaskData.test_end_ut;
                    
                    return {
                        // sendtasks 資料
                        sendtask_uuid: sendtaskData.sendtask_uuid,
                        sendtask_id: sendtaskData.sendtask_id || '',
                        test_end_ut: end_ut || 0,
                        test_start_ut: sendtaskData.test_start_ut || 0,
                        is_pause: sendtaskData.is_pause || false,
                        stop_time_new: sendtaskData.stop_time_new || -1,

                        // sendlog_stats 資料
                        totalplanned: statsData.totalplanned || 0,
                        totalsend: statsData.totalsend || 0,
                        totalsuccess: statsData.totalsuccess || 0,
                        totaltriggered: statsData.totaltriggered || 0,
                        todayunsend: statsData.todayunsend || 0,
                        todaysend: statsData.todaysend || 0,
                        todaysuccess: statsData.todaysuccess || 0,
                        today_earliest_plan_time: statsData.today_earliest_plan_time || 0,
                        today_latest_plan_time: statsData.today_latest_plan_time || 0,
                        all_earliest_plan_time: statsData.all_earliest_plan_time || 0,
                        all_latest_plan_time: statsData.all_latest_plan_time || 0,

                        // 計算的額外資料
                        totalfailed: (statsData.totalsend || 0) - (statsData.totalsuccess || 0),
                        todayfailed: (statsData.todaysend || 0) - (statsData.todaysuccess || 0),
                        
                        // 任務狀態判斷
                        status: getTaskStatus(statsData),
                        
                        // 原始資料（如需要）
                        // raw_sendtask: sendtaskData,
                        // raw_stats: statsData
                    };
                });

            setSendtasksData(combinedDataList);
            
        } catch (error) {
            if (error.name === "AbortError") {
                console.log("批次獲取任務資料請求被中止");
            } else {
                console.error("批次獲取任務資料失敗:", error);
                setError(error.message || "網路錯誤，請稍後再試");
                throw error;
            }
        } finally {
            setLoading(false);
            cleanup();
        }
    };

    // 下載任務資料
    const downloadTaskData = async (taskData, filename = 'task_data.csv') => {
        try {
            // 將資料轉換為 CSV 格式
            const csvRows = [];
            const headers = Object.keys(taskData[0]);
            csvRows.push(headers.join(','));

            for (const row of taskData) {
                const values = headers.map(header => {
                    const escaped = ('' + row[header]).replace(/"/g, '""');
                    return `"${escaped}"`;
                });
                csvRows.push(values.join(','));
            }

            const dataStr = csvRows.join('\n');

            // 創建 Blob 物件
            const blob = new Blob([dataStr], { type: 'application/json' });
            
            // 創建下載連結
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            
            // 觸發下載
            document.body.appendChild(link);
            link.click();
            
            // 清理
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
            
            setSuccess(`成功下載任務資料: ${filename}`);
            console.log(`任務資料已下載: ${filename}`);
            
        } catch (error) {
            console.error("下載任務資料失敗:", error);
            setError("下載失敗，請稍後再試");
            throw error;
        }
    };

    // 輔助函數：判斷任務狀態
    const getTaskStatus = (stats) => {
        if (!stats) return 'unknown';
        
        const totalplanned = Number(stats.totalplanned) || 0;
        const totalsend = Number(stats.totalsend) || 0;
        // const todayunsend = Number(stats.todayunsend) || 0;
        // const todaysuccess = Number(stats.todaysuccess) || 0;
        // const todaysend = Number(stats.todaysend) || 0;
        // const todayfailed = todaysend - todaysuccess;
        
        // 今日任務狀態判斷
        // if (todayunsend > 0) {
        //     if (todaysuccess > 0 && todayfailed === 0) return 'running'; // 執行中
        //     if (todaysuccess === 0 && todayfailed === 0) return 'pending'; // 尚未開始
        //     if (todayfailed > 0) return 'error'; // 有錯誤
        // }
        
        // 整體任務狀態
        if (totalsend === 0) {
            return 'pending'; // 待開始
        } else if (totalplanned === totalsend) {
            return 'completed'; // 已完成
        } else {
            return 'active'; // 進行中
        }
    };

    return {
        // 狀態
        loading,
        error,
        success,
        
        // 客戶任務相關方法
        fetchCustomerSendtasksData,
        sendtasksData,           // 獲取客戶的任務資訊
        downloadTaskData,               // 下載任務資料
        
        // 工具方法
        clearMessages,
        abortAllRequests,
        registerRequest
    };
}