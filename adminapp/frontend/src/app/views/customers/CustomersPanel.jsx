import { useState, useMemo, useContext } from 'react';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import { Box, Button, Divider, CircularProgress, Typography } from '@mui/material';
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

export default function CustomersPanel() {
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

  // 將 sendtask_uuids 陣列轉換為任務物件陣列
  const convertUuidsToTaskObjects = (sendtask_uuids) => {
    if (!sendtask_uuids || !Array.isArray(sendtask_uuids)) return [];
    
    return sendtask_uuids.map(uuid => {
      // 從 tasksData 中找到對應的任務
      const fullTaskData = tasksData.find(task => task.sendtask_uuid === uuid);
      return fullTaskData || { sendtask_uuid: uuid, sendtask_id: `未知任務 (${uuid})` };
    });
  };

  // 將任務物件陣列轉換為 UUID 陣列
  const convertTaskObjectsToUuids = (taskObjects) => {
    if (!taskObjects || !Array.isArray(taskObjects)) return [];
    
    return taskObjects.map(task => task.sendtask_uuid);
  };

  // 處理 Autocomplete 選擇變化
  const handleSendtasksChange = (customerId, newValue) => {
    setCustomerSendtasks(prev => ({
      ...prev,
      [customerId]: newValue || []
    }));
  };

  const handleSaveCustomerSendtasks = async (customer) => {
    const customerKey = customer.customer_name;
    const selectedSendtasks = customerSendtasks[customerKey] || customer.sendtask_uuids;
    
    try {
      setSavingCustomer(customerKey);

      // 轉換為 UUID 陣列格式
      const sendtaskUuids = convertTaskObjectsToUuids(selectedSendtasks);

      // 執行保存操作
      const result = await updateCustomerSendtasks(customerKey, sendtaskUuids);

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
      console.error(`客戶 ${customerKey} 的任務保存失敗:`, error);
      alert(`保存失敗: ${error.message}`);
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
    
    console.log(`客戶 ${customerKey} 的任務選擇已取消`);
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
          const sendtaskUuids = Array.isArray(customer.sendtask_uuids) ? customer.sendtask_uuids : [];
          
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
                      任務數: {sendtaskUuids.length}
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
                      value={
                        customerSendtasks[customerKey] || 
                        convertUuidsToTaskObjects(sendtaskUuids)
                      }
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
                      renderOption={(props, option) => {
                        const { key, ...otherProps } = props;
                        return (
                          <Box component="li" key={key} {...otherProps}>
                            <Box>
                              <Typography variant="body2">
                                {option.sendtask_id}
                              </Typography>
                            </Box>
                          </Box>
                        );
                      }}
                    />
                    {sendtaskUuids.length > 0 && (
                      <Box sx={{ mt: 2, p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                        <Typography variant="subtitle2" sx={{ mb: 1 }}>
                          當前任務 ({sendtaskUuids.length} 個):
                        </Typography>
                        {sendtaskUuids.map((uuid, idx) => {
                          const task = tasksData.find(t => t.sendtask_uuid === uuid);
                          return (
                            <Box key={uuid || idx} sx={{ mb: 1 }}>
                              <Typography variant="body2">
                                <strong>{task ? task.sendtask_id : `未知任務 (${uuid})`}</strong>
                              </Typography>
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
                    disabled={isCurrentlySaving}
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

