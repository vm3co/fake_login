import { useState, useMemo, useContext } from 'react';
import { useSnackbar } from 'notistack';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import {
  Box, 
  Button, 
  Divider, 
  CircularProgress, 
  Typography, 
  FormControlLabel, 
} from '@mui/material';
import Accordion from '@mui/material/Accordion';
import AccordionActions from '@mui/material/AccordionActions';
import AccordionDetails from '@mui/material/AccordionDetails';
import AccordionSummary from '@mui/material/AccordionSummary';
import { styled } from '@mui/material';
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import Checkbox from "@mui/material/Checkbox";

import { SendtaskListContext } from "app/contexts/SendtaskListContext";
import CustomersContext from "app/contexts/CustomersContext";

const AccordionRoot = styled(Box)(({ theme }) => ({
  width: '100%',
  '& .heading': { fontSize: theme.typography.pxToRem(15) },
  '& .secondaryHeading': {
    color: theme.palette.text.secondary,
    fontSize: theme.typography.pxToRem(15)
  },
  '& .icon': {
    width: 20,
    height: 20,
    verticalAlign: 'bottom'
  },
  '& .details': { alignItems: 'center' },
  '& .column': { flexBasis: '33.33%' },
  '& .helper': {
    padding: theme.spacing(1, 2),
    borderLeft: `2px solid ${theme.palette.divider}`
  },
  '& .link': {
    textDecoration: 'none',
    color: theme.palette.primary.main,
    '&:hover': { textDecoration: 'underline' }
  }
}));

const parseTasks = (tasksData) => {
  if (!tasksData) return [];
  if (Array.isArray(tasksData)) return tasksData; // 如果已經是陣列，直接回傳
  if (typeof tasksData === 'string') {
    try {
      const parsed = JSON.parse(tasksData);
      return Array.isArray(parsed) ? parsed : []; // 確保解析後是陣列
    } catch (e) {
      console.error("解析客戶任務 JSON 失敗:", e);
      return []; // 解析失敗則給空陣列
    }
  }
  return []; // 對於其他類型，回傳空陣列
};

export default function CustomersPanel() {
  const { enqueueSnackbar } = useSnackbar();
  
  const { customers, loading, deleteCustomer, updateCustomerSendtasks } = useContext(CustomersContext);
  const { tasksData } = useContext(SendtaskListContext);
  const [selectedCustomers, setSelectedCustomers] = useState([]);  // 勾選客戶
  // 為每個客戶管理選中的 sendtasks
  const [customerSendtasks, setCustomerSendtasks] = useState({});
  const [savingCustomer, setSavingCustomer] = useState(null);

  // 按創建時間排序客戶列表
  const sortedCustomers = useMemo(() => {
    if (!customers || customers.length === 0) return [];
    
    return [...customers].sort((a, b) => {
      const dateA = new Date(a.create_time);
      const dateB = new Date(b.create_time);
      return dateB - dateA; // 降序排列，最晚創建的在前面
    });
  }, [customers]);


  const handleSendtasksChange = (customerKey, newValue) => {
    // newValue 是從 tasksData 來的完整任務物件陣列
    setCustomerSendtasks(prev => {
      const originalTasksRaw = customers.find(c => c.customer_name === customerKey)?.sendtasks;
      const currentTasksRaw = prev[customerKey] || originalTasksRaw;
      const currentTasks = parseTasks(currentTasksRaw);

      const newTasksState = newValue.map(fullTask => {
        const existingTask = currentTasks.find(t => t.uuid === fullTask.sendtask_uuid);
        // 如果任務已存在，保留其狀態；如果是新任務，則使用預設值
        return existingTask || {
          uuid: fullTask.sendtask_uuid,
          send: true,
          failed: true,
          notyet: true,
          notTriggered: true,
          triggered: true,
        };
      });

      return { ...prev, [customerKey]: newTasksState };
    });
  };

  const handleTaskStateChange = (customerKey, taskUuid, field, isChecked) => {
    setCustomerSendtasks(prev => {
      const originalTasksRaw = customers.find(c => c.customer_name === customerKey)?.sendtasks;
      const currentTasksRaw = prev[customerKey] || originalTasksRaw;
      const currentTasks = parseTasks(currentTasksRaw);

      const updatedTasks = currentTasks.map(task => {
        if (task.uuid !== taskUuid) return task;
        // 勾選「已寄出」時，同時勾選「未觸發」與「已觸發」
        if (field === 'send' && isChecked) {
          return { ...task, send: true, notTriggered: true, triggered: true };
        }
        // 取消「已寄出」時，同時取消「未觸發」與「已觸發」
        if (field === 'send' && !isChecked) {
          return { ...task, send: false, notTriggered: false, triggered: false };
        }
        // 取消「未觸發」或「已觸發」時，若兩者都為 false，則「已寄出」也要取消
        if ((field === 'notTriggered' || field === 'triggered') && !isChecked) {
          const otherField = field === 'notTriggered' ? 'triggered' : 'notTriggered';
          const otherChecked = !!task[otherField];
          if (!otherChecked) {
            return { ...task, [field]: false, [otherField]: false, send: false };
          }
          return { ...task, [field]: false };
        }
        // 勾選「未觸發」或「已觸發」時，若「已寄出」未勾選則自動勾選
        if ((field === 'notTriggered' || field === 'triggered') && isChecked) {
          return { ...task, [field]: true, send: true };
        }
        // 其他欄位正常處理
        return { ...task, [field]: isChecked };
      });
      
      return { ...prev, [customerKey]: updatedTasks };
    });
  };

  const handleSaveCustomerSendtasks = async (customer) => {
    const customerKey = customer.customer_name;
    const sendtasksForDb = customerSendtasks[customerKey];

    if (!sendtasksForDb) {
      console.log("沒有變更，無需保存。");
      return;
    }

    try {
      setSavingCustomer(customerKey);

      const result = await updateCustomerSendtasks(customerKey, sendtasksForDb);

      // 保存成功後，重新載入客戶資料
      if (result && result.status === 'success') {
        // 清空暫存選擇
        setCustomerSendtasks(prev => {
          const newState = { ...prev };
          delete newState[customerKey];
          return newState;
        });
      }
      
    } catch (error) {
      enqueueSnackbar(`保存失敗: ${error.message}`, { variant: 'warning' });
    } finally {
      setSavingCustomer(null);
    }
};

  // 處理取消操作
  const handleCancelCustomerSendtasks = (customer) => {
    const customerKey = customer.customer_name;

    // 清空該客戶的暫存選擇，恢復原始狀態
    setCustomerSendtasks(prev => {
      const newState = { ...prev };
      delete newState[customerKey];
      return newState;
    });
  };

  if (loading) {
    return (
      <Box display="flex" alignItems="center" justifyContent="center" minHeight="300px">
        <CircularProgress />
        <Typography sx={{ ml: 2 }}>載入客戶資料中...</Typography>
      </Box>
    );
  }

  // if (error) {
  //   return (
  //     <Alert severity="error" sx={{ mb: 2 }}>
  //       {error}
  //       <Button onClick={fetchCustomers} sx={{ ml: 1 }}>
  //         重試
  //       </Button>
  //     </Alert>
  //   );
  // }
  
  if (!customers || customers.length === 0) {
    return (
      <Box textAlign="center" py={4}>
        <Typography variant="h6" color="text.secondary">
          目前沒有客戶帳號資料
        </Typography>
      </Box>
    );
  }

  return (
    <AccordionRoot>
      <Button
        variant="contained"
        color="primary"
        disabled={selectedCustomers.length === 0}
        onClick={() => deleteCustomer(selectedCustomers)}
        size="small"
      >
        刪除勾選帳號
      </Button>
      <Divider />

      <Box sx={{ marginBottom: 2 }}>
        {sortedCustomers.map((customer, index) => {
          const customerKey = customer.customer_name;
          const isCurrentlySaving = savingCustomer === customerKey;

          const rawTasks = customerSendtasks[customerKey] || customer.sendtasks;
          const displayedTasks = parseTasks(rawTasks);

          const autocompleteValue = displayedTasks.map(task => {
            return tasksData.find(t => t.sendtask_uuid === task.uuid) || { sendtask_uuid: task.uuid, sendtask_id: `未知任務 (${task.uuid})` };
          });

          return (
            <Box key={customer.customer_name || index}>
              <Box sx={{ display: 'flex', alignItems: 'center' }}>
                <Checkbox
                  checked={selectedCustomers.includes(customer.customer_name)}
                  onChange={e => {
                    if (e.target.checked) {
                      setSelectedCustomers([...selectedCustomers, customer.customer_name]);
                    } else {
                      setSelectedCustomers(selectedCustomers.filter(name => name !== customer.customer_name));
                    }
                  }}
                />
                <Typography variant="body1">{index + 1}</Typography>
              </Box>
              <Accordion>
                <AccordionSummary
                  expandIcon={<ExpandMoreIcon />}
                  aria-controls={`panel${index}-content`}
                  id={`panel${index}-header`}
                >
                  <Box className="column">
                    <Typography className="heading">
                      {customer.customer_name}
                    </Typography>
                  </Box>

                  <Box className="column">
                    <Typography className="secondaryHeading">
                      {customer.customer_full_name || ''}
                    </Typography>
                  </Box>

                  <Box className="column">
                    <Typography className="secondaryHeading">
                      任務數: {displayedTasks.length}
                    </Typography>
                  </Box>
                </AccordionSummary>

                <AccordionDetails className="details">
                  <Box className="column helper">
                    <Autocomplete
                      multiple
                      filterSelectedOptions
                      disabled={isCurrentlySaving}
                      id={`tags-outlined-${customerKey || index}`}
                      options={tasksData}
                      getOptionLabel={(option) => option.sendtask_id}
                      value={autocompleteValue}
                      onChange={(event, newValue) => handleSendtasksChange(customerKey, newValue)}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          fullWidth
                          variant="outlined"
                          placeholder="選擇任務"
                          label="客戶任務"
                          disabled={isCurrentlySaving}
                        />
                      )}
                      renderOption={(props, option) => (
                        <Box component="li" {...props} key={option.sendtask_uuid}>
                          <Typography variant="body2">{option.sendtask_id}</Typography>
                        </Box>
                      )}
                    />
                    {displayedTasks.length > 0 && (
                      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                          當前任務 ({displayedTasks.length} 個):
                        </Typography>
                        {displayedTasks.map((task, idx) => {
                          const taskInfo = tasksData.find(t => t.sendtask_uuid === task.uuid);
                          return (
                            <Box key={task.uuid || idx} sx={{ mb: 1, display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
                              <Typography variant="body2" sx={{ minWidth: '150px', mr: 2 }}>
                                <strong>{taskInfo ? taskInfo.sendtask_id : `未知任務 (${task.uuid})`}</strong>
                              </Typography>

                              <FormControlLabel
                                control={<Checkbox checked={!!task.send} onChange={(e) => handleTaskStateChange(customerKey, task.uuid, 'send', e.target.checked)} size="small" />}
                                label="已寄出"
                              />
                              <FormControlLabel
                                control={<Checkbox checked={!!task.failed} onChange={(e) => handleTaskStateChange(customerKey, task.uuid, 'failed', e.target.checked)} size="small" />}
                                label="寄出失敗"
                              />
                              <FormControlLabel
                                control={<Checkbox checked={!!task.notyet} onChange={(e) => handleTaskStateChange(customerKey, task.uuid, 'notyet', e.target.checked)} size="small" />}
                                label="未寄出"
                              />
                              (已寄出中的：
                              <FormControlLabel
                                control={<Checkbox checked={!!task.notTriggered} onChange={(e) => handleTaskStateChange(customerKey, task.uuid, 'notTriggered', e.target.checked)} size="small" />}
                                label="未觸發"
                              />
                              <FormControlLabel
                                control={<Checkbox checked={!!task.triggered} onChange={(e) => handleTaskStateChange(customerKey, task.uuid, 'triggered', e.target.checked)} size="small" />}
                                label="已觸發"
                              />
                              )
                            </Box>
                          );
                        })}
                      </Box>
                    )}
                  </Box>
                </AccordionDetails>

                <Divider />

                <AccordionActions>
                  <Button 
                    size="small"
                    disabled={isCurrentlySaving}
                    onClick={() => handleCancelCustomerSendtasks(customer)}
                  >
                    取消
                  </Button>
                  <Button 
                    size="small" 
                    color="primary"
                    disabled={isCurrentlySaving || !customerSendtasks[customerKey]} // 沒變更時禁用
                    onClick={() => handleSaveCustomerSendtasks(customer)}
                    startIcon={isCurrentlySaving ? <CircularProgress size={16} /> : null}
                  >
                    {isCurrentlySaving ? '保存中...' : '保存'}
                  </Button>
                </AccordionActions>
              </Accordion>
            </Box>
          );
        })}
      </Box>

    </AccordionRoot>
  );
}

