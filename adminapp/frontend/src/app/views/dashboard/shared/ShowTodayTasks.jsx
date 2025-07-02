import { useEffect, useState, useContext } from "react";
import {
  Box,
  // Icon,
  Table,
  styled,
  TableRow,
  TableBody,
  TableCell,
  TableHead,
  // IconButton,
  TablePagination,
} from "@mui/material";
import SimpleCard from "app/components/SimpleCard";
// import { H3 } from "app/components/Typography";
import Button from "@mui/material/Button";
// import TableContainer from "@mui/material/TableContainer";
// import Paper from "@mui/material/Paper";
// import Pagination from "@mui/material/Pagination";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";
// import Switch from "@mui/material/Switch";

import { SendtaskListContext } from "app/contexts/SendtaskListContext";
import formatDate from "app/utils/formatDate";
import { useCheckSends } from "app/hooks/useCheckSends";



// STYLED COMPONENT
const StyledTable = styled(Table)(() => ({
  whiteSpace: "pre",
  "& thead": {
    "& tr": { "& th": { paddingLeft: 0, paddingRight: 0 } }
  },
  "& tbody": {
    "& tr": { "& td": { paddingLeft: 0, textTransform: "capitalize" } }
  }
}));


export default function ShowTodayTasks({ taskState, setTaskState }) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const { loading, statsData, todayTasks, refresh } = useContext(SendtaskListContext);
  const [loadingDots, setLoadingDots] = useState(0);
  const [isCheckingSends, setIsCheckingSends] = useState(false);
  const [updatedTodayUuids, setUpdatedTodayUuids] = useState([]);
  const { fetchCheckSends } = useCheckSends({ refresh, setIsCheckingSends, setUpdatedTodayUuids });
  const [searchText, setSearchText] = useState("");  // 搜尋任務名稱
  const [showExpiredOnly, setShowExpiredOnly] = useState(false);  // 是否只顯示已過期的任務
  const [selectedUuids, setSelectedUuids] = useState([]);  // 勾選任務並只更新這些任務

  // 加入調試代碼
  console.log("ShowTodayTasks - loading:", loading);
  console.log("ShowTodayTasks - todayTasks:", todayTasks);
  console.log("ShowTodayTasks - todayTasks.length:", todayTasks?.length);
  console.log("ShowTodayTasks - statsData:", statsData);
  console.log("ShowTodayTasks - Object.keys(statsData).length:", Object.keys(statsData || {}).length);
  
  // 任務顯示模式
  const now = Date.now();
  const filteredTasks = (todayTasks)
    ?.filter(row => {
      // 搜尋任務名稱
      if (searchText && !row.sendtask_id?.toLowerCase().includes(searchText.toLowerCase())) {
        return false;
      }
      // 過濾已過期
      if (showExpiredOnly) {
        const stats = statsData[row.sendtask_uuid] || {};
        const lastPlan = stats.all_latest_plan_time
          ? (String(stats.all_latest_plan_time).length > 10
            ? stats.all_latest_plan_time
            : stats.all_latest_plan_time * 1000)
          : 0;
        if (!lastPlan || lastPlan > now) return false;
      }

      // 如果選擇"今日全部任務"，直接返回 true（不再進行狀態過濾）
      if (taskState === "all") {
        return true;
      }

      const stats = statsData[row.sendtask_uuid] || {};
      const todayunsend = Number(stats.todayunsend) || 0;
      const todaysuccess = Number(stats.todaysuccess) || 0;
      const todaysend = Number(stats.todaysend) || 0;
      const todayfailed = todaysend - todaysuccess;

      if (taskState === "doing") {
        // 執行中：今日尚未寄出>0 且 今日成功寄出>0 且 今日寄出失敗為0
        return todayunsend > 0 && todaysuccess > 0 && todayfailed === 0;
      }
      if (taskState === "notyet") {
        // 尚未開始：今日尚未寄出>0 且 今日成功寄出=0 且 今日寄出失敗=0
        return todayunsend > 0 && todaysuccess === 0 && todayfailed === 0;
      }
      if (taskState === "done") {
        // 已完成：今日尚未寄出=0 且 今日寄出失敗=0
        return todayunsend === 0 && todayfailed === 0;
      }
      if (taskState === "warning") {
        // 異常：今日寄出失敗非0
        return todayfailed !== 0;
      }
      return true;
    }) || [];

  const pagedTasks = Array.isArray(filteredTasks)
    ? filteredTasks.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
    : [];

  // 動態「...」效果
  useEffect(() => {
    if (!isCheckingSends) return;
    const interval = setInterval(() => {
      setLoadingDots(dots => (dots + 1) % 4);
    }, 400);
    return () => clearInterval(interval);
  }, [isCheckingSends]);

  const handleChangePage = (_, newPage) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event) => {
    setRowsPerPage(+event.target.value);
    setPage(0);
  };

  if (loading)
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minHeight="300px">
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>載入中...</Typography>
      </Box>
    );

  return (
    <Box width="100%" overflow="auto">
      <SimpleCard>
        <Stack direction="row" spacing={2} mb={2}>
          <Button
            variant="contained"
            color="secondary"
            onClick={() => {
              const uuids = todayTasks.map(row => row.sendtask_uuid);
              if (uuids.length === 0) {
                alert("無今日任務可更新");
                return;
              }
              fetchCheckSends(uuids);
            }}
            disabled={isCheckingSends}
          >
            更新今日任務寄送現況
          </Button>
          <Button
            variant="contained"
            color="primary"
            disabled={selectedUuids.length === 0}
            onClick={() => fetchCheckSends(selectedUuids)}
          >
            更新勾選任務
          </Button>
          {isCheckingSends && (
            <Typography color="primary" sx={{ ml: 2 }}>
              任務更新中{".".repeat(loadingDots)}
            </Typography>
          )}
        </Stack>
        <Stack direction="row" spacing={2} mb={2} alignItems="center">
          <TextField
            size="small"
            label="搜尋任務名稱"
            value={searchText}
            onChange={e => {
              setSearchText(e.target.value);
              setPage(0);
            }}
            sx={{ width: 200 }}
          />
          <FormControlLabel
            control={
              <Checkbox
                checked={showExpiredOnly}
                onChange={e => {
                  setShowExpiredOnly(e.target.checked);
                  setPage(0);
                }}
              />
            }
            label="只顯示已過最後預計寄出日的任務"
          />
          <Select
            size="small"
            value={taskState}
            onChange={e => {
              setTaskState(e.target.value);
              setPage(0);
            }}
              sx={{ width: 80, minWidth: '120px' }}
            defaultValue="all"
          >
            <MenuItem value="all">今日任務</MenuItem>
            <MenuItem value="doing">執行中</MenuItem>
            <MenuItem value="notyet">尚未開始</MenuItem>
            <MenuItem value="done">已完成</MenuItem>
            <MenuItem value="warning">異常</MenuItem>
          </Select>
        </Stack>
        <StyledTable>
          <TableHead>
            <TableRow>
              <TableCell align="left">
                <Checkbox
                  checked={pagedTasks.length > 0 && pagedTasks.every(row => selectedUuids.includes(row.sendtask_uuid))}
                  indeterminate={pagedTasks.some(row => selectedUuids.includes(row.sendtask_uuid)) && !pagedTasks.every(row => selectedUuids.includes(row.sendtask_uuid))}
                  onChange={e => {
                    if (e.target.checked) {
                      setSelectedUuids([
                        ...new Set([...selectedUuids, ...pagedTasks.map(row => row.sendtask_uuid)])
                      ]);
                    } else {
                      setSelectedUuids(selectedUuids.filter(uuid => !pagedTasks.map(row => row.sendtask_uuid).includes(uuid)));
                    }
                  }}
                />
              </TableCell>
              <TableCell align="center">任務名稱</TableCell>
              <TableCell align="center">信件總數量</TableCell>
              <TableCell align="center">已寄出總數</TableCell>
              <TableCell align="center">預計開始</TableCell>
              <TableCell align="center">預計結束</TableCell>
              <TableCell align="center">今日尚未寄出</TableCell>
              <TableCell align="center">今日成功</TableCell>
              <TableCell align="center">今日失敗</TableCell>
              <TableCell align="center">最後一封預計日期</TableCell>
              <TableCell align="center">是否暫停</TableCell>
              <TableCell align="center">更新</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {pagedTasks.map((row, index) => {
              const stats = statsData[row.sendtask_uuid] || { planned: "-", send: "-", success: "-" };
              return (
                <TableRow
                  key={index}
                  sx={{
                    backgroundColor: updatedTodayUuids.includes(row.sendtask_uuid)
                      ? "rgba(25, 118, 210, 0.08)"
                      : "inherit",
                  }}
                >
                  <TableCell align="left">
                    <Checkbox
                      checked={selectedUuids.includes(row.sendtask_uuid)}
                      onChange={e => {
                        if (e.target.checked) {
                          setSelectedUuids([...selectedUuids, row.sendtask_uuid]);
                        } else {
                          setSelectedUuids(selectedUuids.filter(uuid => uuid !== row.sendtask_uuid));
                        }
                      }}
                    />
                  </TableCell>

                  <TableCell align="center">{row.sendtask_id}</TableCell>
                  <TableCell align="center">{stats.totalplanned}</TableCell>
                  <TableCell align="center">{stats.totalsend}</TableCell>
                  <TableCell align="center">
                    {stats.today_earliest_plan_time === 0 || stats.today_earliest_plan_time === undefined
                      ? " - "
                      : formatDate(stats.today_earliest_plan_time, "time")}
                  </TableCell>
                  <TableCell align="center">
                    {stats.today_latest_plan_time === 0 || stats.today_latest_plan_time === undefined
                      ? " - "
                      : formatDate(stats.today_latest_plan_time, "time")}
                  </TableCell>
                  <TableCell align="center">{stats.todayunsend}</TableCell>
                  <TableCell align="center">{stats.todaysuccess}</TableCell>
                  <TableCell align="center">{stats.todaysend - stats.todaysuccess}</TableCell>
                  <TableCell align="center">
                    {stats.all_latest_plan_time === 0 || stats.all_latest_plan_time === undefined
                      ? " - "
                      : formatDate(stats.all_latest_plan_time, "date")}
                  </TableCell>
                  <TableCell align="center">
                    {row.is_pause ? (
                      <Chip label="是" color="warning" size="small" />
                    ) : (
                      <Chip label="否" color="success" size="small" />
                    )}
                  </TableCell>
                  <TableCell align="center">
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => fetchCheckSends([row.sendtask_uuid])}
                      disabled={isCheckingSends}
                    >
                      更新
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </StyledTable>
      </SimpleCard>

      <TablePagination
        sx={{ px: 2 }}
        page={page}
        component="div"
        rowsPerPage={rowsPerPage}
        count={filteredTasks.length}
        onPageChange={handleChangePage}
        rowsPerPageOptions={[5, 10, 25, 50, 100]}
        onRowsPerPageChange={handleChangeRowsPerPage}
      // nextIconButtonProps={{ "aria-label": "Next Page" }}
      // backIconButtonProps={{ "aria-label": "Previous Page" }}
      />
    </Box>
  );
}
