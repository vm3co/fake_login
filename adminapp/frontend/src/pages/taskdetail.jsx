import { useParams } from "react-router-dom";
import { useEffect, useState } from "react";

const TaskDetail = () => {
  const { uuid } = useParams(); // 取得任務 id
  const [taskDetail, setTaskDetail] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/createsendlogdata/${uuid}`)
      .then((res) => res.json())
      .then((json) => {
        if (json.status === "success") {
          setTaskDetail(json.data);
        }
        setLoading(false);
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
            <th>target_email</th>
            <th>access</th>
            <th>person_info</th>
          </tr>
        </thead>
        <tbody>
          {taskDetail.map((row, index) => (
            <tr key={index}>
              <td>{row.uuid}</td>
              <td>{row.target_email}</td>
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
              <td>{row.person_info}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
};

export default TaskDetail;
