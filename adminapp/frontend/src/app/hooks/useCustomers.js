import { useState, useRef, useEffect } from "react";
import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";
import useAuth from "app/hooks/useAuth";
import axios from "axios";


// 取得 Cookie 函式
function getCookie(name) {
    const value = document.cookie
        .split("; ")
        .find(row => row.startsWith(`${name}=`));
    try {
        return value ? JSON.parse(decodeURIComponent(value.split("=")[1])) : [];
    } catch {
        return value ? decodeURIComponent(value.split("=")[1]) : null;
    }
}

export default function useCustomers() {
    const [loading, setLoading] = useState(false);
    const [customers, setCustomers] = useState([]);
    const [error, setError] = useState(null);
    const [success, setSuccess] = useState(null);
    const { createController } = useAbortOnUnmount();
    const { isAuthenticated } = useAuth();

    // 用於追蹤所有進行中的請求
    const activeRequestsRef = useRef(new Set());

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
                console.log('Aborting request:', error);
            }
        });
        activeRequestsRef.current.clear();
        setLoading(false);
    };

    // 創建客戶
    const createCustomer = async (customerData) => {
        const controller = createController();
        const cleanup = registerRequest(controller);

        try {
            setLoading(true);
            setError(null);
            setSuccess(null);

            // 獲取當前用戶的 UUID（從 cookie 或其他地方）
            const acct_uuid = getCookie("acct_uuid") || ""; // 需要根據實際情況調整

            const response = await axios.post("/api/create_customer", { 
                customer_name: customerData.customername.trim(),
                customer_full_name: customerData.customerfullname.trim(),
                password: customerData.password,
                acct_uuid: acct_uuid
            }, {
                signal: controller.signal,
            });

            const result = await response.data;

            if (result.status === "success") {
                setSuccess(`客戶 ${result.customer_name} 創建成功！`);
                alert(`客戶 ${result.customer_name} 創建成功！`);
                await fetchCustomers();
                return result;
            } else {
                throw new Error(result.message || "創建客戶失敗");
            }
        } catch (error) {
            if (error.name === "AbortError") {
                console.log("創建客戶請求被中止");
            } else {
                console.error("創建客戶失敗:", error);
                setError(error.message || "網路錯誤，請稍後再試");
                throw error;
            }
        } finally {
            setLoading(false);
            cleanup();
        }
    };

    // 獲取客戶列表
    const fetchCustomers = async () => {
        const controller = createController();
        const cleanup = registerRequest(controller);
        
        try {
            setLoading(true);
            setError(null);

            const acct_uuid = getCookie("acct_uuid") || "";
            if (!acct_uuid) {
                throw new Error("未找到帳戶 UUID，請先登錄");
            }

            const response = await axios.post("/api/get_customers", {
                acct_uuid: acct_uuid
            }, {
                signal: controller.signal,
            });

            const result = response.data;
            
            if (result.status === "success") {
                setCustomers(result.data || []);
                return result.data;
            } else {
                throw new Error(result.message || "獲取客戶帳號列表失敗");
            }
        } catch (error) {
            if (error.name === "AbortError") {
                console.log("獲取客戶帳號列表請求被中止");
            } else {
                console.error("獲取客戶帳號列表失敗:", error);
                setError(error.message || "網路錯誤，請稍後再試");
            }
        } finally {
            setLoading(false);
            cleanup();
        }
    };

    // 更新客戶任務
    const updateCustomerSendtasks = async (customerName, sendtask_uuids) => {
        const controller = createController();
        const cleanup = registerRequest(controller);

        try {
            setLoading(true);
            setError(null);
            setSuccess(null);

            const response = await axios.post("/api/update_customer_sendtasks", {
                customer_name: customerName,
                sendtask_uuids: sendtask_uuids
            }, {
                signal: controller.signal,
            });

            const result = response.data;

            if (result.status === "success") {
                setSuccess(`成功為客戶 ${customerName} 添加任務`);
                alert(`成功為客戶 ${customerName} 添加任務`);
                await fetchCustomers();
                return result;
            } else {
                throw new Error(result.message || "添加任務失敗");
            }
        } catch (error) {
            if (error.name === "AbortError") {
                console.log("添加客戶任務請求被中止");
            } else {
                console.error("添加客戶任務失敗:", error);
                setError(error.message || "網路錯誤，請稍後再試");
                throw error;
            }
        } finally {
            setLoading(false);
            cleanup();
        }
    };

    // 刪除客戶
    const deleteCustomer = async (customerNames) => {
        // 彈出確認視窗
        if (!window.confirm("確定要刪除客戶帳號嗎？")) {
            return;
        } 

        const controller = createController();
        const cleanup = registerRequest(controller);

        try {
            setLoading(true);
            setError(null);
            setSuccess(null);
            console.log(customerNames);

            const response = await axios.post("/api/delete_customer", { 
                del_customer_names: customerNames 
            }, {
                signal: controller.signal,
            });

            const result = response.data;

            if (result.status === "success") {
                setSuccess(`客戶 ${customerNames} 刪除成功`);
                alert(`客戶 ${customerNames} 刪除成功`);
                await fetchCustomers();
                return result;
            } else {
                throw new Error(result.message || "刪除客戶失敗");
            }
        } catch (error) {
            if (error.name === "AbortError") {
                console.log("刪除客戶請求被中止");
            } else {
                console.error("刪除客戶失敗:", error);
                setError(error.message || "網路錯誤，請稍後再試");
                throw error;
            }
        } finally {
            setLoading(false);
            cleanup();
        }
    };

    // 更新客戶密碼
    const updateCustomerPassword = async (customerName, oldPassword, newPassword) => {
        const controller = createController();
        const cleanup = registerRequest(controller);

        try {
            setLoading(true);
            setError(null);
            setSuccess(null);

            const response = await axios.post("/api/update_customer_password", {
                customer_name: customerName,
                old_password: oldPassword,
                new_password: newPassword
            }, {
                signal: controller.signal,
            });

            const result = response.data;

            if (result.status === "success") {
                setSuccess(`客戶 ${customerName} 密碼更新成功`);
                alert(`客戶 ${customerName} 密碼更新成功`);
                return result;
            } else {
                throw new Error(result.message || "密碼更新失敗");
            }
        } catch (error) {
            if (error.name === "AbortError") {
                console.log("更新密碼請求被中止");
            } else {
                console.error("更新密碼失敗:", error);
                setError(error.message || "網路錯誤，請稍後再試");
                throw error;
            }
        } finally {
            setLoading(false);
            cleanup();
        }
    };

    // 清除訊息
    const clearMessages = () => {
        setError(null);
        setSuccess(null);
    };

    // 刷新數據
    const refresh = () => {
        fetchCustomers();
    };

    useEffect(() => {
        if (isAuthenticated) {
            setLoading(true);
            fetchCustomers();
            console.log("Customers data refreshed");
        } else {
            setCustomers([]);
            setLoading(false);
            console.log("User is not authenticated");
        }
    }, [isAuthenticated]);

    return {
        // 狀態
        loading,
        customers,
        error,
        success,
        
        // 方法
        createCustomer,
        fetchCustomers,
        updateCustomerSendtasks,
        deleteCustomer,
        updateCustomerPassword,
        clearMessages,
        refresh,
        
        // 控制方法
        abortAllRequests,
        registerRequest
    };
}