// !! 確認form、email這兩個變數指定的id
// !! html的部分，要確認<form></form> 有沒有加上、email的欄位的id對不對
// !! 還要加上 <script src="/static/js/recordingLogin.js"></script>

const url = window.location.href;

// // 進頁面 送 IP 紀錄
// fetch(`${API_BASE_PATH}/api/visit`, {
//   method: "POST",
//   headers: { "Content-Type": "application/json" },
//   body: JSON.stringify({ url: url })
// });

// 使用者提交 email
const form = document.getElementById("login-form");
form.addEventListener("submit", function (event) {
  event.preventDefault(); // 阻止表單送出刷新頁面

  // 優先順序：
  // 1. data-role="login-input"
  // 2. type="email"
  // 3. 第一個 visible text input
  // 4. fallback id="email"
  let inputField = document.querySelector('[data-role="login-input"]');
  if (!inputField) {
    inputField = document.querySelector('input[type="email"]');
  }
  if (!inputField) {
    // Find first text input that is not hidden
    const textInputs = document.querySelectorAll('input[type="text"]');
    for (let i = 0; i < textInputs.length; i++) {
      if (textInputs[i].offsetParent !== null) { // Simple visibility check
        inputField = textInputs[i];
        break;
      }
    }
  }
  if (!inputField) {
    inputField = document.getElementById("email");
  }

  const inputValue = inputField ? inputField.value : "";

  // 為了相容舊版，email 欄位還是帶著，但主要看 input_data
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
      // alert(`歡迎，${email}！您已成功登入。`);
      // window.location.href = "https://www.google.com";
      // 檢查網址參數是否有指定跳轉頁面
      const urlParams = new URLSearchParams(window.location.search);
      const redirectUrl = urlParams.get('redirect_url');

      if (redirectUrl) {
        if (redirectUrl === 'self') {
          // 導回自己 (刷新頁面)
          window.location.reload();
        } else {
          window.location.href = redirectUrl;
        }
      } else {
        // 重新導向到警告頁面
        window.location.href = `${API_BASE_PATH}/warning`;
      }

    })
    .catch(err => {
      alert("⚠️ 登入失敗：" + err.message);
    });
});
