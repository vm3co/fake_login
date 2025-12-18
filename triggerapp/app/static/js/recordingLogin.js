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

  const email = document.getElementById("email").value;
  fetch(`${API_BASE_PATH}/api/input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email, url: url })
  })
    .then(response => {
      if (!response.ok) throw new Error("伺服器錯誤");
      return response.text();
    })
    .then(data => {
      // alert(`歡迎，${email}！您已成功登入。`);
      // window.location.href = "https://www.google.com";
      // 重新導向到警告頁面
      window.location.href = `${API_BASE_PATH}/warning`;

    })
    .catch(err => {
      alert("⚠️ 登入失敗：" + err.message);
      console.error(err);
    });
});
