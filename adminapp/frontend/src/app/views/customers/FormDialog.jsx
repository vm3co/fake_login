import { useState, forwardRef } from "react";
import AppBar from "@mui/material/AppBar";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import TextField from "@mui/material/TextField";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogContentText from "@mui/material/DialogContentText";
import Fab from "@mui/material/Fab";
import Icon from "@mui/material/Icon";
import Box from "@mui/material/Box";
import Slide from "@mui/material/Slide";
import Toolbar from "@mui/material/Toolbar";
import IconButton from "@mui/material/IconButton";
import CloseIcon from "@mui/icons-material/Close";
import CircularProgress from "@mui/material/CircularProgress";

import useCustomers from 'app/hooks/useCustomers';
import CustomersContext from "app/contexts/CustomersContext";


const Transition = forwardRef(function Transition(props, ref) {
  return <Slide direction="up" ref={ref} {...props} />;
});

export default function FormDialog() {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState({
    customername: "",
    customerfullname: "",
    password: "",
    confirmPassword: ""
  });
  const [errors, setErrors] = useState({});
  // 使用 useCustomers hook
  const { 
    loading, 
    createCustomer, 
    clearMessages,
  } = useCustomers(CustomersContext);

  const handleClickOpen = () => setOpen(true);
  const handleClose = () => setOpen(false);

  const handleSubmit = async (event) => {
    event.preventDefault(); // 防止表單預設提交行為
    
    // 基本驗證
    const newErrors = {};
    
    if (!customername.trim()) {
      newErrors.customername = '請輸入客戶名稱';
    }
    
    if (!password.trim()) {
      newErrors.password = '請輸入密碼';
    }
    
    if (password !== confirmPassword) {
      newErrors.confirmPassword = '密碼確認不一致';
    }
    
    if (!customerfullname.trim()) {
      newErrors.customerfullname = '請輸入客戶全名';
    }
    
    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }
    
    try {
      await createCustomer(state);
      
      // 成功後清空表單並關閉對話框
      setState({
        customername: "",
        customerfullname: "",
        password: "",
        confirmPassword: ""
      });
      setErrors({});
      setOpen(false);
      clearMessages(); 
      
    } catch (error) {
      console.error("創建客戶失敗:", error); // 調試：檢查完整錯誤
      setErrors({ api: error.message || "創建客戶失敗，請稍後再試" });
    }
  };

  const handleCancel = () => {
    // 清空表單並關閉對話框
    setState({
      customername: "",
      customerfullname: "",
      password: "",
      confirmPassword: ""
    });
    setErrors({});
    clearMessages();
    handleClose();
    setOpen(false);
  };

  const handleChange = (event) => {
    event.persist();
    const { name, value } = event.target;
    
    if (name === 'customername') {
      // 直接過濾掉非法字符，保留合法字符
      const filteredValue = value.replace(/[^A-Za-z0-9_]/g, '');
      
      // 如果過濾後的值與原值不同，表示有非法字符
      if (filteredValue !== value) {
        setErrors({ ...errors, customername: '僅能輸入英文字母、數字和_ ' });
      } else {
        // 清除錯誤訊息
        const newErrors = { ...errors };
        delete newErrors.customername;
        setErrors(newErrors);
      }
      
      // 總是使用過濾後的值
      setState({ ...state, [name]: filteredValue });
    } else {
      setState({ ...state, [name]: value });
    }
  };

  const { customername, customerfullname, password, confirmPassword } =
    state;

  return (
    <div>
      <Box display="flex" justifyContent="flex-end" alignItems="center" gap={1}>
        <Fab size="medium" color="secondary" aria-label="Add" className="button" onClick={handleClickOpen}>
          <Icon>add user</Icon>
        </Fab>
        <h3>新增帳號</h3>
      </Box>

      <Dialog open={open} onClose={handleClose} TransitionComponent={Transition}>
        <AppBar sx={{ position: "relative" }}>
          <Toolbar>
            <IconButton edge="start" color="inherit" onClick={handleClose} aria-label="Close">
              <CloseIcon />
            </IconButton>
          </Toolbar>
        </AppBar>

        <form onSubmit={handleSubmit}>

          <DialogTitle id="form-dialog-title">新增帳號</DialogTitle>

          <DialogContent>
            {/* {error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                {error}
              </Alert>
            )}
            {success && (
              <Alert severity="success" sx={{ mb: 2 }}>
                {success}
              </Alert>
            )} */}
            <DialogContentText>
              提供給客戶使用的帳號
            </DialogContentText>
            <br />
            <TextField
              sx={{ mb: 2 }}
              fullWidth
              type="text"
              name="customername"
              value={customername}
              onChange={handleChange}
              label="Customer Name"
              error={!!errors.customername}
              helperText={errors.customername || "僅能輸入英文字母、數字和_ "}
              inputProps={{
                pattern: "[A-Za-z0-9_]*" // HTML5 pattern 作為額外保障
              }}
            />
            <TextField
              sx={{ mb: 1 }}
              fullWidth
              name="password"
              type="password"
              label="Password"
              value={password}
              onChange={handleChange}
              error={!!errors.password}
              helperText={errors.password}
            />
            <TextField
              sx={{ mb: 1 }}
              fullWidth
              type="password"
              name="confirmPassword"
              onChange={handleChange}
              label="Confirm Password"
              value={confirmPassword}
              error={!!errors.confirmPassword}
              helperText={errors.confirmPassword}
            />
            <TextField
              sx={{ mb: 1 }}
              fullWidth
              type="text"
              name="customerfullname"
              value={customerfullname}
              onChange={handleChange}
              label="Customer Full Name"
              error={!!errors.customerfullname}
              helperText={errors.customerfullname}
            />
          </DialogContent>

          <Box display="flex" justifyContent="center" alignItems="center" gap={1} sx={{ mb: 1 }}>
            <Button 
              variant="contained" 
              type="submit"
              color="primary"
              disabled={loading}
              startIcon={loading ? <CircularProgress size={20} /> : null}
            >
              {loading ? '創建中...' : '新增'}
            </Button>
          </Box>
        </form>
        <Box display="flex" justifyContent="center" alignItems="center" gap={1} sx={{ mb: 1 }}>
          <Button variant="outlined" color="secondary" onClick={handleCancel}>
            取消
          </Button>
        </Box>
      </Dialog>
    </div>
  );
}
