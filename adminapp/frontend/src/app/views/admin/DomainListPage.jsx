import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Icon,
  IconButton,
  Paper,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Typography,
  CircularProgress
} from "@mui/material";
import { useEffect, useState } from "react";
import axios from "axios";
import { useSnackbar } from "notistack";

const EMPTY_FORM = {
  id: null,
  domain: "",
  label: "",
  source_company: "",
  notes: "",
  is_active: true
};

const DomainListPage = () => {
  const { enqueueSnackbar } = useSnackbar();
  const [domains, setDomains] = useState([]);
  const [loading, setLoading] = useState(true);

  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [submitting, setSubmitting] = useState(false);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleting, setDeleting] = useState(false);

  const isEdit = form.id !== null;

  const fetchDomains = async () => {
    setLoading(true);
    try {
      const { data } = await axios.get("/api/domain/list");
      setDomains(data);
    } catch (err) {
      console.error("讀取 domain 列表失敗", err);
      enqueueSnackbar(err.response?.data?.detail || "讀取 domain 列表失敗", { variant: "error" });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDomains();
  }, []);

  const handleOpenCreate = () => {
    setForm(EMPTY_FORM);
    setEditDialogOpen(true);
  };

  const handleOpenEdit = (row) => {
    setForm({
      id: row.id,
      domain: row.domain,
      label: row.label || "",
      source_company: row.source_company || "",
      notes: row.notes || "",
      is_active: !!row.is_active
    });
    setEditDialogOpen(true);
  };

  const handleCloseDialog = () => {
    if (submitting) return;
    setEditDialogOpen(false);
  };

  const handleSubmit = async () => {
    if (!isEdit && !form.domain.trim()) {
      enqueueSnackbar("請輸入網域", { variant: "warning" });
      return;
    }
    setSubmitting(true);
    try {
      const fd = new FormData();
      if (isEdit) {
        fd.append("id", String(form.id));
        fd.append("label", form.label);
        fd.append("source_company", form.source_company);
        fd.append("notes", form.notes);
        fd.append("is_active", form.is_active ? "true" : "false");
        await axios.post("/api/domain/update", fd);
        enqueueSnackbar("更新成功", { variant: "success" });
      } else {
        fd.append("domain", form.domain.trim().toLowerCase());
        fd.append("label", form.label);
        fd.append("source_company", form.source_company);
        fd.append("notes", form.notes);
        await axios.post("/api/domain/create", fd);
        enqueueSnackbar("新增成功", { variant: "success" });
      }
      setEditDialogOpen(false);
      fetchDomains();
    } catch (err) {
      console.error(err);
      enqueueSnackbar(err.response?.data?.detail || "操作失敗", { variant: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const fd = new FormData();
      fd.append("id", String(deleteTarget.id));
      await axios.post("/api/domain/delete", fd);
      enqueueSnackbar("刪除成功", { variant: "success" });
      setDeleteTarget(null);
      fetchDomains();
    } catch (err) {
      console.error(err);
      enqueueSnackbar(err.response?.data?.detail || "刪除失敗", { variant: "error" });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <Box sx={{ p: 3 }}>
      <Box sx={{ mb: 3, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Box>
          <Typography variant="h5">Domain 管理</Typography>
          <Typography variant="body2" color="text.secondary">
            維護可綁定到觸發頁面的網域清單。新增後請確保 DNS 已指向本伺服器。
          </Typography>
        </Box>
        <Button variant="contained" color="primary" startIcon={<Icon>add</Icon>} onClick={handleOpenCreate}>
          新增 Domain
        </Button>
      </Box>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", p: 4 }}>
          <CircularProgress />
        </Box>
      ) : (
        <TableContainer component={Paper}>
          <Table>
            <TableHead>
              <TableRow>
                <TableCell>網域</TableCell>
                <TableCell>顯示名稱</TableCell>
                <TableCell>來源公司</TableCell>
                <TableCell>註記</TableCell>
                <TableCell>狀態</TableCell>
                <TableCell>建立時間</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {domains.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} align="center">
                    <Typography color="text.secondary" sx={{ py: 3 }}>
                      尚未新增任何 domain
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                domains.map((d) => (
                  <TableRow key={d.id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontFamily: "monospace" }}>
                        {d.domain}
                      </Typography>
                    </TableCell>
                    <TableCell>{d.label || "—"}</TableCell>
                    <TableCell>{d.source_company || "—"}</TableCell>
                    <TableCell sx={{ maxWidth: 240, whiteSpace: "normal" }}>
                      {d.notes || "—"}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={d.is_active ? "啟用" : "停用"}
                        size="small"
                        color={d.is_active ? "success" : "default"}
                        variant={d.is_active ? "filled" : "outlined"}
                      />
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">
                        {d.create_time ? new Date(d.create_time).toLocaleString() : "—"}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        <IconButton size="small" color="primary" onClick={() => handleOpenEdit(d)} title="編輯">
                          <Icon fontSize="small">edit</Icon>
                        </IconButton>
                        <IconButton size="small" color="error" onClick={() => setDeleteTarget(d)} title="刪除">
                          <Icon fontSize="small">delete</Icon>
                        </IconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* 新增 / 編輯 Dialog */}
      <Dialog open={editDialogOpen} onClose={handleCloseDialog} fullWidth maxWidth="sm">
        <DialogTitle>{isEdit ? "編輯 Domain" : "新增 Domain"}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <TextField
              required
              label="網域 (Hostname)"
              placeholder="例如 trigger-a.example.com"
              value={form.domain}
              onChange={(e) => setForm({ ...form, domain: e.target.value })}
              disabled={isEdit}
              helperText={isEdit ? "網域名稱不可修改 (如需更動請新增後刪除舊的)" : "純 hostname，不含 https:// 或路徑"}
              fullWidth
            />
            <TextField
              label="顯示名稱"
              placeholder="留空會自動使用網域字串"
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              fullWidth
            />
            <TextField
              label="來源公司"
              placeholder="例如：A 公司"
              value={form.source_company}
              onChange={(e) => setForm({ ...form, source_company: e.target.value })}
              fullWidth
            />
            <TextField
              label="註記"
              placeholder="取得日期、費用、聯絡人、到期日…"
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
              fullWidth
              multiline
              rows={3}
            />
            {isEdit && (
              <FormControlLabel
                control={
                  <Switch
                    checked={form.is_active}
                    onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                  />
                }
                label={form.is_active ? "啟用中 (可在建立頁面時選擇)" : "已停用 (不會出現在下拉)"}
              />
            )}
            <Alert severity="info">
              新增 domain 後請確認：1) DNS A 紀錄已指到本伺服器 IP；2) 若需 HTTPS，憑證已備妥
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog} disabled={submitting}>取消</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={submitting}
            startIcon={submitting ? <CircularProgress size={18} color="inherit" /> : null}
          >
            {isEdit ? "儲存" : "新增"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* 刪除確認 Dialog */}
      <Dialog open={!!deleteTarget} onClose={() => !deleting && setDeleteTarget(null)} maxWidth="xs">
        <DialogTitle>確認刪除</DialogTitle>
        <DialogContent>
          <Typography>
            確定刪除網域 <strong>{deleteTarget?.domain}</strong>？
          </Typography>
          <Alert severity="warning" sx={{ mt: 2 }}>
            若此 domain 仍被任何 trigger page 綁定，刪除會失敗。請先解除綁定再試。
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteTarget(null)} disabled={deleting}>取消</Button>
          <Button
            onClick={handleDelete}
            variant="contained"
            color="error"
            disabled={deleting}
            startIcon={deleting ? <CircularProgress size={18} color="inherit" /> : null}
          >
            刪除
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default DomainListPage;
