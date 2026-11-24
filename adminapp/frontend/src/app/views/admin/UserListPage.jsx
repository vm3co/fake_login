import {
  Avatar,
  Box,
  Badge,
  Button,
  Card,
  CardActions,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Grid,
  Icon,
  IconButton,
  InputAdornment,
  styled,
  TextField,
  Typography,
  CircularProgress
} from "@mui/material";
import { useEffect, useState } from "react";
import axios from "axios";
import { useSnackbar } from "notistack";

const UserCard = styled(Card)(({ theme }) => ({
  textAlign: "center",
  padding: theme.spacing(3)
}));

const UserAvatar = styled(Avatar)(({ theme }) => ({
  width: 80,
  height: 80,
  margin: "0 auto",
  marginBottom: theme.spacing(2)
}));

const StyledBadge = styled(Badge)(({ theme }) => ({
  "& .MuiBadge-badge": {
    border: `2px solid ${theme.palette.background.paper}`,
    padding: "0 4px"
  }
}));

const ActionButton = styled(IconButton)(({ theme }) => ({
  padding: theme.spacing(0.5)
}));

const UserListPage = () => {
  const [users, setUsers] = useState([]);
  const [syncing, setSyncing] = useState(false);
  const { enqueueSnackbar } = useSnackbar();

  // --- 密碼重設 Dialog 狀態 ---
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState(null);
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [passwordError, setPasswordError] = useState("");

  const fetchUsers = async () => {
    try {
      const response = await axios.get("/api/users/all");
      setUsers(response.data);
    } catch (error) {
      console.error("Failed to fetch users:", error);
      enqueueSnackbar("讀取使用者列表失敗！", { variant: "error" });
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const response = await axios.post("/api/users/sync-accts");
      enqueueSnackbar(response.data.message, { variant: "success" });
      fetchUsers(); // 同步後重新載入資料
    } catch (error) {
      console.error("Failed to sync accounts:", error);
      enqueueSnackbar(error.response?.data?.detail || "同步主系統帳號失敗！", { variant: "error" });
    } finally {
      setSyncing(false);
    }
  };

  // 開啟密碼重設 Dialog
  const handleOpenPasswordDialog = (user) => {
    setSelectedUser(user);
    setNewPassword("");
    setConfirmPassword("");
    setShowNewPassword(false);
    setShowConfirmPassword(false);
    setPasswordError("");
    setPasswordDialogOpen(true);
  };

  // 關閉 Dialog
  const handleClosePasswordDialog = () => {
    if (resetting) return; // 送出中不允許關閉
    setPasswordDialogOpen(false);
    setSelectedUser(null);
  };

  // 驗證密碼輸入
  const validatePasswords = () => {
    if (!newPassword) {
      setPasswordError("請輸入新密碼");
      return false;
    }
    if (newPassword.length < 4) {
      setPasswordError("密碼長度至少需要 4 個字元");
      return false;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("兩次輸入的密碼不一致");
      return false;
    }
    setPasswordError("");
    return true;
  };

  // 送出密碼重設
  const handleResetPassword = async () => {
    if (!validatePasswords()) return;

    setResetting(true);
    try {
      await axios.post("/api/users/reset-password", {
        acct_uuid: selectedUser.acct_uuid,
        new_password: newPassword
      });
      enqueueSnackbar(`已成功重設 ${selectedUser.acct_full_name} 的密碼`, { variant: "success" });
      setPasswordDialogOpen(false);
    } catch (error) {
      console.error("Failed to reset password:", error);
      const detail = error.response?.data?.detail || "密碼重設失敗，請稍後再試";
      enqueueSnackbar(detail, { variant: "error" });
    } finally {
      setResetting(false);
    }
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ mb: 3, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="h5">使用者列表</Typography>
        <Button variant="contained" color="secondary" onClick={handleSync} disabled={syncing} startIcon={syncing ? <CircularProgress size={20} color="inherit" /> : <Icon>sync</Icon>}>
          {syncing ? "同步中..." : "同步主系統帳號"}
        </Button>
      </Box>

      <Grid container spacing={3}>
        {users.map((user) => (
          <Grid item xs={12} sm={6} md={4} key={user.acct_uuid}>
            <UserCard>
              <StyledBadge
                overlap="circular"
                anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                variant="dot"
                color={user.is_registered ? "success" : "default"}
              >
                <UserAvatar src={`/assets/images/avatars/00${(user.acct_id.charCodeAt(0) % 5) + 1}-man.svg`} />
              </StyledBadge>

              <Typography variant="h6">{user.acct_full_name}</Typography>
              <Typography color="text.secondary">{user.acct_email}</Typography>
              <Typography color="text.secondary">{user.orgs}</Typography>
              <Typography variant="body2" sx={{ mt: 1, mb: 2 }}>
                {user.is_registered ? "已註冊" : "尚未註冊"}
              </Typography>
              <CardActions sx={{ justifyContent: "center" }}>
                {/* <ActionButton size="small" color="primary">
                  <Icon>edit</Icon>
                </ActionButton> */}
                <ActionButton
                  size="small"
                  color="secondary"
                  disabled={!user.is_registered}
                  onClick={() => handleOpenPasswordDialog(user)}
                  title="重設密碼"
                >
                  <Icon>lock_reset</Icon>
                </ActionButton>
                {/* <ActionButton size="small" color="error" disabled={!user.is_registered}>
                  <Icon>delete</Icon>
                </ActionButton> */}
              </CardActions>
            </UserCard>
          </Grid>
        ))}
      </Grid>

      {/* 密碼重設 Dialog */}
      <Dialog
        open={passwordDialogOpen}
        onClose={handleClosePasswordDialog}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          重設密碼
          {selectedUser && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              使用者：{selectedUser.acct_full_name}
            </Typography>
          )}
        </DialogTitle>
        <DialogContent>
          <TextField
            label="新密碼"
            type={showNewPassword ? "text" : "password"}
            fullWidth
            margin="normal"
            value={newPassword}
            onChange={(e) => {
              setNewPassword(e.target.value);
              setPasswordError("");
            }}
            error={!!passwordError && !newPassword}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => setShowNewPassword((v) => !v)} edge="end" size="small">
                    <Icon>{showNewPassword ? "visibility_off" : "visibility"}</Icon>
                  </IconButton>
                </InputAdornment>
              )
            }}
          />
          <TextField
            label="確認新密碼"
            type={showConfirmPassword ? "text" : "password"}
            fullWidth
            margin="normal"
            value={confirmPassword}
            onChange={(e) => {
              setConfirmPassword(e.target.value);
              setPasswordError("");
            }}
            error={!!passwordError}
            helperText={passwordError}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => setShowConfirmPassword((v) => !v)} edge="end" size="small">
                    <Icon>{showConfirmPassword ? "visibility_off" : "visibility"}</Icon>
                  </IconButton>
                </InputAdornment>
              )
            }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={handleClosePasswordDialog} disabled={resetting} color="inherit">
            取消
          </Button>
          <Button
            onClick={handleResetPassword}
            variant="contained"
            color="secondary"
            disabled={resetting}
            startIcon={resetting ? <CircularProgress size={16} color="inherit" /> : <Icon>lock_reset</Icon>}
          >
            {resetting ? "重設中..." : "確認重設"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default UserListPage;
