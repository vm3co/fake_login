// !! 確認form、email這兩個變數指定的id
// !! html的部分，要確認<form></form> 有沒有加上、email的欄位的id對不對
// !! 還要加上 <script src="/static/js/recordingLoginGoogle.js"></script>
// !! 下載按鈕觸發：在元素上加 data-role="download-trigger"

const BASE_PATH = (typeof API_BASE_PATH !== 'undefined') ? API_BASE_PATH : "";
const url = window.location.href;

// // 進頁面 送 IP 紀錄
// fetch(`${BASE_PATH}/api/visit`, {
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

/**
 * 共用的後端紀錄函式
 * @param {string} inputValue - 要記錄的輸入值（登入時為帳號，下載時為 "DOWNLOAD_TRIGGERED"）
 */
function sendInputRecord(inputValue) {
    fetch(`${BASE_PATH}/api/input`, {
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
            // 檢查網址參數是否有指定跳轉頁面
            const urlParams = new URLSearchParams(window.location.search);
            const redirectUrl = urlParams.get('redirect_url');

            if (redirectUrl) {
                if (redirectUrl === 'self') {
                    // 導回自己 (刷新頁面)
                    window.location.reload();
                } else if (redirectUrl === 'password') {
                    // 導回密碼警告頁面
                    window.location.href = `${BASE_PATH}/password-wrong`;
                } else {
                    window.location.href = redirectUrl;
                }
            } else {
                // 重新導向到警告頁面
                window.location.href = `${BASE_PATH}/warning`;
            }
        })
        .catch(err => {
            alert("⚠️ 錯誤：" + err.message);
        });
}

// ── 觸發方式一：登入按鈕點擊 (id="login-button") ────────────────────────────
const loginButton = document.getElementById("login-button");

if (loginButton) {
    loginButton.addEventListener("click", function () {
        // 優先順序：
        // 1. data-role="login-input" (支援多個，用 " | " 分隔)
        // 2. 所有 visible text input (支援多個，用 " | " 分隔)

        let inputValues = [];
        const customInputs = document.querySelectorAll('[data-role="login-input"]');

        if (customInputs.length > 0) {
            customInputs.forEach(input => {
                inputValues.push(input.value);
            });
        } else {
            // Fallback Logic
            let emailInput = document.querySelector('input[type="email"]');

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

            if (emailInput) {
                inputValues.push(emailInput.value);
            }
        }

        if (inputValues.length === 0) {
            console.error("Could not find input element!");
            return; // 如果找不到輸入框，停止執行
        }

        const inputValue = inputValues.join(" | ");
        sendInputRecord(inputValue);
    });
} else {
    // 如果找不到按鈕，在這裡報錯
    console.error("Could not find login button element!");
}

// ── 觸發方式二：下載按鈕點擊 (data-role="download-trigger") ─────────────────
// 支援頁面上多個下載按鈕
const downloadTriggers = document.querySelectorAll('[data-role="download-trigger"]');
downloadTriggers.forEach(btn => {
    btn.addEventListener("click", function (event) {
        event.preventDefault();
        sendInputRecord("DOWNLOAD_TRIGGERED");
    });
});

