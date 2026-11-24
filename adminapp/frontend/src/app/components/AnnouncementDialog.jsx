import {
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  Icon,
  Typography
} from "@mui/material";
import { useState } from "react";
import useAuth from "app/hooks/useAuth";

/**
 * 系統更新公告彈窗
 * 登入後若有未被忽略的公告，自動顯示。
 * 使用者可選擇「之後不再顯示」來永久略過此版本的公告。
 */
const AnnouncementDialog = () => {
  const { announcement, announcementVisible, dismissAnnouncement } = useAuth();
  const [neverShow, setNeverShow] = useState(false);

  if (!announcementVisible || !announcement) return null;

  const handleClose = () => {
    dismissAnnouncement(neverShow);
    setNeverShow(false);
  };

  return (
    <Dialog
      open={announcementVisible}
      onClose={handleClose}
      maxWidth="sm"
      fullWidth
      disableEscapeKeyDown={false}
    >
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <Icon color="info">campaign</Icon>
        系統公告
      </DialogTitle>
      <Divider />
      <DialogContent>
        <Typography
          variant="body1"
          sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}
        >
          {announcement}
        </Typography>
      </DialogContent>
      <Divider />
      <DialogActions sx={{ px: 3, py: 1.5, justifyContent: "space-between" }}>
        <FormControlLabel
          control={
            <Checkbox
              size="small"
              checked={neverShow}
              onChange={(e) => setNeverShow(e.target.checked)}
            />
          }
          label={
            <Typography variant="body2" color="text.secondary">
              之後不再顯示
            </Typography>
          }
        />
        <Button variant="contained" onClick={handleClose} startIcon={<Icon>check</Icon>}>
          我知道了
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default AnnouncementDialog;
