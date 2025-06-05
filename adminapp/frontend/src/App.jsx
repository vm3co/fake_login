import { Routes, Route, Navigate, useNavigate, NavLink } from "react-router-dom";
import { useState, useEffect } from "react";
import "bootstrap/dist/css/bootstrap.min.css";
import "./App.css"
import CreateUrl from "./pages/createurl";
import ShowTasks from "./pages/showtasks";
import TaskDetail from "./pages/taskdetail";


function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}


function App() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const navigate = useNavigate(); // 初始化 useNavigate

  useEffect(() => {
    // 檢查是否已登入
    const isLoggedIn = getCookie("isLoggedIn");
    if (!isLoggedIn) {
      navigate("/login"); // 若未登入，跳轉到 Login 頁面
    }
  }, [navigate]);
  
  // 切換主題
  useEffect(() => {
    document.body.className = isDarkMode ? 'dark-theme' : 'light-theme';
  }, [isDarkMode]);



  return (
    <>
      <div style={{ padding: "1rem", textAlign: "right" }}>
        <button
          style={{ marginLeft: "1rem" }}
          className="btn btn-outline-danger btn-sm"
          onClick={() => {
            document.cookie = "isLoggedIn=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            document.cookie = "orgs=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
            navigate("/login");
          }}
        >
          登出
        </button>
        <button 
          style={{ marginLeft: "1rem" }} 
          onClick={() => setIsDarkMode(prev => !prev)}
        >
          {isDarkMode ? "light" : "dark"}
        </button>
      </div>

      <div className="task-detail-dark">
        <div className="container mt-4">
          {/* Header 標題 */}
          <h2 className="mb-4">社交工程紀錄後台</h2>

          {/* Bootstrap 導覽列 */}
          <nav className="mb-4">
            <ul className="nav nav-tabs">
              <li className="nav-item">
                <NavLink
                  to="/showtasks"
                  className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
                >
                  所有任務
                </NavLink>
              </li>
              <li className="nav-item">
                <NavLink
                  to="/createurl"
                  className={({ isActive }) => "nav-link" + (isActive ? " active" : "")}
                >
                  建立網址
                </NavLink>
              </li>
            </ul>
          </nav>

          {/* 路由設定 */}
          <Routes>
            <Route path="/" element={<Navigate to="/showtasks" />} />
            <Route path="/createurl" element={<CreateUrl />} />
            <Route path="/showtasks" element={<ShowTasks />} />
            <Route path="/showtasks/:uuid" element={<TaskDetail />} />

            {/* 所有找不到的路徑，導回 /showtasks */}
            <Route path="*" element={
              <div>
                <h3>找不到頁面！請確認網址是否正確。</h3>
                <a href="/">回首頁</a>
              </div>
            } />
          </Routes>
        </div>
      </div>
      {/* Footer 底部 */}
      <footer className="mt-4 footer-fixed-bottom">
        <p className="text-center">© 2025 社交工程紀錄後台</p>
      </footer>
    </>
  );
}

export default App;
