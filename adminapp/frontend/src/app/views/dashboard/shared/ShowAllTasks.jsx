import { useEffect, useState, useContext } from "react";
import {
  Box,
  Table,
  styled,
  TableRow,
  TableBody,
  TableCell,
  TableHead,
  TablePagination,
} from "@mui/material";
import SimpleCard from "app/components/SimpleCard";
import Button from "@mui/material/Button";
import TableContainer from "@mui/material/TableContainer";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import TextField from "@mui/material/TextField";
import Checkbox from "@mui/material/Checkbox";
import FormControlLabel from "@mui/material/FormControlLabel";

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
        "&:last-child": {
          borderRight: "none", // 最後一欄不需要右邊框線
        },
        // 特定欄位寬度設定
        "&:nth-of-type(1)": { width: "60px" }, // 勾選框
        "&:nth-of-type(2)": { width: "160px" }, // 任務名稱
        "&:nth-of-type(3)": { width: "60px" }, // 信件總數量
        "&:nth-of-type(4)": { width: "60px" }, // 已寄出總數
        "&:nth-of-type(5)": { width: "80px" }, // 第一封寄出預計日期
        "&:nth-of-type(6)": { width: "80px" }, // 最後一封寄出預計日期
        "&:nth-of-type(7)": { width: "60px" }, // 是否暫停
        "&:nth-of-type(8)": { width: "80px" }, // 更新
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
        "&:nth-of-type(3), &:nth-of-type(4)": {
          fontWeight: "bold",
          // color: "#FF6A00" // 橘色
        },

      } 
    } 
  }
}));

function getTodayTimestamps() {
  const timeZone = "Asia/Taipei";

  const now = new Date();
  const formatter = new Intl.DateTimeFormat("en-US", {
    timeZone: timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  });

  const parts = formatter.formatToParts(now);
  const year = parts.find(p => p.type === 'year').value;
  const month = parts.find(p => p.type === 'month').value;
  const day = parts.find(p => p.type === 'day').value;

  const startDate = new Date(`${year}-${month}-${day}T00:00:00`);
  const todayStartTs = Math.floor(startDate.getTime() / 1000);
  const todayEndTs = todayStartTs + 24 * 60 * 60 * 1000;

  return [todayStartTs, todayEndTs];
};


export default function ShowAllTasks() {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(5);
  const { 
    loading, 
    statsData, 
    tasksData, 
    refresh, 
    isCheckingSends, 
    setIsCheckingSends 
  } = useContext(SendtaskListContext);
  const [loadingDots, setLoadingDots] = useState(0);
  const [updatedTodayUuids, setUpdatedTodayUuids] = useState([]);
  const { fetchCheckSends } = useCheckSends({ refresh, setIsCheckingSends, setUpdatedTodayUuids });
  const [searchText, setSearchText] = useState("");  // 搜尋任務名稱
  const [selectedUuids, setSelectedUuids] = useState([]);  // 勾選任務並只更新這些任務
  // 顯示狀況
  const [showExpiredOnly, setShowExpiredOnly] = useState(false);  // 是否只顯示已過期的任務
  const [showNotStartedOnly, setShowNotStartedOnly] = useState(false);  // 是否只顯示已過期的任務
  const [showRunningOnly, setShowRunningOnly] = useState(false);  // 是否只顯示已過期的任務
  const [todayStartTs, todayEndTs] = getTodayTimestamps();

  // 任務顯示模式
  const filteredTasks = (tasksData)
    ?.filter(row => {
      // 搜尋任務名稱
      if (searchText && !row.sendtask_id?.toLowerCase().includes(searchText.toLowerCase())) {
        return false;
      }

      // 過濾
      const stats = statsData[row.sendtask_uuid] || {};
      const lastPlan = stats.all_latest_plan_time;
      const firstPlan = stats.all_earliest_plan_time
      if (showExpiredOnly) {
        if (!lastPlan || lastPlan > todayStartTs) return false;
      } else if (showNotStartedOnly) {
        if (!firstPlan || firstPlan < todayEndTs) return false;
      } else if (showRunningOnly) {
        if (lastPlan < todayStartTs || firstPlan > todayEndTs) return false;
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
    <Box width="100%" overflow="hidden">
      <SimpleCard sx={{ padding:1 }}>
        <Stack direction="row" spacing={2} mb={2}>
          <Button
            variant="contained"
            color="primary"
            disabled={selectedUuids.length === 0}
            onClick={() => fetchCheckSends(selectedUuids)}
            size="small"
          >
            更新勾選任務
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
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
            <FormControlLabel
              control={
                <Checkbox
                  checked={showRunningOnly}
                  onChange={e => {
                    setShowRunningOnly(e.target.checked);
                    setPage(0);
                  }}
                  size="small"
                />
              }
              label="執行中"
              sx={{ margin: 0 }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={showNotStartedOnly}
                  onChange={e => {
                    setShowNotStartedOnly(e.target.checked);
                    setPage(0);
                  }}
                  size="small"
                />
              }
              label="未開始"
              sx={{ margin: 0 }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={showExpiredOnly}
                  onChange={e => {
                    setShowExpiredOnly(e.target.checked);
                    setPage(0);
                  }}
                  size="small"
                />
              }
              label="已結束"
              sx={{ margin: 0 }}
            />
          </Box>
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
                <TableCell>任務名稱</TableCell>
                <TableCell>信件<br />總數量</TableCell>
                <TableCell>已寄出<br />總數</TableCell>
                <TableCell>第一封寄出<br />預計日期</TableCell>
                <TableCell>最後一封寄出<br />預計日期</TableCell>
                <TableCell>是否暫停</TableCell>
                <TableCell>更新</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pagedTasks.map((row, index) => {
                const stats = statsData[row.sendtask_uuid] || { planned: "-", send: "-", success: "-" };
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
