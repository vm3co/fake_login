import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const ShowTasks = () => {
  const [tasksData, setTasksData] = useState([]);
  useEffect(() => {
    fetch("/api/gettasks")
      .then((res) => res.json())
      .then((json) => {
        if (json.status === "success") {
          setTasksData(json.data);
        }
      });
  }, []);

  const fetchCheckTasks = () => {
    fetch("/api/checktasks")
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
          fetch("/api/gettasks")
            .then((res) => res.json())
            .then((json) => {
              if (json.status === "success") {
                setTasksData(json.data);
            }
          });
        }
      });
  };

  return (
    <div>
      <button className="btn btn-primary" onClick={fetchCheckTasks}>更新任務列表</button>
      <div className="table-responsive">
        <table className="table table-bordered table-striped">
          <thead className="table-light">
            <tr>
              <th>uuid</th>
              <th>任務名稱</th>
              <th>建立時間</th>
            </tr>
          </thead>
          <tbody>
            {tasksData.map((row, index) => (
              <tr key={index}>
                <td>{row.sendtask_uuid}</td>
                <td><Link to={`/showtasks/${row.sendtask_uuid}`}>{row.sendtask_id}</Link></td>
                <td>{row.sendtask_create_ut}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ShowTasks;
