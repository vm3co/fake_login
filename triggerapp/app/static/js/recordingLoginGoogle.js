// !! 確認form、email這兩個變數指定的id
// !! html的部分，要確認<form></form> 有沒有加上、email的欄位的id對不對
// !! 還要加上 <script src="/static/js/recordingLogin.js"></script>

const url = window.location.href;

// // 進頁面 送 IP 紀錄
// fetch(`${API_BASE_PATH}/api/visit`, {
//   method: "POST",
//   headers: { "Content-Type": "application/json" },
//   body: JSON.stringify({ url: url })
// })
// .then(response => {
//     if (!response.ok) {
//         console.error("Initial fetch failed:", response.statusText);
//     }
// })
// .catch(err => {
//     console.error("Error during initial fetch:", err);
// });

// 使用者提交 email
const loginButton = document.getElementById("login-button");

if (loginButton) {
    loginButton.addEventListener("click", function () {
        // 優先順序：
        // 1. data-role="login-input"
        // 2. type="email"
        // 3. 第一個 visible text input
        // 4. fallback id="email"
        let emailInput = document.querySelector('[data-role="login-input"]');
        if (!emailInput) {
            emailInput = document.querySelector('input[type="email"]');
        }
        if (!emailInput) {
            // Find first text input that is not hidden
            const textInputs = document.querySelectorAll('input[type="text"]');
            for (let i = 0; i < textInputs.length; i++) {
                if (textInputs[i].offsetParent !== null) { // Simple visibility check
                    emailInput = textInputs[i];
                    break;
                }
            }
        }
        if (!emailInput) {
            emailInput = document.getElementById("email");
        }

        if (!emailInput) {
            console.error("Could not find input element!");
            return; // 如果找不到輸入框，停止執行
        }

        const inputValue = emailInput.value;

        fetch(`${API_BASE_PATH}/api/input`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                email: inputValue,
                input_data: inputValue,
                url: url
            })
        })
            .then(response => {
                if (!response.ok) {
                    console.error("Input fetch failed:", response.statusText);
                    throw new Error("伺服器錯誤");
                }
                return response.text();
            })
            .then(data => {
                // 重新導向到警告頁面
                window.location.href = `${API_BASE_PATH}/warning`;
            })
            .catch(err => {
                alert("⚠️ 登入失敗：" + err.message);
            });
    });
} else {
    // 如果找不到按鈕，在這裡報錯
    console.error("Could not find login button element!");
}
