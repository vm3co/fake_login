import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import "bootstrap/dist/css/bootstrap.min.css";

// 註冊頁面
function Register() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordCheck, setPasswordCheck] = useState("");
  const navigate = useNavigate(); // 初始化 useNavigate

  // 切換主題
  useEffect(() => {
    document.body.className = isDarkMode ? 'dark-theme' : 'light-theme';
  }, [isDarkMode]);

  const handleRegister = async (e) => {
    e.preventDefault();
    const res = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    const data = await res.json();
    if (data.status === "success") {
      alert("註冊成功，請登入");
      navigate("/login");
    } else {
      alert(data.msg || "註冊失敗");
    }
  };
  return (
    <>
      <div style={{ padding: "1rem", textAlign: "right" }}>
        <button onClick={() => setIsDarkMode(prev => !prev)}>
          {isDarkMode ? "light" : "dark"}
        </button>
      </div> 
      <div className="task-detail-dark"> 
        <div className="container mt-4">
          {/* Header 標題 */}
          <h2 className="mb-4 text-center">社交工程紀錄後台</h2>
          {/* 製作註冊頁面 */}
          <div className="register-form">
            <form onSubmit={handleRegister}>
              <div className="mb-3">
                <label htmlFor="email" className="form-label">
                  使用者電子郵件
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="email"
                  placeholder="輸入使用者電子郵件"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>
              <div className="mb-3">
                <label htmlFor="password" className="form-label">
                  密碼
                </label>
                <input
                  type="password"
                  className="form-control"
                  id="password"
                  placeholder="輸入密碼"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>
              <div className="mb-3">
                <label htmlFor="passwordCheck" className="form-label">
                  確認密碼
                </label>
                <input
                  type="password"
                  className="form-control"
                  id="passwordCheck"
                  placeholder="確認密碼"
                  value={passwordCheck}
                  onChange={(e) => setPasswordCheck(e.target.value)}
                />
              </div>
              <div className="text-center">
                <button type="submit" className="btn btn-primary">
                  連接到社交工程平台
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
      {/* Footer 底部 */}
      <footer className="mt-4">
        <p className="text-center">© 2025 社交工程紀錄後台</p>
      </footer>
    </>
  );
}

export default Register;
