import { useState, useEffect } from 'react';
import axios from 'axios'; 
import {
  Box,
  Card,
  Typography,
  Button,
  Chip,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
  TextField,
  FormControl,
  Select,
  MenuItem,
  FormControlLabel,
  Checkbox,
  Avatar,
  IconButton,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Divider,
  Switch,
} from '@mui/material';
import { styled } from '@mui/material/styles';
import {
  Assignment,
  Close,
  Download,
  Search,
  ExpandMore as ExpandMoreIcon,
} from '@mui/icons-material';

const MainContainer = styled(Box)(() => ({
  display: 'flex',
  flexDirection: 'column',
  minHeight: '100vh',
  backgroundColor: '#f5f7fa',
  padding: '16px'
}));

const HeaderCard = styled(Card)(({ theme }) => ({
  marginBottom: theme.spacing(2),
  borderRadius: '12px',
  border: '1px solid #e0e7ff'
}));

const HeaderContent = styled(Box)(({ theme }) => ({
  padding: theme.spacing(3),
  display: 'flex',
  alignItems: 'center',
  gap: theme.spacing(2)
}));

const FilterCard = styled(Card)(({ theme }) => ({
  marginBottom: theme.spacing(2),
  borderRadius: '12px',
  padding: theme.spacing(2)
}));

const StyledTable = styled(Table)(() => ({
  '& .MuiTableHead-root': {
    '& .MuiTableRow-root': {
      '& .MuiTableCell-root': {
        backgroundColor: '#f8fafc',
        fontWeight: 600,
        borderBottom: '2px solid #e2e8f0',
        whiteSpace: 'nowrap'
      }
    }
  },
  '& .MuiTableBody-root': {
    '& .MuiTableRow-root': {
      '&:nth-of-type(even)': {
        backgroundColor: '#f8fafc'
      },
      '&:hover': {
        backgroundColor: '#e2e8f0'
      },
      '& .MuiTableCell-root': {
        borderBottom: '1px solid #e2e8f0',
        fontSize: '0.875rem'
      }
    }
  },
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
        "&:nth-of-type(1)": { width: "40px" }, // NO
        "&:nth-of-type(2)": { width: "45px" }, // 類型
        "&:nth-of-type(3)": { width: "60px" }, // 信箱
        "&:nth-of-type(4)": { width: "60px" }, // 信件主旨
        "&:nth-of-type(5)": { width: "60px" }, // 預計寄送時間
        "&:nth-of-type(6)": { width: "60px" }, // 實際寄送時間
        "&:nth-of-type(7)": { width: "160px" }, // 郵件讀取資訊
        "&:nth-of-type(8)": { width: "160px" }, // 按鈕點擊資訊
        "&:nth-of-type(9)": { width: "160px" }, // 附件開啟資訊
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
          }
        } 
      } 
    }
}));


// 格式化日期時間
const formatDateTime = (timestamp) => {
  if (!timestamp) return '-';
  const date = new Date(timestamp * 1000);
  return date.toLocaleString('zh-TW');
};

export default function TaskDetail({ task, open, onClose }) {
  const [taskData, setTaskData] = useState(null);
  const [mailTemplates, setMailTemplates] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [page, setPage] = useState(0);
  const [selectedUuids, setSelectedUuids] = useState([]);  // 勾選受測者並下載
  const [totalLogs, setTotalLogs] = useState(0);
  const [nowRowsPerPage, setNowRowsPerPage] = useState(20);
  const [isAsc, setIsAsc] = useState(false); // false for 'desc', true for 'asc'
  const [downloading, setDownloading] = useState(false);
  const [selectAllAcrossPages, setSelectAllAcrossPages] = useState(false); // 是否選取所有頁面所有資料


  // 篩選條件
  const [filters, setFilters] = useState({
    searchText:'',
    dateFrom: '',
    dateTo: '',
    resultType: 'ALL',
    showAccessed: false,
    showClicked: false,
    showFiled: false,
    sortBy: 'target_email',
    rowsPerPage: 20,
    sort: 'asc'
  });

  // 載入任務詳細資料
  const fetchTaskLogs = async () => {
    if (!task?.sendtask_uuid) return;

    try {
      setLoading(true);
      setError(null);
      // 獲取詳細日誌 (帶上所有參數)
      const response = await axios.post("/api/get_sendlog_detail", { 
        sendtask_uuid: task.sendtask_uuid,
        page: page + 1, // 後端頁碼從 1 開始
        ...filters 
      });

      const logsResult = response.data;
      if (logsResult.status === "success") {
        setLogs(logsResult.data || []);
        setTotalLogs(logsResult.total_count || 0);
      } else {
        throw new Error(logsResult.message || "獲取日誌資料失敗");
      }
    } catch (err) {
      console.error("獲取任務日誌失敗:", err);
      setError(err.response?.data?.detail || err.message || "獲取日誌資料失敗");
      setLogs([]);
      setTotalLogs(0);
    } finally {
      setLoading(false);
    }
  };

  // 首次載入或任務變更時，載入固定資訊
  useEffect(() => {
    const fetchInitialData = async () => {
        if (!task?.sendtask_uuid) return;
        
        // 重置狀態
        setLogs([]);
        setTotalLogs(0);
        setPage(0);
        setTaskData(null);

        try {
            const [taskResponse, mtmplResponse] = await Promise.all([
                axios.post("/api/get_sendlog_stats", { 
                    sendtask_uuids: [task.sendtask_uuid] 
                }),
                axios.get("/api/get_mtmpl")
            ]);

            const taskResult = taskResponse.data;
            if (taskResult.status === "success" && taskResult.data.length > 0) {
                setTaskData(taskResult.data[0]);
            }

            const mtmplResult = mtmplResponse.data;
            if (mtmplResult.status === "success") {
                setMailTemplates(mtmplResult.data || []);
            }
        } catch (error) {
            console.error("獲取初始資料失敗:", error);
        }
    };
    if (open && task) {
        fetchInitialData();
    };
  }, [open, task]);

  // 當分頁、篩選條件改變時，重新獲取日誌資料
  useEffect(() => {
    if (open && task) {
      setSelectedUuids([]);
      setSelectAllAcrossPages(false);
      fetchTaskLogs();
    } else if (!open) {
      // 清理舊資料
      setLogs([]);
      setTaskData(null);
      setPage(0);
      setFilters({
        searchText:'',
        dateFrom: '',
        dateTo: '',
        resultType: 'ALL',
        showAccessed: false,
        showClicked: false,
        showFiled: false,
        sortBy: 'target_email',
        rowsPerPage: 20,
        sort: 'asc'
      });
      setSelectedUuids([]);
      setSelectAllAcrossPages(false);
      setNowRowsPerPage(20);
      setIsAsc(false);
    }

  }, [open, task, page]);

  const handleDownloadCsv = async () => {
    if (!task?.sendtask_uuid) return;

    setDownloading(true);
    try {
      const response = await axios.post("/api/download_sendlog_csv", {
        sendtask_uuid: task.sendtask_uuid,
        selected_uuids: selectAllAcrossPages ? [] : selectedUuids,
        ...filters,
      }, {
        responseType: 'blob', // 告訴 axios 預期接收的是二進位檔案資料
      });

      if (response.status !== 200) {
        throw new Error(`下載失敗: ${response.statusText}`);
      }

      const blob = response.data;
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.style.display = "none";
      a.href = url;
      a.download = `sendlog_${task.sendtask_uuid}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

    } catch (err) {
      console.error("下載 CSV 失敗:", err);
      alert(`下載失敗: ${err.response?.data?.detail || err.message}`);
    } finally {
      setDownloading(false);
    }
  };

  const handleChangePage = (event, newPage) => {
    setPage(newPage);
  };

  return (
    <>
        <Dialog
        open={open}
        onClose={onClose}
        maxWidth="xl"
        fullWidth
        PaperProps={{
            sx: { height: '120vh' }
        }}
        >
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
                <Typography variant="h6">任務詳細資訊</Typography>
            </Box>
            <IconButton onClick={onClose}>
                <Close />
            </IconButton>
        </DialogTitle>

        <DialogContent sx={{ p: 0 }}>
            <MainContainer>
            {/* 任務基本資訊 */}
            {task && taskData && (
                <HeaderCard>
                <HeaderContent>
                    <Avatar sx={{ bgcolor: '#3b82f6', width: 56, height: 56 }}>
                    <Assignment />
                    </Avatar>
                    <Box sx={{ flex: 1 }}>
                    <Typography variant="h6" sx={{ fontWeight: 600, mb: 1 }}>
                        {task.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
                        {task.sendtask_uuid}
                    </Typography>
                    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                        <Chip 
                        label={`觸發率: ${taskData.totalsend > 0 ? ((taskData.totaltriggered / taskData.totalsend) * 100).toFixed(1) : 0}%`}
                        color="warning"
                        size="small"
                        />
                        <Chip 
                        label={`總信件數: ${taskData.totalplanned || 0}`}
                        color="info"
                        size="small"
                        />
                        <Chip 
                        label={`已寄出: ${taskData.totalsend || 0}`}
                        color="success"
                        size="small"
                        />
                        <Chip 
                        label={`已觸發: ${taskData.totaltriggered || 0}`}
                        color="error"
                        size="small"
                        />
                    </Box>
                    </Box>
                    <Box sx={{ display: 'flex', gap: 1 }}>
                      <Button 
                        variant="contained" 
                        size="small" 
                        startIcon={downloading ? <CircularProgress size={20} color="inherit" /> : <Download />}
                        onClick={handleDownloadCsv}
                        disabled={downloading}
                      >
                        {downloading ? '下載中...' :
                          (selectedUuids.length > 0 || selectAllAcrossPages) ? '下載選取資料' : '下載全部資料'
                        }
                      </Button>
                    </Box>
                </HeaderContent>
                </HeaderCard>
            )}

            <FilterCard>
                <Accordion sx={{ boxShadow: 'none', '&:before': { display: 'none' } }}>  
                    <AccordionSummary expandIcon={<ExpandMoreIcon />}>              
                        <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                            篩選項目
                        </Typography>
                    </AccordionSummary>
                    <AccordionDetails>
                      <Divider />
                      <br />
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap', mb: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                          <Typography variant="subtitle2" sx={{ fontWeight: 600 }}>
                              寄送時間
                          </Typography>
                          <TextField
                              size="small"
                              type="date"
                              label="起始日期"
                              value={filters.dateFrom}
                              onChange={(e) => setFilters({ ...filters, dateFrom: e.target.value })}
                              InputLabelProps={{ shrink: true }}
                              sx={{ width: 150 }}
                          />
                          <TextField
                              size="small"
                              type="date"
                              label="結束日期"
                              value={filters.dateTo}
                              onChange={(e) => setFilters({ ...filters, dateTo: e.target.value })}
                              InputLabelProps={{ shrink: true }}
                              sx={{ width: 150 }}
                          />
                          <FormControl  size="small" sx={{ minWidth: 120 }}>
                              <Select
                              value={filters.resultType}
                              onChange={(e) => setFilters({ ...filters, resultType: e.target.value })}
                              >
                              <MenuItem value="ALL">ALL</MenuItem>
                              <MenuItem value="notyet">待寄出</MenuItem>
                              <MenuItem value="send">已寄出</MenuItem>
                              <MenuItem value="failed">寄出失敗</MenuItem>
                              <MenuItem value="not_triggered">未觸發</MenuItem>
                              <MenuItem value="triggered">已觸發</MenuItem>
                              </Select>
                          </FormControl>
                          <TextField
                              size="small"
                              placeholder="搜尋姓名或郵件位址"
                              value={filters.searchText}
                              onChange={(e) => setFilters({ ...filters, searchText: e.target.value })}
                              InputProps={{
                                startAdornment: <Search sx={{ mr: 1, color: '#94a3b8' }} />
                              }}
                          />                                            
                        </Box>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                          <Typography variant="subtitle2">行為過濾：</Typography>
                          <FormControlLabel
                              control={
                                  <Checkbox
                                      checked={filters.showAccessed}
                                      onChange={(e) => setFilters({ ...filters, showAccessed: e.target.checked })}
                                      size="small"
                                  />
                              }
                              label="讀取"
                          />
                          <FormControlLabel
                              control={
                                  <Checkbox
                                      checked={filters.showClicked}
                                      onChange={(e) => setFilters({ ...filters, showClicked: e.target.checked })}
                                      size="small"
                                  />
                              }
                              label="點擊"
                          />
                          <FormControlLabel
                              control={
                                  <Checkbox
                                      checked={filters.showFiled}
                                      onChange={(e) => setFilters({ ...filters, showFiled: e.target.checked })}
                                      size="small"
                                  />
                              }
                              label="開啟"
                          />
                          <Typography variant="subtitle2">排序方式: </Typography>
                          <FormControl size="small" sx={{ minWidth: 160 }}>
                              <Select
                              value={filters.sortBy}
                              onChange={(e) => setFilters({ ...filters, sortBy: e.target.value })}
                              >
                              <MenuItem value="target_email">郵件地址</MenuItem>
                              <MenuItem value="plan_time">預計寄送時間</MenuItem>
                              <MenuItem value="send_time">實際寄送時間</MenuItem>
                              <MenuItem value="person_info">姓名</MenuItem>
                              </Select>
                          </FormControl>
                          <FormControlLabel
                            control={
                              <Switch
                                checked={isAsc}
                                onChange={(e) => {
                                  setIsAsc(e.target.checked);
                                  setFilters({ ...filters, sort: isAsc ? "asc" : "desc" });
                                }}
                                color="primary"
                              />
                            }
                            label={isAsc ? "正序" : "反序"}
                          />
                          <Typography variant="subtitle2">每頁 </Typography>
                          <FormControl size="small" sx={{ minWidth: 80 }}>
                              <Select
                                value={filters.rowsPerPage}
                                onChange={(e) => {
                                  setFilters({ ...filters, rowsPerPage: e.target.value });
                                }}
                              >
                              <MenuItem value={20}>20</MenuItem>
                              <MenuItem value={50}>50</MenuItem>
                              <MenuItem value={100}>100</MenuItem>
                              <MenuItem value={200}>200</MenuItem>
                              </Select>
                          </FormControl>
                          <Typography variant="subtitle2">筆 </Typography>  
                        </Box>
                      </Box>
                      <Box sx={{ display: 'flex', gap: 2 }}>
                        <Button 
                          variant="contained" 
                          size="small" 
                          color="secondary"
                          onClick={() => {
                            setFilters({
                              searchText:'',
                              dateFrom: '',
                              dateTo: '',
                              resultType: 'ALL',
                              showAccessed: false,
                              showClicked: false,
                              showFiled: false,
                              sortBy: 'target_email',
                              rowsPerPage: 20,
                              sort: 'asc'
                            });
                          }}>
                            清空
                        </Button>
                        <Button 
                          variant="contained" 
                          size="small" 
                          onClick={() => {
                            setNowRowsPerPage(filters.rowsPerPage);
                            setPage(0);
                            setSelectedUuids([]);
                            setSelectAllAcrossPages(false);
                            fetchTaskLogs();
                          }}>
                            查詢
                        </Button>
                      </Box>
                    </AccordionDetails>
                </Accordion>
            </FilterCard>

            {/* 資料表格 */}
            {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                {error}
                </Alert>
            )}

            {loading ? (
                <Box display="flex" alignItems="center" justifyContent="center" minHeight="300px">
                    <CircularProgress />
                    <Typography sx={{ ml: 2 }}>載入中...</Typography>
                </Box>
            ) : (
                <Card sx={{ borderRadius: '12px', overflow: 'hidden' }}>
                    <TablePagination
                        component="div"
                        count={totalLogs}
                        page={page}
                        onPageChange={handleChangePage}
                        rowsPerPage={nowRowsPerPage}
                        onRowsPerPageChange={() => {}}
                        rowsPerPageOptions={[]}
                        labelRowsPerPage=""
                        labelDisplayedRows={({ from, to, count }) => 
                        `${from}-${to} / 共 ${count} 筆`
                        }
                    />
                    {totalLogs > 0 && selectedUuids.length === logs.length && !selectAllAcrossPages && 
                      <Typography sx={{ ml: 2, mb: 1 }}>
                        已選取這個頁面上全部{logs.length}個項目
                        <Button 
                          onClick={() => {setSelectAllAcrossPages(true);}}
                          variant="text"
                          size="small"
                          sx={{ 
                            textTransform: 'none',
                            minWidth: 'unset',
                            padding: '0 4px',
                            verticalAlign: 'baseline'
                          }}
                        >
                            選取所有篩選資料項目
                        </Button>
                      </Typography>
                    }
                    {selectAllAcrossPages &&
                      <Typography sx={{ ml: 2, mb: 1 }}>
                        已選取全部{totalLogs}個篩選資料項目
                        <Button 
                          onClick={() => {
                            setSelectAllAcrossPages(false);
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
                          清除選取資料項目
                        </Button>
                      </Typography>
                    }
                    <TableContainer sx={{ maxHeight: '60vh' }}>
                        <StyledTable stickyHeader>
                        <TableHead>
                            <TableRow>
                            <TableCell>
                              選取下載 <br />
                              <Checkbox
                                  checked={totalLogs > 0 && selectedUuids.length === logs.length}
                                  indeterminate={selectedUuids.length > 0 && selectedUuids.length < logs.length}
                                  onChange={e => {
                                    if (e.target.checked) {
                                        setSelectedUuids([
                                        ...new Set([...selectedUuids, ...logs.map(log => log.uuid)])
                                        ]);
                                    } else {
                                        setSelectedUuids([]);
                                        setSelectAllAcrossPages(false);
                                    }                                    
                                  }}
                              />
                            </TableCell>
                            <TableCell>類型</TableCell>
                            <TableCell>受測人</TableCell>
                            <TableCell>信件主旨</TableCell>
                            <TableCell>預計寄送時間</TableCell>
                            <TableCell>實際寄送時間</TableCell>
                            <TableCell>郵件讀取資訊</TableCell>
                            <TableCell>按鈕點擊資訊</TableCell>
                            <TableCell>附件開啟資訊</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {logs.map((log, index) => {
                            const globalIndex = page * filters.rowsPerPage + index + 1;
                            const templateTitle = mailTemplates.find(
                              (tmpl) => tmpl.mtmpl_uuid === log.template_uuid
                            )?.mtmpl_title;

                            return (
                                <TableRow key={log.id || index}>
                                    <TableCell>
                                        <Box>
                                            <Checkbox
                                            checked={selectedUuids.includes(log.uuid)}
                                            onChange={e => {
                                                if (e.target.checked) {
                                                setSelectedUuids([...selectedUuids, log.uuid]);
                                                } else {
                                                setSelectedUuids(selectedUuids.filter(uuid => uuid !== log.uuid));
                                                }
                                            }}
                                            />{globalIndex}
                                        </Box>
                                    </TableCell>
                                    <TableCell>
                                        <Box>
                                            <Chip 
                                                label={log.access_dev ? '已觸發' : 
                                                  (log.send_time && log.send_res && log.send_res.includes("True")) ? '已寄出' : 
                                                  (log.send_time && log.send_res && log.send_res.includes("False")) ? '寄出失敗' : '待寄出'}
                                                size="small"
                                                color={log.access_dev ? 'error' : 
                                                  (log.send_time && log.send_res && log.send_res.includes("True")) ? 'success' :
                                                  (log.send_time && log.send_res && log.send_res.includes("False")) ? 'secondary' : 'info'}
                                            />
                                        </Box>
                                    </TableCell>
                                    <TableCell>
                                        <Typography>
                                            {log.person_info || ''}
                                        </Typography>
                                        <Typography>
                                            {log.target_email || ''}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>{templateTitle || log.template_uuid}</TableCell>
                                    <TableCell>{formatDateTime(log.plan_time)}</TableCell>
                                    <TableCell>{formatDateTime(log.send_time)}</TableCell>
                                    <TableCell>
                                        <Typography>
                                            <strong>{formatDateTime(log.access_time)}</strong>
                                        </Typography>
                                        <Typography>
                                            {log.access_src}
                                        </Typography>
                                        <Typography>
                                            {log.access_dev}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>
                                        <Typography>
                                            <strong>{formatDateTime(log.click_time)}</strong>
                                        </Typography>
                                        <Typography>
                                            {log.click_src}
                                        </Typography>
                                        <Typography>
                                            {log.click_dev}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>
                                        <Typography>
                                            <strong>{formatDateTime(log.file_time)}</strong>
                                        </Typography>
                                        <Typography>
                                            {log.file_src}
                                        </Typography>
                                        <Typography>
                                            {log.file_dev}
                                        </Typography>
                                    </TableCell>
                                </TableRow>
                            );
                            })}
                        </TableBody>
                        </StyledTable>
                    </TableContainer>
                </Card>
            )}
            </MainContainer>
        </DialogContent>
        </Dialog>
    </>
  );
}