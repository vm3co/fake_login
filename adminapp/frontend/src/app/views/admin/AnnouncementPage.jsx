import {
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  Icon,
  InputAdornment,
  Switch,
  TextField,
  Typography,
  Alert,
  IconButton
} from "@mui/material";
import { useState, useEffect } from "react";
import axios from "axios";
import { useSnackbar } from "notistack";

const AnnouncementPage = () => {
  const { enqueueSnackbar } = useSnackbar();

  // 系統設定狀態
  const [maintenanceMode, setMaintenanceMode] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const [loading, setLoading] = useState(true);

  // 密碼確認 Dialog
  const [confirmDialog, setConfirmDialog] = useState({ open: false, action: null, label: "" });
  const [controlPassword, setControlPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // 編輯中的值
  const [editMaintenance, setEditMaintenance] = useState(false);
  const [editAnnouncement, setEditAnnouncement] = useState("");

  // 載入現有設定
  const fetchConfig = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/api/system/config");
      setMaintenanceMode(data.maintenance_mode);
      setAnnouncement(data.announcement || "");
      setEditMaintenance(data.maintenance_mode);
      setEditAnnouncement(data.announcement || "");
    } catch (error) {
      console.error("取得系統設定失敗:", error);
      enqueueSnackbar("取得系統設定失敗", { variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfig();
  }, []);

  // 開啟密碼確認 Dialog
  const openConfirm = (action, label) => {
    setControlPassword("");
    setShowPassword(false);
    setConfirmDialog({ open: true, action, label });
  };

  const closeConfirm = () => {
    if (submitting) return;
    setConfirmDialog({ open: false, action: null, label: "" });
  };

  // 送出設定
  const handleConfirm = async () => {
    if (!controlPassword) {
      enqueueSnackbar("請輸入控制密碼", { variant: "warning" });
      return;
    }
    setSubmitting(true);
    try {
      const payload = { control_password: controlPassword };

      if (confirmDialog.action === "maintenance") {
        payload.maintenance_mode = editMaintenance;
      } else if (confirmDialog.action === "announcement") {
        payload.announcement = editAnnouncement;
      } else if (confirmDialog.action === "both") {
        payload.maintenance_mode = editMaintenance;
        payload.announcement = editAnnouncement;
      }

      const { data } = await axios.post("/api/system/config", payload);
      enqueueSnackbar(data.message, { variant: "success" });
      closeConfirm();
      fetchConfig(); // 重新載入最新狀態
    } catch (error) {
      const detail = error.response?.data?.detail || "操作失敗，請稍後再試";
      enqueueSnackbar(detail, { variant: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", pt: 8 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 700 }}>
      <Typography variant="h5" sx={{ mb: 3 }}>
        更新公告管理
      </Typography>

      {/* 維護模式區塊 */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
            <Icon sx={{ mr: 1, color: editMaintenance ? "error.main" : "text.secondary" }}>
              {editMaintenance ? "construction" : "check_circle"}
            </Icon>
            <Typography variant="h6">維護模式</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            開啟後，所有非管理員使用者將無法登入，系統會顯示「系統更新中，請洽詢服務人員」。
          </Typography>

          {maintenanceMode && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              目前維護模式已開啟，一般使用者無法登入。
            </Alert>
          )}

          <Box sx={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <FormControlLabel
              control={
                <Switch
                  checked={editMaintenance}
                  onChange={(e) => setEditMaintenance(e.target.checked)}
                  color="error"
                />
              }
              label={
                <Typography fontWeight="medium">
                  {editMaintenance ? "維護模式：開啟" : "維護模式：關閉"}
                </Typography>
              }
            />
            <Button
              variant="contained"
              color={editMaintenance ? "error" : "success"}
              onClick={() => openConfirm("maintenance", editMaintenance ? "開啟維護模式" : "關閉維護模式")}
              disabled={editMaintenance === maintenanceMode}
              startIcon={<Icon>save</Icon>}
            >
              儲存維護模式
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* 更新公告區塊 */}
      <Card>
        <CardContent>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
            <Icon sx={{ mr: 1, color: "info.main" }}>campaign</Icon>
            <Typography variant="h6">更新公告</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            使用者登入後會彈出公告視窗，使用者可選擇「之後不再顯示」。更新公告內容後，所有使用者將再次看到新公告。
          </Typography>

          <TextField
            label="公告內容"
            multiline
            rows={6}
            fullWidth
            value={editAnnouncement}
            onChange={(e) => setEditAnnouncement(e.target.value)}
            placeholder="在此輸入公告內容（留空則不顯示公告）…"
            sx={{ mb: 2 }}
          />

          <Box sx={{ display: "flex", justifyContent: "flex-end" }}>
            <Button
              variant="contained"
              color="info"
              onClick={() => openConfirm("announcement", "更新公告內容")}
              disabled={editAnnouncement === announcement}
              startIcon={<Icon>send</Icon>}
            >
              儲存公告
            </Button>
          </Box>
        </CardContent>
      </Card>

      {/* 密碼確認 Dialog */}
      <Dialog open={confirmDialog.open} onClose={closeConfirm} maxWidth="xs" fullWidth>
        <DialogTitle>
          確認操作：{confirmDialog.label}
        </DialogTitle>
        <Divider />
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            此操作需要輸入控制密碼才能執行。
          </Typography>
          <TextField
            label="控制密碼"
            type={showPassword ? "text" : "password"}
            fullWidth
            autoFocus
            value={controlPassword}
            onChange={(e) => setControlPassword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") handleConfirm(); }}
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton onClick={() => setShowPassword((v) => !v)} size="small" edge="end">
                    <Icon>{showPassword ? "visibility_off" : "visibility"}</Icon>
                  </IconButton>
                </InputAdornment>
              )
            }}
          />
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={closeConfirm} disabled={submitting} color="inherit">
            取消
          </Button>
          <Button
            onClick={handleConfirm}
            variant="contained"
            color="primary"
            disabled={submitting}
            startIcon={submitting ? <CircularProgress size={16} color="inherit" /> : <Icon>lock_open</Icon>}
          >
            {submitting ? "執行中..." : "確認執行"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default AnnouncementPage;
