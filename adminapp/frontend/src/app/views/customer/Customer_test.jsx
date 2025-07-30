import { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Chip,
  Alert,
  Grid,
  List,
  ListItem,
  ListItemText
} from '@mui/material';
import { styled } from '@mui/material/styles';

const StyledContainer = styled(Box)(({ theme }) => ({
  padding: theme.spacing(3),
  minHeight: '100vh',
  backgroundColor: theme.palette.background.default
}));

const StyledCard = styled(Card)(({ theme }) => ({
  marginBottom: theme.spacing(3),
  padding: theme.spacing(2)
}));

// 獲取特定 Cookie 的函數
function getCookie(name) {
  const value = document.cookie
    .split("; ")
    .find(row => row.startsWith(`${name}=`));
  
  if (!value) return null;
  
  try {
    const decoded = decodeURIComponent(value.split("=")[1]);
    // 嘗試解析 JSON
    return JSON.parse(decoded);
  } catch {
    // 如果不是 JSON，返回解碼後的字串
    return decodeURIComponent(value.split("=")[1]);
  }
}


export default function Customer() {
  const [customerData, setCustomerData] = useState({
    sendtasks: null,
    acct_uuid: null
  });
  const [refreshKey, setRefreshKey] = useState(0);

  // 載入客戶 Cookie 資料
  const loadCustomerData = () => {
    const sendtasks = getCookie('sendtasks');
    const acct_uuid = getCookie('acct_uuid');
    
    setCustomerData({
      sendtasks,
      acct_uuid
    });
    setRefreshKey(prev => prev + 1);
  };

  // 組件載入時讀取 Cookie
  useEffect(() => {
    loadCustomerData();
  }, []);

  // 模擬設定 cookie 的函數（用於測試）
  const setTestCookies = () => {
    const testSendtasks = ["任務A", "任務B", "任務C"];
    const testAcctUuid = "test-uuid-12345";
    
    document.cookie = `sendtasks=${encodeURIComponent(JSON.stringify(testSendtasks))}; path=/;`;
    document.cookie = `acct_uuid=${encodeURIComponent(testAcctUuid)}; path=/;`;
    
    setTimeout(loadCustomerData, 100); // 稍微延遲重新讀取
  };

  // 清除 cookie 的函數
  const clearCookies = () => {
    document.cookie = "sendtasks=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    document.cookie = "acct_uuid=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    
    setTimeout(loadCustomerData, 100);
  };

  const { sendtasks, acct_uuid } = customerData;

  return (
    <StyledContainer>
      <Typography variant="h4" gutterBottom>
        客戶 Cookie 測試頁面
      </Typography>
      
      <Box sx={{ display: 'flex', gap: 2, mb: 3, flexWrap: 'wrap' }}>
        <Button 
          variant="contained" 
          onClick={loadCustomerData}
          size="small"
        >
          重新讀取 Cookie
        </Button>
        <Button 
          variant="outlined" 
          onClick={setTestCookies}
          size="small"
          color="secondary"
        >
          設定測試 Cookie
        </Button>
        <Button 
          variant="outlined" 
          onClick={clearCookies}
          size="small"
          color="error"
        >
          清除 Cookie
        </Button>
        <Chip 
          label={`刷新次數: ${refreshKey}`} 
          color="primary" 
          variant="outlined" 
        />
      </Box>

      <Grid container spacing={3}>
        {/* 客戶帳戶 UUID */}
        <Grid item xs={12} md={6}>
          <StyledCard>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                客戶帳戶 UUID
              </Typography>
              {acct_uuid ? (
                <Box>
                  <Chip label="已設定" color="success" size="small" sx={{ mb: 2 }} />
                  <Paper 
                    variant="outlined" 
                    sx={{ 
                      p: 2, 
                      backgroundColor: '#f5f5f5',
                      fontFamily: 'monospace',
                      fontSize: '0.9rem',
                      wordBreak: 'break-all'
                    }}
                  >
                    {acct_uuid}
                  </Paper>
                </Box>
              ) : (
                <Alert severity="warning">
                  未找到 acct_uuid cookie
                </Alert>
              )}
            </CardContent>
          </StyledCard>
        </Grid>

        {/* 客戶任務列表 */}
        <Grid item xs={12} md={6}>
          <StyledCard>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                客戶任務列表 (sendtasks)
              </Typography>
              {sendtasks ? (
                <Box>
                  <Box sx={{ display: 'flex', gap: 1, mb: 2 }}>
                    <Chip label="已設定" color="success" size="small" />
                    <Chip 
                      label={`${Array.isArray(sendtasks) ? sendtasks.length : 0} 個任務`} 
                      color="info" 
                      size="small" 
                    />
                  </Box>
                  
                  {Array.isArray(sendtasks) && sendtasks.length > 0 ? (
                    <Paper variant="outlined">
                      <List dense>
                        {sendtasks.map((task, index) => (
                          <ListItem key={index}>
                            <ListItemText 
                              primary={`${index + 1}. ${task}`}
                              primaryTypographyProps={{ fontSize: '0.9rem' }}
                            />
                          </ListItem>
                        ))}
                      </List>
                    </Paper>
                  ) : (
                    <Alert severity="info">
                      任務列表為空
                    </Alert>
                  )}
                </Box>
              ) : (
                <Alert severity="warning">
                  未找到 sendtasks cookie
                </Alert>
              )}
            </CardContent>
          </StyledCard>
        </Grid>
      </Grid>

      {/* 原始 Cookie 資料 */}
      <StyledCard>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            原始 Cookie 資料
          </Typography>
          
          <TableContainer component={Paper} variant="outlined">
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><strong>Cookie 名稱</strong></TableCell>
                  <TableCell><strong>狀態</strong></TableCell>
                  <TableCell><strong>原始值</strong></TableCell>
                  <TableCell><strong>解析值</strong></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                <TableRow>
                  <TableCell>sendtasks</TableCell>
                  <TableCell>
                    <Chip 
                      label={sendtasks ? "已設定" : "未設定"} 
                      color={sendtasks ? "success" : "error"} 
                      size="small" 
                    />
                  </TableCell>
                  <TableCell>
                    <Box 
                      sx={{ 
                        maxWidth: '200px', 
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        fontSize: '0.8rem'
                      }}
                    >
                      {document.cookie.includes('sendtasks=') 
                        ? document.cookie.split('sendtasks=')[1]?.split(';')[0] || '(空)'
                        : '(未設定)'
                      }
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Box component="pre" sx={{ fontSize: '0.8rem', margin: 0 }}>
                      {sendtasks ? JSON.stringify(sendtasks, null, 2) : '(無)'}
                    </Box>
                  </TableCell>
                </TableRow>
                <TableRow>
                  <TableCell>acct_uuid</TableCell>
                  <TableCell>
                    <Chip 
                      label={acct_uuid ? "已設定" : "未設定"} 
                      color={acct_uuid ? "success" : "error"} 
                      size="small" 
                    />
                  </TableCell>
                  <TableCell>
                    <Box 
                      sx={{ 
                        maxWidth: '200px', 
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        fontSize: '0.8rem'
                      }}
                    >
                      {document.cookie.includes('acct_uuid=') 
                        ? document.cookie.split('acct_uuid=')[1]?.split(';')[0] || '(空)'
                        : '(未設定)'
                      }
                    </Box>
                  </TableCell>
                  <TableCell>
                    <Box sx={{ fontSize: '0.8rem' }}>
                      {acct_uuid || '(無)'}
                    </Box>
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </TableContainer>
        </CardContent>
      </StyledCard>

      {/* 完整的 document.cookie */}
      <StyledCard>
        <CardContent>
          <Typography variant="h6" gutterBottom>
            完整 document.cookie
          </Typography>
          <Paper 
            variant="outlined" 
            sx={{ 
              p: 2, 
              backgroundColor: '#f5f5f5',
              fontFamily: 'monospace',
              fontSize: '0.8rem',
              wordBreak: 'break-all'
            }}
          >
            {document.cookie || '(沒有 cookie)'}
          </Paper>
        </CardContent>
      </StyledCard>

      {/* 頁面資訊 */}
      <Box sx={{ mt: 3, p: 2, backgroundColor: '#f9f9f9', borderRadius: 1 }}>
        <Typography variant="caption" color="text.secondary">
          最後更新時間: {new Date().toLocaleString()} | 
          頁面位置: /app/views/customer/Customer.jsx
        </Typography>
      </Box>
    </StyledContainer>
  );
}