import {
  Avatar,
  Box,
  Badge,
  Button,
  Card,
  CardActions,
  Grid,
  Icon,
  IconButton,
  styled,
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
  // const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const { enqueueSnackbar } = useSnackbar();

  const fetchUsers = async () => {
    // setLoading(true);
    try {
      const response = await axios.get("/api/users/all");
      setUsers(response.data);
    } catch (error) {
      console.error("Failed to fetch users:", error);
      enqueueSnackbar("讀取使用者列表失敗！", { variant: "error" });
    // } finally {
      // setLoading(false);
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
                <ActionButton size="small" color="primary">
                  <Icon>edit</Icon>
                </ActionButton>
                <ActionButton size="small" color="secondary" disabled={!user.is_registered}>
                  <Icon>lock_open</Icon>
                </ActionButton>
                <ActionButton size="small" color="error" disabled={!user.is_registered}>
                  <Icon>delete</Icon>
                </ActionButton>
              </CardActions>
            </UserCard>
          </Grid>
        ))}
      </Grid>
    </Box>
  );
};

export default UserListPage;
