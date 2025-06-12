import React, { useEffect, useState } from "react";
// import { Link } from "react-router-dom";


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
  const [statsData, setStatsData] = useState({}); // 存所有統計資料
  const [currentPage, setCurrentPage] = useState(1);
  const [loadingDots, setLoadingDots] = useState(0);
  
  useEffect(() => {
    const controller = new AbortController();
    // 取得 orgs
    const orgs = getCookie("orgs");
    const orgsArr = orgs ? JSON.parse(decodeURIComponent(orgs)) : [];

    setLoading(true);
    fetchData(orgsArr, controller);

    return () => controller.abort();
  }, []);


  // 取得所有統計資料，直接 setStatsData
  const fetchStats = async (uuids) => {
    if (!uuids.length) return;
    // 批次取得所有統計
    const res = await fetch("/api/sendlog_stats/get", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ uuids }),
    });
    const json = await res.json();
    const statsList = json.data || [];
    // 轉成 { uuid: stats, ... }
    const statsObj = {};
    statsList.forEach(stats => {
      statsObj[stats.sendtask_uuid] = stats;
    });
    setStatsData(statsObj);
  };

  const fetchData = async (orgsArr, controller) => {
    try {
      const res = await fetch("/api/sendtasks/get", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ orgs: orgsArr }),
        signal: controller.signal,
      });

      const json = await res.json();
      if (json.status === "success") {
        setTasksData(json.data);

        const uuidsToFetch = json.data.map(task => task.sendtask_uuid);

        if (uuidsToFetch.length === 0) {
          setLoading(false);
          setStatsData({});
          return;
        }

        await fetchStats(uuidsToFetch);
      }
    } catch (error) {
      console.error("取得任務列表失敗", error);
    } finally {
      setLoading(false);
    }
  };



  const fetchCheckTasks = () => {
    setLoading(true);
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
          const controller = new AbortController();
          const orgsRaw = getCookie("orgs");
          const orgsArr = orgsRaw ? JSON.parse(decodeURIComponent(orgsRaw)) : [];
          fetchData(orgsArr, controller);
        } else {
          alert("檢查任務失敗：" + json.message);
        }
      });
  };


  // const [isUpdatingSendlog, setIsUpdatingSendlog] = useState(false);
  // const fetchAllCheckSends = () => {
  //   setIsUpdatingSendlog(true);
  //   fetch("/api/sendlog/refresh", { method: "POST" })
  //     .then(res => res.json())
  //     .then(json => {
  //       if (json.status === "success") {
  //         alert(`${json.message} 已更新！頁面將重新載入`);
  //         window.location.reload(); // 直接重新載入頁面
  //       } else {
  //         alert("更新失敗：" + json.message);
  //         setIsUpdatingSendlog(false);
  //       }
  //     });
  // };    

  const [isCheckingSends, setIsCheckingSends] = useState(false);
  const [updatedTodayUuids, setUpdatedTodayUuids] = useState([]);

  // 更新今日寄送任務的狀態
  const fetchCheckSends = async (uuid = "") => {
    setIsCheckingSends(true);
  
    // 只取今日未寄送最早的 plan_time 非0的任務
    let checkTasks = [];
    if (!uuid) {
      // 如果沒有指定 uuid，則取今日有計劃寄送的任務
      checkTasks = tasksData.filter(row => {
        const stats = statsData[row.sendtask_uuid];
        return stats && stats.today_earliest_plan_time > 0;
      });
      // 如果沒有任務就直接結束
      if (checkTasks.length === 0) {
        alert("今日沒有預計寄送的任務！");
        setIsCheckingSends(false);
        return;
      }
    } else {
      // 如果有指定 uuid，則只更新該任務
      checkTasks = tasksData.filter(row => row.sendtask_uuid === uuid);
    }
    const uuids = checkTasks.map(row => row.sendtask_uuid);

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
            alert("任務已是最新狀態");
          } else {
            alert(`${json.message} 已更新`);
            // 直接批次取得最新統計
            const controller = new AbortController();
            // 取得 orgs
            const orgs = getCookie("orgs");
            const orgsArr = orgs ? JSON.parse(decodeURIComponent(orgs)) : [];
            setLoading(true);
            fetchData(orgsArr, controller);
          }
        } else {
          alert("更新失敗：" + json.message);
        }
      })
      .catch((err) => {
        console.error("發生錯誤", err);
        alert("伺服器錯誤，請稍後再試");
      })
      .finally(() => {
        setIsCheckingSends(false);
      });
  };

  const [showTodayOnly, setShowTodayOnly] = useState(true);
  const showTodayTasks = () => {
    setShowTodayOnly(true);
    setCurrentPage(1);
  };

  const showAllTasks = () => {
    setShowTodayOnly(false);
  };

  // 根據 showTodayOnly 選擇性過濾任務
  // 如果 showTodayOnly 為 true，則只顯示今日有計劃寄送的任務
  const filteredTasks = showTodayOnly
    ? tasksData.filter(row => {
        const stats = statsData[row.sendtask_uuid];
        return stats && stats.today_earliest_plan_time > 0;
      })
    : tasksData;

  // 分頁相關
  const totalPages = Math.ceil(filteredTasks.length / PAGE_SIZE);
  const pagedTasks = filteredTasks.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // 動態「...」效果
  useEffect(() => {
    // if (!isUpdatingSendlog && !isCheckingSends) return;
    if (!isCheckingSends) return;
    const interval = setInterval(() => {
      setLoadingDots(dots => (dots + 1) % 4);
    }, 400);
    return () => clearInterval(interval);
  // }, [isUpdatingSendlog, isCheckingSends]);
  }, [isCheckingSends]);

  const handlePageChange = (page) => {
    if (page >= 1 && page <= totalPages) setCurrentPage(page);
  };

  if (loading) return <p>載入中...</p>;

  return (
    <div>
      <button className="btn btn-primary" onClick={fetchCheckTasks}>更新任務列表</button>
      {!showTodayOnly && <button className="btn btn-primary" onClick={showTodayTasks} >顯示今日寄送任務</button>}
      {showTodayOnly && <button className="btn btn-primary" onClick={showAllTasks} >顯示全部寄送任務</button>}
      <button className="btn btn-primary" onClick={() => fetchCheckSends()} disabled={isCheckingSends}>更新今日任務寄送現況</button>
      {/* <button className="btn btn-primary" onClick={fetchAllCheckSends} disabled={isUpdatingSendlog}>更新全部任務寄送現況(所需時間較久)(製作中)</button>
      {isUpdatingSendlog && (
        <span style={{ marginLeft: "1rem", color: "#007bff" }}>
          全任務更新中{".".repeat(loadingDots)}
        </span>
      )} */}
      {isCheckingSends && (
        <span style={{ marginLeft: "1rem", color: "#007bff" }}>
          任務更新中{".".repeat(loadingDots)}
        </span>
      )}
      <div className="table-responsive">
        <table className="table table-bordered table-striped">
          <thead className="table-light">
            <tr>
              <th>任務名稱</th>
              <th>信件總數量</th>
              <th>已寄出總數</th>
              <th>今日任務開始時間</th>
              <th>今日任務結束時間</th>
              <th>今日尚未寄出</th>
              <th>今日寄出</th>
              <th>今日成功寄出</th>
              <th>最後一封寄出預計時間</th>
              <th>是否暫停</th>
              <th>更新</th>
            </tr>
          </thead>
          <tbody>
            {pagedTasks.map((row, index) => {
                const stats = statsData[row.sendtask_uuid] || { planned: "-", send: "-", success: "-" };
                return (
                  <tr key={index} className={updatedTodayUuids.includes(row.sendtask_uuid) ? "updated-task-row" : ""}>
                    {/* <td><Link to={`/showtasks/${row.sendtask_uuid}`}>{row.sendtask_id}</Link></td> */}
                    <td>{row.sendtask_id}</td>
                    <td>{stats.totalplanned}</td>
                    <td>{stats.totalsend}</td>
                    <td>
                      {stats.today_earliest_plan_time === 0 || stats.today_earliest_plan_time === undefined
                        ? " - "
                        : formatDate(stats.today_earliest_plan_time)}
                    </td>
                    <td>
                      {stats.today_latest_plan_time === 0 || stats.today_latest_plan_time === undefined
                        ? " - "
                        : formatDate(stats.today_latest_plan_time)}
                    </td>
                    <td>{stats.todayunsend}</td>
                    <td>{stats.todaysend}</td>
                    <td>{stats.todaysuccess}</td>
                    <td>
                      {stats.all_latest_plan_time === 0 || stats.all_latest_plan_time === undefined
                        ? " - "
                        : formatDate(stats.all_latest_plan_time)}
                    </td>
                    <td>{row.is_pause ? "是" : "否"}</td>
                    <td>
                      <button 
                        className="btn btn-primary btn-sm"
                        onClick={() => fetchCheckSends(row.sendtask_uuid)}
                        disabled={isCheckingSends}
                      >
                        更新
                      </button>
                    </td>
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
