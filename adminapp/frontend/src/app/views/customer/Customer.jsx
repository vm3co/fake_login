import { useState, useEffect } from 'react';
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
  CircularProgress
} from '@mui/material';
import { styled } from '@mui/material/styles';
import {
  Assignment,
  Schedule,
  Search,
  FilterList,
} from '@mui/icons-material';

import useCustomer from 'app/hooks/useCustomer';
import { useCheckSends } from "app/hooks/useCheckSends";
import TaskDetail from './TaskDetail';


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

export default function Customer() {
  const [customerData, setCustomerData] = useState({
    sendtasks: null,
    acct_uuid: null
  });
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortBy, setSortBy] = useState('建立時間');
  const [showOnlyActive, setShowOnlyActive] = useState(false);
  const [showOnlyTriggered, setShowOnlyTriggered] = useState(false);
  const [detailDialog, setDetailDialog] = useState({
    open: false,
    task: null
  });

  // 新增：更新按鈕相關 state
  const [isCheckingSends, setIsCheckingSends] = useState(false);
  // const [updatedUuids, setUpdatedUuids] = useState([]);
  const [cooldowns, setCooldowns] = useState({}); // 用於追蹤每個任務的冷卻時間


  const { loading, error, sendtasksData, fetchCustomerSendtasksData } = useCustomer();

  // 載入客戶 Cookie 資料
  const loadCustomerData = () => {
    const sendtasks = parseTasks(getCookie('sendtasks'));
    const acct_uuid = getCookie('acct_uuid');
    setCustomerData({
      sendtasks,
      acct_uuid
    });
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
        totaltriggered: task.totaltriggered || 0,
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
    switch(status) {
      case 'triggered': return '已觸發';
      case 'active': return '進行中';
      case 'pending': return '等待中';
      case 'completed': return '已完成';
      default: return status;
    }
  };

  const getStatusColor = (status) => {
    switch(status) {
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
    await fetchCheckSends([uuid]);
    // 更新成功後，設定冷卻時間
    setCooldowns(prev => ({
      ...prev,
      [uuid]: Date.now()
    }));
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
              <MenuItem value="triggered">已觸發</MenuItem>
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
        <FilterSection>
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
        </FilterSection>

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
        </Box>

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
                    <Typography variant="h6" sx={{ fontWeight: 600 }}>
                      {task.name}
                    </Typography>
                    <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
                      <Schedule sx={{ mr: 1, color: '#64748b', fontSize: 20 }} />
                      <Typography variant="body2" color="text.secondary">
                        {task.startDate} - {task.endDate}
                      </Typography>
                    </Box>

                    <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
                      {taskStatus.triggered &&
                      <Chip 
                      label={`觸發率: ${task.totalsuccess > 0 ? ((task.totaltriggered / task.totalsuccess) * 100).toFixed(1) : 0}%`}
                      color="warning"
                      size="small"
                      />
                      }
                      <Chip 
                      label={`總信件數: ${task.totalplanned || 0}`}
                      color="info"
                      size="small"
                      />
                      {taskStatus.send && 
                      <Chip 
                      label={`已成功寄出: ${task.totalsuccess || 0}`}
                      color="secondary"
                      size="small"
                      />
                      }
                      {taskStatus.triggered &&
                      <Chip 
                      label={`已觸發: ${task.totaltriggered || 0}`}
                      color="error"
                      size="small"
                      />
                      }
                    </Box>
                    {taskStatus && (
                      <Box sx={{ mt: 1 }}>
                        <Typography variant="subtitle2">顯示：</Typography>
                        <ul style={{ margin: 0, paddingLeft: 16 }}>
                          {taskStatus.send && 
                          <li>
                            已成功寄送:
                            <ul>
                            {taskStatus.notTriggered && <li>未觸發</li>}
                            {taskStatus.triggered && <li>已觸發</li>}
                            </ul>
                          </li>}
                          {taskStatus.failed && <li>寄送失敗</li>}
                          {taskStatus.notyet && <li>待寄送</li>}
                          {!taskStatus.send && !taskStatus.failed && !taskStatus.notyet && !taskStatus.notTriggered && !taskStatus.triggered && <li>無</li>}
                        </ul>
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
                      onClick={() => handleCardClick(task)}
                    >
                      查看詳情
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      onClick={() => handleUpdateTask(task.sendtask_uuid)}
                      disabled={isCheckingSends || isInCooldown}
                      sx={{ minWidth: '80px' }}
                    >
                      {isInCooldown ? '冷卻中' : '更新'}
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
    </MainContainer>
  );
}