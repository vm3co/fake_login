import { Routes, Route, Navigate, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import "bootstrap/dist/css/bootstrap.min.css";

function Login() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const [mail, setMail] = useState("");
  const [password, setPassword] = useState("");
  const navigate = useNavigate(); // 初始化 useNavigate

  // 切換主題
  useEffect(() => {
    document.body.className = isDarkMode ? 'dark-theme' : 'light-theme';
  }, [isDarkMode]);

  const handleLogin = async (e) => {
    e.preventDefault();
    // 呼叫後端 API
    const res = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: mail, password }),
    });
    const data = await res.json();
    if (data.status === "success") {
      document.cookie = "isLoggedIn=true; path=/;";
      document.cookie = `orgs=${encodeURIComponent(JSON.stringify(data.orgs))}; path=/;`; // 存入 orgs
      alert("登入成功！");
      navigate("/");
    } else {
      alert("登入失敗，請檢查帳號或密碼！");
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
          {/* 製作登入頁面 */}
          <div className="login-form">
            <form onSubmit={handleLogin}>
              <div className="mb-3">
                <label htmlFor="mail" className="form-label">
                  使用者電子郵件
                </label>
                <input
                  type="text"
                  className="form-control"
                  id="mail"
                  placeholder="輸入使用者電子郵件"
                  value={mail}
                  onChange={(e) => setMail(e.target.value)}
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
              <div className="text-center">
                <button type="submit" className="btn btn-primary">
                  登入
                </button>
              </div>
            </form>
            <br />
            <div className="text-center">
              <p>還沒有帳號？</p>
              <button
                className="btn btn-secondary"
                onClick={() => navigate("/register")}
              >
                註冊
              </button>
            </div>
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

export default Login;
