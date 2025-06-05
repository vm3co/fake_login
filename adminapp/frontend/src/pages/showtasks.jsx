import React, { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";


// 統計計算函式
function calcStats(stats) {
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayEnd = new Date(todayStart);
  todayEnd.setDate(todayEnd.getDate() + 1);
  const startTS = Math.floor(todayStart.getTime() / 1000);
  const endTS = Math.floor(todayEnd.getTime() / 1000);

  const todayPlans = stats.filter(t => t.plan_time >= startTS && t.plan_time < endTS);
  const todaySends = stats.filter(t => t.send_time >= startTS && t.send_time < endTS && t.send_time !== 0);
  const todaySuccess = todaySends.filter(t => t.send_res?.startsWith("True"));
  const totalSends = stats.filter(t => t.send_time !== 0);

  return {
    totalplanned: stats.length,
    todayplanned: todayPlans.length,
    todaysent: todaySends.length,
    todaysuccess: todaySuccess.length,
    totalsent: totalSends.length
  };
}

// 格式化時間戳記
function formatDate(ts) {
  if (!ts) return "";
  // 若是字串，先轉成數字
  const t = typeof ts === "string" ? parseInt(ts, 10) : ts;
  // 判斷是否為秒級（10位數）或毫秒級（13位數）
  const date = t > 1e12 ? new Date(t) : new Date(t * 1000);
  return date.toLocaleString();
}

// 複製 getCookie 函式
function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return null;
}

const PAGE_SIZE = 10; // 每頁顯示幾筆

const ShowTasks = () => {
  const [loading, setLoading] = useState(true);
  const [tasksData, setTasksData] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [loadingDots, setLoadingDots] = useState(0);


  // 新增一個快取 statsCache 
  const statsCache = useRef({});

  // 讀取 sessionStorage 快取
  useEffect(() => {
    const cacheStr = sessionStorage.getItem("statsCache");
    if (cacheStr) {
      try {
        statsCache.current = JSON.parse(cacheStr);
      } catch { /* empty */ }
    }
  }, []);

  // 每次 statsCache 有更新就寫入 sessionStorage
  const updateStatsCache = (uuid, stats) => {
    statsCache.current[uuid] = stats;
    sessionStorage.setItem("statsCache", JSON.stringify(statsCache.current));
    console.log("寫入 sessionStorage statsCache", statsCache.current); // ← 加這行

  };

  // 取得 orgs
  const orgs = getCookie("orgs");

  useEffect(() => {
    setLoading(true);
    const orgsArr = orgs ? JSON.parse(decodeURIComponent(orgs)) : [];
    fetch("/api/sendtasks/get", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ orgs: orgsArr }),
    })
      .then((res) => res.json())
      .then((json) => {
        if (json.status === "success") {
          setTasksData(json.data);

          // 只 fetch 沒有快取過的 uuid
          const uuidsToFetch = json.data
            .map(task => task.sendtask_uuid)
            .filter(uuid => !statsCache.current[uuid]);

          // 如果沒有需要 fetch 的 uuid，就直接結束
          if (uuidsToFetch.length === 0) {
            setLoading(false);
            return;
          }

          const fetchStats = uuidsToFetch.map(uuid =>
            fetch(`/api/sendlog/get/${uuid}`)
              .then(res => res.json())
              .then(stats => {
                updateStatsCache(uuid, calcStats(stats.data || []));
                })
          );

          Promise.all(fetchStats).then(() => {
            setLoading(false);
          });
        }
      });
  }, [orgs]);

  const fetchCheckTasks = () => {
    setLoading(true);
    const orgsArr = orgs ? JSON.parse(decodeURIComponent(orgs)) : [];
    // 先檢查新增或移除的任務
    fetch("/api/sendtasks/check")
      .then((res) => res.json())
      .then((json) => {
        if (json.status === "success") {
          const { added, removed } = json.data;
          // 取出 sendtask_id 並格式化成多行文字
          const addedIds = added.map(item => `- ${item.sendtask_id}`).join("\n");
          const removedIds = removed.map(item => `- ${item.sendtask_id}`).join("\n");
          const message = 
            `新增 ${added.length} 筆：\n${addedIds || "(無)"}\n\n` +
            `移除 ${removed.length} 筆：\n${removedIds || "(無)"}`;
          alert(message);
          // 再次取得最新任務資料
          fetch("/api/sendtasks/get", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ orgs: orgsArr }),
          })
            .then((res) => res.json())
            .then((json) => {
              if (json.status === "success") {
                setTasksData(json.data);
                
                // 只 fetch 沒有快取過的 uuid
                const uuidsToFetch = json.data
                  .map(task => task.sendtask_uuid)
                  .filter(uuid => !statsCache.current[uuid]);

                if (uuidsToFetch.length === 0) {
                  setLoading(false);
                  return;
                }

                const fetchStats = uuidsToFetch.map(uuid =>
                  fetch(`/api/sendlog/get/${uuid}`)
                    .then(res => res.json())
                    .then(stats => {
                      updateStatsCache(uuid, calcStats(stats.data || []));
                    })
                );

                Promise.all(fetchStats).then(() => {
                  setLoading(false);
                });
              }
          });
        }
      });
  };


  const [isUpdatingSendlog, setIsUpdatingSendlog] = useState(false);
  const fetchCheckSends = () => {
    setIsUpdatingSendlog(true);
    fetch("/api/sendlog/refresh", { method: "POST" })
      .then(res => res.json())
      .then(json => {
        if (json.status === "success") {
          alert(`${json.message} 已更新！頁面將重新載入`);
          localStorage.removeItem("statsCache");
          window.location.reload(); // 直接重新載入頁面
        } else {
          alert("更新失敗：" + json.message);
          setIsUpdatingSendlog(false);
        }
      });
  };    

  const [isUpdatingTodaySendlog, setIsUpdatingTodaySendlog] = useState(false);
  const [updatedTodayUuids, setUpdatedTodayUuids] = useState([]);

  // 更新今日寄送任務的狀態
  const fetchCheckTodaySends = async () => {
    setIsUpdatingTodaySendlog(true);
  
    // 只取今日預計非0的任務
    const todayTasks = tasksData.filter(row => {
      const stats = statsCache.current[row.sendtask_uuid];
      return stats && stats.todayplanned > 0;
    });
  
    // 如果沒有任務就直接結束
    if (todayTasks.length === 0) {
      alert("今日沒有預計寄送的任務！");
      setIsUpdatingTodaySendlog(false);
      return;
    }
  
    // 假設後端支援批次傳送 uuids
    const uuids = todayTasks.map(row => row.sendtask_uuid);
  
    fetch("/api/sendlog/refresh/today", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uuids }),
    })
      .then(res => res.json())
      .then(json => {
        if (json.status === "success") {
          
          const uuidsToFetch = json.updated || [];
          setUpdatedTodayUuids(uuidsToFetch);
          if (uuidsToFetch.length === 0) {
            alert("今日寄送任務已是最新狀態");
            setIsUpdatingTodaySendlog(false);
            return;
          }

          const fetchStats = uuidsToFetch.map(uuid =>
            fetch(`/api/sendlog/get/${uuid}`)
              .then(res => res.json())
              .then(stats => {
                updateStatsCache(uuid, calcStats(stats.data || []));
              })
          );

          Promise.all(fetchStats).then(() => {
            setLoading(false);
          });

          alert(`${json.message} 已更新`);
        } else {
          alert("更新失敗：" + json.message);
          setIsUpdatingTodaySendlog(false);
        }
      });
  };

  const [showTodayOnly, setShowTodayOnly] = useState(false);
  const showTodayTasks = () => {
    setShowTodayOnly(true);
  };

  const showAllTasks = () => {
    setShowTodayOnly(false);
  };

  // 根據 showTodayOnly 選擇性過濾任務
  // 如果 showTodayOnly 為 true，則只顯示今日有計劃寄送的任務
  const filteredTasks = showTodayOnly
    ? tasksData.filter(row => {
        const stats = statsCache.current[row.sendtask_uuid];
        return stats && stats.todayplanned > 0;
      })
    : tasksData;

  // 分頁相關
  const totalPages = Math.ceil(filteredTasks.length / PAGE_SIZE);
  const pagedTasks = filteredTasks.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // 動態「...」效果
  useEffect(() => {
    if (!isUpdatingSendlog && !isUpdatingTodaySendlog) return;
    const interval = setInterval(() => {
      setLoadingDots(dots => (dots + 1) % 4);
    }, 400);
    return () => clearInterval(interval);
  }, [isUpdatingSendlog, isUpdatingTodaySendlog]);

  const handlePageChange = (page) => {
    if (page >= 1 && page <= totalPages) setCurrentPage(page);
  };

  if (loading) return <p>載入中...</p>;

  return (
    <div>
      <button className="btn btn-primary" onClick={fetchCheckTasks}>更新任務列表</button>
      {!showTodayOnly && <button className="btn btn-primary" onClick={showTodayTasks} >顯示今日寄送任務</button>}
      {showTodayOnly && <button className="btn btn-primary" onClick={showAllTasks} >顯示全部寄送任務</button>}
      <button className="btn btn-primary" onClick={fetchCheckTodaySends} disabled={isUpdatingTodaySendlog}>更新今日任務寄送現況</button>
      {/* <button className="btn btn-primary" onClick={fetchCheckSends} disabled={isUpdatingSendlog}>更新全部任務寄送現況(所需時間較久)(製作中)</button> */}
      <button className="btn btn-primary" onClick={fetchCheckSends} disabled={true}>更新全部任務寄送現況(所需時間較久)(製作中)</button>
      {isUpdatingSendlog && (
        <span style={{ marginLeft: "1rem", color: "#007bff" }}>
          全任務更新中{".".repeat(loadingDots)}
        </span>
      )}
      {isUpdatingTodaySendlog && (
        <span style={{ marginLeft: "1rem", color: "#007bff" }}>
          今日任務更新中{".".repeat(loadingDots)}
        </span>
      )}
      <div className="table-responsive">
        <table className="table table-bordered table-striped">
          <thead className="table-light">
            <tr>
              <th>任務名稱</th>
              <th>建立時間</th>
              <th>總數量</th>
              <th>今日預計</th>
              <th>今日寄出</th>
              <th>今日成功寄出</th>
              <th>實際寄出</th>
            </tr>
          </thead>
          <tbody>
            {pagedTasks.map((row, index) => {
                const stats = statsCache.current[row.sendtask_uuid] || { planned: "-", sent: "-", success: "-" };
                return (
                  <tr key={index} style={updatedTodayUuids.includes(row.sendtask_uuid) ? { background: "#ffeeba" } : {}}>
                    {/* <td><Link to={`/showtasks/${row.sendtask_uuid}`}>{row.sendtask_id}</Link></td> */}
                    <td>{row.sendtask_id}</td>
                    <td>{formatDate(row.sendtask_create_ut)}</td>
                    <td>{stats.totalplanned}</td>
                    <td>{stats.todayplanned}</td>
                    <td>{stats.todaysent}</td>
                    <td>{stats.todaysuccess}</td>
                    <td>{stats.totalsent}</td>
                  </tr>
                );
            })}
          </tbody>
        </table>
      </div>
      {/* 分頁按鈕 */}
      <nav className="mt-3">
        <ul 
          className="pagination justify-content-center"
          style={{ flexWrap: "wrap" }}
        >
          <li className={`page-item${currentPage === 1 ? " disabled" : ""}`}>
            <button className="page-link" onClick={() => handlePageChange(currentPage - 1)}>上一頁</button>
          </li>
          {[...Array(totalPages)].map((_, i) => (
            <li key={i} className={`page-item${currentPage === i + 1 ? " active" : ""}`}>
              <button className="page-link" onClick={() => handlePageChange(i + 1)}>{i + 1}</button>
            </li>
          ))}
          <li className={`page-item${currentPage === totalPages ? " disabled" : ""}`}>
            <button className="page-link" onClick={() => handlePageChange(currentPage + 1)}>下一頁</button>
          </li>
        </ul>
      </nav>
    </div>
  );
};

export default ShowTasks;
