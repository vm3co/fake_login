import { useEffect, useState, useContext } from "react";
import {
  Box,
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
import TableContainer from "@mui/material/TableContainer";
import Paper from "@mui/material/Paper";
// import Pagination from "@mui/material/Pagination";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import Select from "@mui/material/Select";
import MenuItem from "@mui/material/MenuItem";
import TextField from "@mui/material/TextField";
import Checkbox from "@mui/material/Checkbox";
// import Switch from "@mui/material/Switch";

import { SendtaskListContext } from "app/contexts/SendtaskListContext";
import formatDate from "app/utils/formatDate";
import { useCheckSends } from "app/hooks/useCheckSends";



// STYLED COMPONENT
const StyledTable = styled(Table)(() => ({
  whiteSpace: "normal",
  "& thead": {
    "& tr": { 
      "& th": { 
        textAlign: "center", // align="center"
        whiteSpace: "normal", // sx={{ whiteSpace: 'normal' }}
        lineHeight: 1.2, // sx={{ lineHeight: 1.2 }}
        borderRight: "1px solid #e0e0e0", // 垂直框線
        cursor: "pointer", // 滑鼠移到欄位上顯示可按的形狀
        "&:hover": {
          backgroundColor: "#f1f1f1", // 提示使用者可以點擊
        },
        "&:last-child": {
          borderRight: "none", // 最後一欄不需要右邊框線
        },
        // 特定欄位寬度設定
        "&:nth-of-type(1)": { width: "60px" }, // 勾選框
        "&:nth-of-type(2)": { width: "140px" }, // 任務名稱
        "&:nth-of-type(3)": { width: "60px" }, // 信件總數量
        "&:nth-of-type(4)": { width: "60px" }, // 已寄出總數
        "&:nth-of-type(5)": { width: "70px" }, // 預計開始
        "&:nth-of-type(6)": { width: "70px" }, // 預計結束
        "&:nth-of-type(7)": { width: "60px" }, // 今日尚未寄出
        "&:nth-of-type(8)": { width: "60px" }, // 今日成功
        "&:nth-of-type(9)": { width: "60px" }, // 今日失敗
        "&:nth-of-type(10)": { width: "80px" }, // 第一封寄出預計日期
        "&:nth-of-type(11)": { width: "80px" }, // 最後一封寄出預計日期
        "&:nth-of-type(12)": { width: "40px" }, // 是否暫停
        "&:nth-of-type(13)": { width: "50px" }, // 更新
      } 
    }
  },
  "& tbody": {
    "& tr": { 
      "& td": { 
        textAlign: "center",
        whiteSpace: "normal",
        lineHeight: 1.2,
        wordBreak: "keep-all", // 保持單詞完整，不斷字
        overflowWrap: "break-word", // 當單詞太長時才斷字
        borderRight: "1px solid #e0e0e0",
        "&:last-child": {
          borderRight: "none",
        },
        // 今日相關數據欄位樣式
        "&:nth-of-type(7)": { // 今日尚未寄出
          fontWeight: "bold",
          color: "#FF6A00" // 橘色
        },
        "&:nth-of-type(8)": { // 今日成功
          fontWeight: "bold",
          color: "#4caf50" // 綠色
        },
        "&:nth-of-type(9)": { // 今日失敗
          fontWeight: "bold",
          color: "#f44336" // 紅色
        }
      } 
    } 
  }
}));


export default function ShowTodayTasks({ taskState, setTaskState }) {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);
  const [sortBy, setSortBy] = useState("today_earliest_plan_time");  // 預設排序順序為寄信開始時間
  const [sortOrder, setSortOrder] = useState("asc"); // 排序方向：asc 或 desc
  const { 
    loading, 
    statsData, 
    todayTasks, 
    refresh, 
    isCheckingSends, 
    setIsCheckingSends 
  } = useContext(SendtaskListContext);
  const [loadingDots, setLoadingDots] = useState(0);
  const [updatedTodayUuids, setUpdatedTodayUuids] = useState([]);
  const { fetchCheckSends } = useCheckSends({ refresh, setIsCheckingSends, setUpdatedTodayUuids });
  const [searchText, setSearchText] = useState("");  // 搜尋任務名稱
  const [selectedUuids, setSelectedUuids] = useState([]);  // 勾選任務並只更新這些任務

  // 排序邏輯
  const sortedTasks = [...(todayTasks || [])].sort((a, b) => {
    if (!sortBy) return 0; // 如果未指定排序欄位，保持原順序
    let valueA, valueB;
    if (sortBy === "is_pause") {
      valueA = a[sortBy];
      valueB = b[sortBy];
    } else if (sortBy === "sendtask_id") {
      valueA = a[sortBy]?.toLowerCase();
      valueB = b[sortBy]?.toLowerCase();
    } else {
      valueA = statsData[a.sendtask_uuid]?.[sortBy];
      valueB = statsData[b.sendtask_uuid]?.[sortBy];
    }
    if (valueA < valueB) return sortOrder === "asc" ? -1 : 1;
    if (valueA > valueB) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });
  
  // 任務顯示模式
  const filteredTasks = sortedTasks.filter(row => {
      // 搜尋任務名稱
      if (searchText && !row.sendtask_id?.toLowerCase().includes(searchText.toLowerCase())) {
        return false;
      }

      // 如果選擇"今日全部任務"，直接返回 true（不再進行狀態過濾）
      if (taskState === "all") {
        return true;
      }

      const stats = statsData[row.sendtask_uuid] || {};
      const todayunsend = Number(stats.todayunsend) || 0;
      const todaysuccess = Number(stats.todaysuccess) || 0;
      const todayfailed = Number(stats.todayfailed) || 0;;

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

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc"); // 切換排序方向
    } else {
      setSortBy(column);
      setSortOrder("asc"); // 默認升序
    }
  };

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
    <Box width="100%" overflow="hidden">
      <SimpleCard sx={{ padding: 1 }}>
        <Stack direction="row" spacing={2} mb={2} sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Button
            variant="contained"
            color="primary"
            disabled={selectedUuids.length === 0 || isCheckingSends}
            onClick={() => {
              fetchCheckSends(selectedUuids);
            }}
            size="small"
          >
            更新勾選任務
          </Button>
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
            size="small"
          >
            更新今日任務寄送現況
          </Button>
          {isCheckingSends && (
            <Typography color="primary" sx={{ ml: 2, fontSize: '0.875rem' }}>
              任務更新中{".".repeat(loadingDots)}
            </Typography>
          )}
        </Stack>
        <Stack 
          direction="row" 
          spacing={2} 
          mb={2} 
          alignItems="center"
          sx={{ 
            flexWrap: 'wrap', 
            gap: 1,
            '@media (max-width: 768px)': {
              flexDirection: 'column',
              alignItems: 'stretch'
            }
          }}
        >
          <TextField
            size="small"
            label="搜尋任務名稱"
            value={searchText}
            onChange={e => {
              setSearchText(e.target.value);
              setPage(0);
            }}
            sx={{ 
              width: 200,
              '@media (max-width: 768px)': {
                width: '100%'
              }
            }}
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
          {selectedUuids.length > 0 &&
            <Button 
              onClick={() => {
                setSelectedUuids([]);
              }}
              variant="text"
              size="small"
              sx={{ 
                textTransform: 'none',
                minWidth: 'unset',
                padding: '0 4px',
                verticalAlign: 'baseline'
              }}
            >
              清除所有選取任務
            </Button>
          }
        </Stack>
        <TableContainer 
          component={Paper} 
          sx={{ 
            overflow: 'auto',
            maxHeight: '70vh', // 限制最大高度
            '&::-webkit-scrollbar': {
              width: '8px',
              height: '8px',
            },
            '&::-webkit-scrollbar-track': {
              backgroundColor: '#f1f1f1',
            },
            '&::-webkit-scrollbar-thumb': {
              backgroundColor: '#888',
              borderRadius: '4px',
            },
            '&::-webkit-scrollbar-thumb:hover': {
              backgroundColor: '#555',
            },
          }}
        >
          <StyledTable>
            <TableHead>
              <TableRow>
                <TableCell align="center">
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
                <TableCell align="center" onClick={() => handleSort("sendtask_id")}>
                  任務名稱 {sortBy === "sendtask_id" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("totalplanned")}>
                  信件<br />總數量 {sortBy === "totalplanned" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("totalsend")}>
                  已寄出<br />總數 {sortBy === "totalsend" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("today_earliest_plan_time")}>
                  預計開始 {sortBy === "today_earliest_plan_time" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("today_latest_plan_time")}>
                  預計結束 {sortBy === "today_latest_plan_time" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("todayunsend")}>
                  今日<br />尚未寄出 {sortBy === "todayunsend" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("todaysuccess")}>
                  今日成功 {sortBy === "todaysuccess" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("todayfailed")}>
                  今日失敗 {sortBy === "todayfailed" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("all_earliest_plan_time")}>
                  第一封寄出<br />預計日期 {sortBy === "all_earliest_plan_time" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("all_latest_plan_time")}>
                  最後一封寄出<br />預計日期 {sortBy === "all_latest_plan_time" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell align="center" onClick={() => handleSort("is_paused")}>
                  是否<br />暫停 {sortBy === "is_paused" && (sortOrder === "asc" ? "▲" : "▼")}
                </TableCell>
                <TableCell>
                  更新
                </TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pagedTasks.map((row, index) => {
                const stats = statsData[row.sendtask_uuid] || { planned: "-", send: "-", success: "-" };
                // const todayfailed = 
                const rowNumber = page * rowsPerPage + index + 1; // 全域編號
                return (
                  <TableRow
                    key={index}
                    sx={{
                      backgroundColor: updatedTodayUuids.includes(row.sendtask_uuid)
                        ? "rgba(170, 210, 25, 0.18)" // 更新後的高亮色
                        : index % 2 === 0
                        ? "rgba(25, 118, 210, 0.14)" // 偶數行背景色
                        : "transparent",
                      "&:hover": {
                        backgroundColor: updatedTodayUuids.includes(row.sendtask_uuid)
                          ? "rgba(107, 133, 16, 0.38)" // 更新後的懸停色
                          : "rgba(0, 0, 0, 0.24)", // 一般懸停色
                      },
                    }}
                  >
                    <TableCell align="center">
                      <Checkbox
                        checked={selectedUuids.includes(row.sendtask_uuid)}
                        onChange={e => {
                          if (e.target.checked) {
                            setSelectedUuids([...selectedUuids, row.sendtask_uuid]);
                          } else {
                            setSelectedUuids(selectedUuids.filter(uuid => uuid !== row.sendtask_uuid));
                          }
                        }}
                      /><strong>{rowNumber}</strong>
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
                    <TableCell align="center">{stats.todayfailed}</TableCell>
                    <TableCell align="center">
                      {stats.all_earliest_plan_time === 0 || stats.all_earliest_plan_time === undefined
                        ? " - "
                        : formatDate(stats.all_earliest_plan_time, "date")}
                    </TableCell>
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
                        sx={{
                          minWidth: 'auto',
                          padding: '4px 8px'
                        }}
                      >
                        更新
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </StyledTable>
        </TableContainer>
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
      />
    </Box>
  );
}
