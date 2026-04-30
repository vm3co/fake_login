import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Card,
  Typography,
  Button,
  Paper,
  Chip,
  Alert,
  TextField,
  FormControl,
  Select,
  MenuItem,
  Switch,
  FormControlLabel,
  Avatar,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Divider,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import StopIcon from '@mui/icons-material/Stop';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useSnackbar } from 'notistack';
import { styled } from '@mui/material/styles';
import {
  Assignment,
  Schedule,
  Search,
  FilterList,
  AddCircleOutline,
  BuildCircle,
} from '@mui/icons-material';
import axios from 'axios';

import useCustomer from 'app/hooks/useCustomer';
import { useCheckSends } from "app/hooks/useCheckSends";
import TaskDetail from './TaskDetail';
import CreateTask from './CreateTask';


const MainContainer = styled(Box)(() => ({
  display: 'flex',
  minHeight: '100vh',
  backgroundColor: '#f5f7fa'
}));

const LeftSidebar = styled(Paper)(({ theme }) => ({
  width: '280px',
  padding: theme.spacing(3),
  margin: theme.spacing(2),
  marginRight: 0,
  borderRadius: '12px',
  height: 'fit-content',
  position: 'sticky',
  top: theme.spacing(2)
}));

const RightContent = styled(Box)(({ theme }) => ({
  flex: 1,
  padding: theme.spacing(2),
  paddingLeft: theme.spacing(3)
}));

const TaskCard = styled(Card)(({ theme }) => ({
  marginBottom: theme.spacing(2),
  borderRadius: '12px',
  transition: 'all 0.2s ease-in-out',
  border: '1px solid #e0e7ff',
  '&:hover': {
    transform: 'translateY(-2px)',
    boxShadow: '0 8px 25px rgba(0,0,0,0.1)',
    borderColor: '#3b82f6'
  }
}));

const TaskHeader = styled(Box)(({ theme }) => ({
  display: 'flex',
  alignItems: 'center',
  padding: theme.spacing(2),
  borderBottom: '1px solid #f1f5f9'
}));

const FilterSection = styled(Box)(({ theme }) => ({
  marginBottom: theme.spacing(3)
}));

const StatusChip = styled(Chip)(({ status }) => ({
  fontWeight: 600,
  ...(status === 'active' && {
    backgroundColor: '#dcfce7',
    color: '#166534'
  }),
  ...(status === 'pending' && {
    backgroundColor: '#fef3c7',
    color: '#92400e'
  }),
  ...(status === 'completed' && {
    backgroundColor: '#dbeafe',
    color: '#1e40af'
  })
}));

// 獲取特定 Cookie 的函數
function getCookie(name) {
  const value = document.cookie
    .split("; ")
    .find(row => row.startsWith(`${name}=`));

  if (!value) return null;

  try {
    const decoded = decodeURIComponent(value.split("=")[1]);
    return JSON.parse(decoded);
  } catch {
    return decodeURIComponent(value.split("=")[1]);
  }
}

const parseTasks = (sendtasks) => {
  if (!sendtasks) return [];
  if (Array.isArray(sendtasks)) return sendtasks; // 如果已經是陣列，直接回傳
  if (typeof sendtasks === 'string') {
    try {
      const parsed = JSON.parse(sendtasks);
      return Array.isArray(parsed) ? parsed : []; // 確保解析後是陣列
    } catch (e) {
      console.error("解析客戶任務 JSON 失敗:", e);
      return []; // 解析失敗則給空陣列
    }
  }
  return []; // 對於其他類型，回傳空陣列
};

// 格式化日期函數
const formatDate = (timestamp, type = "datetime") => {
  if (!timestamp || timestamp === 0) return "-";

  const date = new Date(timestamp * 1000);

  if (type === "date") {
    return date.toLocaleDateString('zh-TW');
  }
  return date.toLocaleString('zh-TW');
};

// 專案狀態文字與顏色
const getProjectStatusText = (status) => {
  switch (status) {
    case 'created': return '已建立';
    case 'active': return '執行中';
    case 'stopped': return '已停止';
    case 'deleted': return '已刪除';
    default: return status;
  }
};

const getProjectStatusColor = (status) => {
  switch (status) {
    case 'created': return { bg: '#dbeafe', color: '#1e40af' };
    case 'active': return { bg: '#dcfce7', color: '#166534' };
    case 'stopped': return { bg: '#fed7aa', color: '#9a3412' };
    case 'deleted': return { bg: '#f1f5f9', color: '#64748b' };
    default: return { bg: '#f1f5f9', color: '#64748b' };
  }
};

export default function Customer() {
  const [customerData, setCustomerData] = useState({
    sendtasks: null,
    acct_uuid: null,
    customer_uuid: null,
    task_creation_enabled: false,
    task_creation_org_uuid: ''
  });
  const { enqueueSnackbar } = useSnackbar();
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('建立時間');
  const [showOnlyActive, setShowOnlyActive] = useState(false);
  const [showOnlyTriggered, setShowOnlyTriggered] = useState(false);
  const [detailDialog, setDetailDialog] = useState({
    open: false,
    task: null
  });
  const [createTaskOpen, setCreateTaskOpen] = useState(false);

  // 新增：更新按鈕相關 state
  const [isCheckingSends, setIsCheckingSends] = useState(false);
  // const [updatedUuids, setUpdatedUuids] = useState([]);
  const [cooldowns, setCooldowns] = useState({}); // 用於追蹤每個任務的冷卻時間

  // 我的任務相關 state
  const [myProjects, setMyProjects] = useState([]);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [operatingProject, setOperatingProject] = useState(null); // 正在操作的專案 UUID

  const { loading, error, sendtasksData, fetchCustomerSendtasksData } = useCustomer();

  // 載入客戶 Cookie 資料
  const loadCustomerData = () => {
    const sendtasks = parseTasks(getCookie('sendtasks'));
    const acct_uuid = getCookie('acct_uuid');
    const customer_uuid = getCookie('customer_uuid');
    const task_creation_enabled = getCookie('task_creation_enabled') === true || getCookie('task_creation_enabled') === 'true';
    const task_creation_org_uuid = getCookie('task_creation_org_uuid') || '';
    setCustomerData({
      sendtasks,
      acct_uuid,
      customer_uuid,
      task_creation_enabled,
      task_creation_org_uuid
    });
  };

  // 取得客戶建立的專案列表
  const fetchMyProjects = useCallback(async () => {
    const customerUuid = getCookie('customer_uuid');
    if (!customerUuid) return;
    setLoadingProjects(true);
    try {
      const res = await axios.get(`/api/task/get_customer_tasks?customer_uuid=${customerUuid}`);
      if (res.data?.status === 'success') {
        setMyProjects(res.data.data || []);
      }
    } catch (err) {
      console.error('取得專案列表失敗:', err);
    } finally {
      setLoadingProjects(false);
    }
  }, []);

  // 啟動任務
  const handleStartTask = async (testcaseUuid) => {
    setOperatingProject(testcaseUuid);
    try {
      const res = await axios.post('/api/task/create_sendtask', { testcase_uuid: testcaseUuid });
      if (res.data?.status === 'success') {
        enqueueSnackbar('任務啟動成功！', { variant: 'success' });
        fetchMyProjects();
      }
    } catch (err) {
      enqueueSnackbar(err.response?.data?.detail || '啟動任務失敗', { variant: 'error' });
    } finally {
      setOperatingProject(null);
    }
  };

  // 停止任務
  const handleStopTask = async (sendtaskUuid) => {
    setOperatingProject(sendtaskUuid);
    try {
      const res = await axios.post('/api/task/delete_sendtask', { sendtask_uuid: sendtaskUuid });
      if (res.data?.status === 'success') {
        enqueueSnackbar('任務已停止', { variant: 'success' });
        fetchMyProjects();
      }
    } catch (err) {
      enqueueSnackbar(err.response?.data?.detail || '停止任務失敗', { variant: 'error' });
    } finally {
      setOperatingProject(null);
    }
  };

  // 刪除專案
  const handleDeleteProject = async (testcaseUuid) => {
    setOperatingProject(testcaseUuid);
    try {
      const res = await axios.post('/api/task/delete_testcase', { testcase_uuid: testcaseUuid });
      if (res.data?.status === 'success') {
        enqueueSnackbar('專案已刪除', { variant: 'success' });
        fetchMyProjects();
      }
    } catch (err) {
      enqueueSnackbar(err.response?.data?.detail || '刪除專案失敗', { variant: 'error' });
    } finally {
      setOperatingProject(null);
    }
  };

  // 初始化更新 Hook
  const { fetchCheckSends } = useCheckSends({
    refresh: fetchCustomerSendtasksData,
    setIsCheckingSends,
    // setUpdatedTodayUuids: setUpdatedUuids,
  });

  // 組件載入時讀取 Cookie
  useEffect(() => {
    loadCustomerData();
  }, []);

  useEffect(() => {
    if (customerData.sendtasks && customerData.sendtasks.length > 0) {
      fetchCustomerSendtasksData();
    }
  }, [customerData.sendtasks]);

  // 載入我的任務
  useEffect(() => {
    if (customerData.task_creation_enabled && customerData.customer_uuid) {
      fetchMyProjects();
    }
  }, [customerData.task_creation_enabled, customerData.customer_uuid, fetchMyProjects]);

  // 處理冷卻時間
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      const newCooldowns = { ...cooldowns };
      let changed = false;
      for (const uuid in newCooldowns) {
        if (now - newCooldowns[uuid] >= 10000) {
          delete newCooldowns[uuid];
          changed = true;
        }
      }
      if (changed) setCooldowns(newCooldowns);
    }, 1000); // 每秒檢查一次
    return () => clearInterval(interval);
  }, [cooldowns]);

  // 準備任務資料
  const prepareTaskData = () => {
    return sendtasksData.map((task, index) => ({
      id: index + 1,
      sendtask_uuid: task.sendtask_uuid,
      name: task.sendtask_id,
      status: task.status,
      startDate: formatDate(task.test_start_ut, "date"),
      endDate: task.stop_time_new === -1 ? formatDate(task.test_end_ut, "date") : formatDate(task.stop_time_new, "date"),
      is_pause: task.is_pause,
      totalplanned: task.totalplanned || 0,
      totalsuccess: task.totalsuccess || 0,
      totalfailed: task.totalfailed || 0,
      totaltriggered: task.totaltriggered || 0,
      totalnotyet: task.totalnotyet || 0,
    }));
  };

  const taskData = prepareTaskData();

  // 篩選任務
  const filteredTasks = taskData.filter(task => {
    const matchesSearch = task.name.toLowerCase().includes(searchText.toLowerCase());
    const matchesStatus = statusFilter === 'all' || task.status === statusFilter;
    const matchesActive = !showOnlyActive || task.status === 'active';
    const matchesTriggered = !showOnlyTriggered || task.totaltriggered > 0;

    return matchesSearch && matchesStatus && matchesActive && matchesTriggered;
  });

  const getStatusText = (status) => {
    switch (status) {
      case 'triggered': return '已觸發';
      case 'active': return '進行中';
      case 'pending': return '等待中';
      case 'completed': return '已完成';
      default: return status;
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'triggered': return '#ef4444';
      case 'active': return '#10b981';
      case 'pending': return '#f59e0b';
      case 'completed': return '#3b82f6';
      default: return '#6b7280';
    }
  };

  // 手動重新載入資料
  const handleRefreshData = () => {
    loadCustomerData();
    if (customerData.sendtasks) {
      fetchCustomerSendtasksData();
    }
  };

  const handleCardClick = (task) => {
    const taskStatus = customerData.sendtasks.find(t => t.uuid === task.sendtask_uuid);
    setDetailDialog({
      open: true,
      task: { ...task, ...taskStatus }
    });
  };

  // 處理單一任務更新的函式
  const handleUpdateTask = async (uuid) => {
    // Check cooldown
    if (cooldowns[uuid] && (Date.now() - cooldowns[uuid] < 10000)) {
      enqueueSnackbar("任務已是最新狀態", { variant: 'info' });
      return;
    }
    const result = await fetchCheckSends([uuid]);
    if (!result) return;

    // 更新成功後，設定冷卻時間
    setCooldowns(prev => ({
      ...prev,
      [uuid]: Date.now()
    }));
  };

  // 建立任務成功回呼
  const handleCreateSuccess = (testcaseUuid) => {
    setCreateTaskOpen(false);
    fetchMyProjects(); // 重新整理專案列表
  };


  return (
    <MainContainer>
      {/* 左側篩選面板 */}
      <LeftSidebar elevation={0}>
        <Box sx={{ display: 'flex', alignItems: 'center', mb: 3 }}>
          <FilterList sx={{ mr: 1, color: '#6366f1' }} />
          <Typography variant="h6" sx={{ fontWeight: 600 }}>
            篩選條件
          </Typography>
        </Box>

        <FilterSection>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
            關鍵字搜尋
          </Typography>
          <TextField
            fullWidth
            size="small"
            placeholder="輸入任務名稱"
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            InputProps={{
              startAdornment: <Search sx={{ mr: 1, color: '#94a3b8' }} />
            }}
          />
        </FilterSection>

        <FilterSection>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
            狀態篩選
          </Typography>
          <FormControl fullWidth size="small">
            <Select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <MenuItem value="all">全部</MenuItem>
              {/* <MenuItem value="triggered">已觸發</MenuItem> */}
              <MenuItem value="active">進行中</MenuItem>
              <MenuItem value="pending">等待中</MenuItem>
              <MenuItem value="completed">已完成</MenuItem>
            </Select>
          </FormControl>
        </FilterSection>

        <FilterSection>
          <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>
            排序方式
          </Typography>
          <FormControl fullWidth size="small">
            <Select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value)}
            >
              <MenuItem value="建立時間">建立時間</MenuItem>
              <MenuItem value="任務名稱">任務名稱</MenuItem>
              <MenuItem value="狀態">狀態</MenuItem>
            </Select>
          </FormControl>
        </FilterSection>

        <FilterSection>
          <FormControlLabel
            control={
              <Switch
                checked={showOnlyActive}
                onChange={(e) => setShowOnlyActive(e.target.checked)}
                color="primary"
              />
            }
            label="只顯示進行中"
          />
        </FilterSection>
        {customerData.task_creation_enabled && (
          <FilterSection>
            <FormControlLabel
              control={
                <Switch
                  // checked={ }
                  // onChange={ }
                  color="primary"
                />
              }
              label="只顯示使用者建立之任務"
            />
          </FilterSection>
        )}

        {/* <FilterSection>
          <FormControlLabel
            control={
              <Switch
                checked={showOnlyTriggered}
                onChange={(e) => setShowOnlyTriggered(e.target.checked)}
                color="primary"
              />
            }
            label="只顯示已觸發"
          />
        </FilterSection> */}

      </LeftSidebar>

      {/* 右側內容區域 */}
      <RightContent>
        <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography variant="h4" sx={{ fontWeight: 600, mb: 1 }}>
              社交工程任務清單
            </Typography>
            <Typography variant="body2" color="text.secondary">
              顯示 {filteredTasks.length} 個任務 / 共 {taskData.length} 個
            </Typography>
          </Box>
          {customerData.task_creation_enabled && (
            <Button
              variant="contained"
              color="primary"
              startIcon={<AddCircleOutline />}
              onClick={() => setCreateTaskOpen(true)}
              sx={{ borderRadius: '8px', fontWeight: 600 }}
            >
              新增任務
            </Button>
          )}
        </Box>

        {/* ====== 我的任務區塊 ====== */}
        {customerData.task_creation_enabled && (
          <Paper elevation={0} sx={{ mb: 3, p: 2, borderRadius: '12px', border: '1px solid #e0e7ff' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <BuildCircle sx={{ color: '#6366f1' }} />
                <Typography variant="h6" sx={{ fontWeight: 600 }}>
                  我的任務
                </Typography>
                <Chip label={myProjects.filter(p => p.status !== 'deleted').length} size="small" color="primary" />
              </Box>
              <IconButton size="small" onClick={fetchMyProjects} disabled={loadingProjects}>
                <RefreshIcon sx={{ fontSize: 20 }} />
              </IconButton>
            </Box>

            {loadingProjects ? (
              <Box display="flex" alignItems="center" justifyContent="center" py={2}>
                <CircularProgress size={20} />
                <Typography sx={{ ml: 1 }} variant="body2">載入中...</Typography>
              </Box>
            ) : myProjects.filter(p => p.status !== 'deleted').length === 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                尚未建立任何任務，點擊「新增任務」開始建立
              </Typography>
            ) : (
              <TableContainer>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ '& th': { fontWeight: 700, color: '#475569', bgcolor: '#f8fafc' } }}>
                      <TableCell>專案名稱</TableCell>
                      <TableCell>類型</TableCell>
                      <TableCell>狀態</TableCell>
                      <TableCell>建立時間</TableCell>
                      <TableCell align="right">操作</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {myProjects.filter(p => p.status !== 'deleted').map((project) => {
                      const statusStyle = getProjectStatusColor(project.status);
                      const isOperating = operatingProject === project.testcase_uuid || operatingProject === project.sendtask_uuid;
                      return (
                        <TableRow key={project.testcase_uuid} sx={{ '&:hover': { bgcolor: '#f8fafc' } }}>
                          <TableCell>
                            <Typography variant="body2" fontWeight={600}>{project.task_name}</Typography>
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={project.task_type === 'pre' ? '前測' : '正式'}
                              size="small"
                              sx={{ fontWeight: 600, fontSize: '0.7rem' }}
                            />
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={getProjectStatusText(project.status)}
                              size="small"
                              sx={{ fontWeight: 600, fontSize: '0.7rem', bgcolor: statusStyle.bg, color: statusStyle.color }}
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption" color="text.secondary">
                              {project.created_at ? new Date(project.created_at).toLocaleString('zh-TW') : '-'}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end' }}>
                              {/* 啟動任務按鈕：只有 created 狀態可按 */}
                              {project.status === 'created' && (
                                <Button
                                  size="small"
                                  variant="contained"
                                  color="success"
                                  startIcon={isOperating ? <CircularProgress size={14} color="inherit" /> : <PlayArrowIcon />}
                                  onClick={() => handleStartTask(project.testcase_uuid)}
                                  disabled={isOperating}
                                  sx={{ fontSize: '0.75rem', minWidth: 0, px: 1.5 }}
                                >
                                  啟動
                                </Button>
                              )}
                              {/* 停止任務按鈕：只有 active 狀態可按 */}
                              {project.status === 'active' && (
                                <Button
                                  size="small"
                                  variant="outlined"
                                  color="warning"
                                  startIcon={isOperating ? <CircularProgress size={14} /> : <StopIcon />}
                                  onClick={() => handleStopTask(project.sendtask_uuid)}
                                  disabled={isOperating}
                                  sx={{ fontSize: '0.75rem', minWidth: 0, px: 1.5 }}
                                >
                                  停止
                                </Button>
                              )}
                              {/* 刪除專案按鈕：created 或 stopped 狀態可按 */}
                              {(project.status === 'created' || project.status === 'stopped') && (
                                <Button
                                  size="small"
                                  variant="outlined"
                                  color="error"
                                  startIcon={isOperating ? <CircularProgress size={14} /> : <DeleteOutlineIcon />}
                                  onClick={() => handleDeleteProject(project.testcase_uuid)}
                                  disabled={isOperating}
                                  sx={{ fontSize: '0.75rem', minWidth: 0, px: 1.5 }}
                                >
                                  刪除
                                </Button>
                              )}
                            </Box>
                          </TableCell>
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Paper>
        )}

        {error && (
          <Alert severity="error" sx={{ mb: 2, borderRadius: '12px' }}>
            {error}
            <Button onClick={handleRefreshData} sx={{ ml: 1 }}>
              重試
            </Button>
          </Alert>
        )}

        {!customerData.sendtasks ? (
          <Alert
            severity="info"
            sx={{ borderRadius: '12px' }}
          >
            未找到任務資料，請洽詢管理者
          </Alert>
        ) : loading ? (
          <Box display="flex" alignItems="center" justifyContent="center" minHeight="300px">
            <CircularProgress />
            <Typography sx={{ ml: 2 }}>載入任務統計資料中...</Typography>
          </Box>
        ) : filteredTasks.length === 0 ? (
          <Alert severity="warning" sx={{ borderRadius: '12px' }}>
            沒有符合篩選條件的任務
          </Alert>
        ) : (
          filteredTasks.map((task) => {
            const taskStatus = customerData.sendtasks.find(t => t.uuid === task.sendtask_uuid);
            const isInCooldown = cooldowns[task.sendtask_uuid] && (Date.now() - cooldowns[task.sendtask_uuid] < 10000);
            return (
              <TaskCard
                key={task.id}
                elevation={0}
              >
                <TaskHeader>
                  <Avatar
                    sx={{
                      bgcolor: getStatusColor(task.status),
                      mr: 2
                    }}
                  >
                    <Assignment />
                  </Avatar>

                  <Box sx={{ flex: 1 }}>
                    <Typography variant="h6"
                      onClick={() => handleCardClick(task)}
                      sx={{
                        cursor: 'pointer',
                        color: 'primary.main',
                        '&:hover': {
                          textDecoration: 'underline',
                        },
                        fontWeight: 'bold'
                      }}>
                      {task.name}
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Schedule sx={{ mr: 1, color: '#64748b', fontSize: 20 }} />
                      <Typography variant="body2" color="text.secondary">
                        {task.startDate} - {task.endDate}
                      </Typography>
                    </Box>

                    {taskStatus && (
                      <Box sx={{ mt: 1.5 }}>
                        {/* 總數徽章 */}
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Chip
                            label={`📋 總數：${task.totalplanned || 0}`}
                            size="small"
                            sx={{
                              backgroundColor: '#e0e7ff',
                              color: '#3730a3',
                              fontWeight: 700,
                              fontSize: '0.78rem',
                              borderRadius: '8px',
                            }}
                          />
                        </Box>
                        {/* 統計徽章列 */}
                        <Box sx={{ display: 'flex', gap: 0.8, flexWrap: 'wrap' }}>
                          {taskStatus.send && (
                            <Chip
                              label={`✅ 已寄出：${task.totalsuccess}`}
                              size="small"
                              sx={{
                                backgroundColor: '#dcfce7',
                                color: '#15803d',
                                fontWeight: 600,
                                fontSize: '0.75rem',
                                borderRadius: '8px',
                              }}
                            />
                          )}
                          {taskStatus.failed && (
                            <Chip
                              label={`❌ 失敗：${task.totalfailed}`}
                              size="small"
                              sx={{
                                backgroundColor: '#fee2e2',
                                color: '#b91c1c',
                                fontWeight: 600,
                                fontSize: '0.75rem',
                                borderRadius: '8px',
                              }}
                            />
                          )}
                          {taskStatus.notyet && (
                            <Chip
                              label={`⏳ 待寄送：${task.totalnotyet}`}
                              size="small"
                              sx={{
                                backgroundColor: '#fef9c3',
                                color: '#a16207',
                                fontWeight: 600,
                                fontSize: '0.75rem',
                                borderRadius: '8px',
                              }}
                            />
                          )}
                          {!taskStatus.send && !taskStatus.failed && !taskStatus.notyet && !taskStatus.notTriggered && !taskStatus.triggered && (
                            <Chip
                              label="— 無資料"
                              size="small"
                              sx={{
                                backgroundColor: '#f1f5f9',
                                color: '#64748b',
                                fontWeight: 600,
                                fontSize: '0.75rem',
                                borderRadius: '8px',
                              }}
                            />
                          )}
                        </Box>
                      </Box>
                    )}
                  </Box>

                  <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                    <StatusChip
                      label={getStatusText(task.status)}
                      status={task.status}
                      size="small"
                    />
                  </Box>
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 1 }}>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => handleUpdateTask(task.sendtask_uuid)}
                      disabled={isCheckingSends || isInCooldown}
                      sx={{ minWidth: '130px' }}
                    >
                      {isInCooldown ? '目前為最新資料' : '更新'}
                    </Button>
                  </Box>
                </TaskHeader>
              </TaskCard>
            );
          })
        )}
      </RightContent>

      <TaskDetail
        task={detailDialog.task}
        open={detailDialog.open}
        onClose={() => setDetailDialog({ open: false, task: null })}
      />

      {/* 新增任務 Dialog */}
      <Dialog
        open={createTaskOpen}
        onClose={() => setCreateTaskOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          新增任務
          <IconButton onClick={() => setCreateTaskOpen(false)} size="small">
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent>
          <CreateTask onSuccess={handleCreateSuccess} />
        </DialogContent>
      </Dialog>
    </MainContainer>
  );
}