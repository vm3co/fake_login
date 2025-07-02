// 格式化時間戳記
export default function formatDate(ts, type = "datetime") {
    if (!ts) return "";
    // 統一轉換為整數，處理 string、int、float
    let t;
    if (typeof ts === "string") {
        t = parseInt(ts, 10);
    } else if (typeof ts === "number") {
        t = Math.floor(ts); // 使用 Math.floor 去除小數部分
    } else {
        return ""; // 無效輸入
    }
    // 判斷是否為秒級（10位數）或毫秒級（13位數）
    const date = t > 1e12 ? new Date(t) : new Date(t * 1000);
    const options = {
        // year: "numeric",    // 2025
        // month: "2-digit",   // 01
        // day: "2-digit",     // 01
        // hour: "2-digit",    // 01
        // minute: "2-digit",  // 00
        // second: "2-digit",  // 00
        hour12: false          // 24小時制
    };
    if (type === "date") return date.toLocaleDateString("zh-TW", options); // 格式化為日期
    if (type === "time") return date.toLocaleTimeString("zh-TW", options); // 格式化為時間
    return date.toLocaleString("zh-TW", options);                          // 格式化為日期時間
}