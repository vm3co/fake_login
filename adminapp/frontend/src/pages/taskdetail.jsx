import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";

const TaskDetail = () => {
  const { uuid } = useParams(); // 取得任務 id
  const [taskDetail, setTaskDetail] = useState([]);
  const [loading, setLoading] = useState(true);
  const [templateMap, setTemplateMap] = useState({});

  useEffect(() => {
    setLoading(true);
  Promise.all([
    fetch("/api/mtmpl/get").then(res => res.json()),
    fetch(`/api/sendlog/get/${uuid}`).then(res => res.json())
  ])
    .then(([mtmplRes, sendlogRes]) => {
      // 郵件主旨對應處理
      if (mtmplRes.status === "success") {
        const map = {};
        mtmplRes.data.forEach(t => {
          map[t.mtmpl_uuid] = t.mtmpl_title;
        });
        setTemplateMap(map);
      }

      // 任務詳細資料處理
      if (sendlogRes.status === "success") {
        setTaskDetail(sendlogRes.data);
      }
    })
    .finally(() => {
      setLoading(false);  // ← 不論成功或失敗都關掉 loading
    });
}, [uuid]);

  if (loading) return <p>載入中...</p>;

  return (
    <div>
      <h4>任務內容：{uuid}</h4>
      <table className="table table-bordered">
        <thead>
          <tr>
            <th>uuid</th>
            <th>郵件位址</th>
            <th>人員資訊</th>
            <th>郵件主旨</th>
            <th>觸發現況</th>
          </tr>
        </thead>
        <tbody>
          {taskDetail.map((row, index) => (
            <tr key={index}>
              <td>{row.uuid}</td>
              <td>{row.target_email}</td>
              <td>{row.person_info}</td>
              <td>{templateMap[row.template_uuid]}</td>
              <td>
                <table className="table table-sm m-0">
                  <thead>
                    <tr>
                      <th>Active</th>
                      <th>IP</th>
                      <th>Time</th>
                    </tr>
                  </thead>
                  <tbody>
                    {row.access_active?.map((_, i) => (
                      <tr key={i}>
                        <td>{row.access_active[i]}</td>
                        <td>{row.access_ip[i]}</td>
                        <td>{row.access_time[i]}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default TaskDetail;
