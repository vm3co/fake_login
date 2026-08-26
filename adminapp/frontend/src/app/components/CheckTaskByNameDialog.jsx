import { useState } from "react";
import { useSnackbar } from "notistack";
import axios from "axios";
import Dialog from "@mui/material/Dialog";
import DialogTitle from "@mui/material/DialogTitle";
import DialogContent from "@mui/material/DialogContent";
import DialogActions from "@mui/material/DialogActions";
import Divider from "@mui/material/Divider";
import Box from "@mui/material/Box";
import TextField from "@mui/material/TextField";
import Button from "@mui/material/Button";
import Table from "@mui/material/Table";
import TableHead from "@mui/material/TableHead";
import TableBody from "@mui/material/TableBody";
import TableRow from "@mui/material/TableRow";
import TableCell from "@mui/material/TableCell";
import Checkbox from "@mui/material/Checkbox";
import CircularProgress from "@mui/material/CircularProgress";
import Typography from "@mui/material/Typography";
import Icon from "@mui/material/Icon";
import Chip from "@mui/material/Chip";
import ThemeProvider from "@mui/material/styles/ThemeProvider";

import useSettings from "app/hooks/useSettings";
import formatDate from "app/utils/formatDate";

const CheckTaskByNameDialog = ({ open, onClose }) => {
  const { enqueueSnackbar } = useSnackbar();
  const { settings } = useSettings();
  const pageTheme = settings.themes[settings.activeTheme];
  const [keyword, setKeyword] = useState("");
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [results, setResults] = useState([]);
  const [selectedUuids, setSelectedUuids] = useState([]);
  const [submitting, setSubmitting] = useState(false);

  const resetState = () => {
    setKeyword("");
    setSearching(false);
    setHasSearched(false);
    setResults([]);
    setSelectedUuids([]);
    setSubmitting(false);
  };

  const handleClose = () => {
    if (submitting) return;
    resetState();
    onClose();
  };

  const handleDialogClose = (event, reason) => {
    if (reason === "backdropClick") return;
    handleClose();
  };

  const handleSearch = async () => {
    const trimmed = keyword.trim();
    if (!trimmed) {
      enqueueSnackbar("請輸入任務名稱關鍵字", { variant: "warning" });
      return;
    }
    setSearching(true);
    setSelectedUuids([]);
    try {
      const { data } = await axios.post("/api/search_sendtasks_by_name", {
        keyword: trimmed
      });
      if (data.status === "success") {
        setResults(data.data || []);
      } else {
        enqueueSnackbar(data.message || "查詢失敗", { variant: "error" });
        setResults([]);
      }
    } catch (error) {
      const detail = error.response?.data?.message || "查詢失敗，請稍後再試";
      enqueueSnackbar(detail, { variant: "error" });
      setResults([]);
    } finally {
      setSearching(false);
      setHasSearched(true);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSearch();
    }
  };

  const allSelected = results.length > 0 && results.every((row) => selectedUuids.includes(row.sendtask_uuid));
  const someSelected = results.some((row) => selectedUuids.includes(row.sendtask_uuid));

  const handleToggleAll = (e) => {
    if (e.target.checked) {
      setSelectedUuids(results.map((row) => row.sendtask_uuid));
    } else {
      setSelectedUuids([]);
    }
  };

  const handleToggleRow = (uuid) => (e) => {
    if (e.target.checked) {
      setSelectedUuids([...selectedUuids, uuid]);
    } else {
      setSelectedUuids(selectedUuids.filter((id) => id !== uuid));
    }
  };

  const handleUpdateSelected = async () => {
    if (selectedUuids.length === 0) return;
    setSubmitting(true);
    try {
      const { data } = await axios.post("/api/upsert_selected_sendtasks", {
        sendtask_uuids: selectedUuids
      });
      if (data.status === "success") {
        const updatedCount = data.data?.upserted?.length || 0;
        enqueueSnackbar(`已更新 ${updatedCount} 筆任務`, { variant: "success" });
        setSelectedUuids([]);
      } else {
        enqueueSnackbar(data.message || "更新失敗", { variant: "error" });
      }
    } catch (error) {
      const detail = error.response?.data?.message || "更新失敗，請稍後再試";
      enqueueSnackbar(detail, { variant: "error" });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ThemeProvider theme={pageTheme}>
      <Dialog open={open} onClose={handleDialogClose} maxWidth="md" fullWidth>
        <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
          <Icon color="primary">search</Icon>
          依名稱更新任務
        </DialogTitle>
        <Divider />
        <DialogContent>
          <Box display="flex" gap={1} alignItems="center" mt={1} mb={2}>
            <TextField
              fullWidth
              size="small"
              label="任務名稱關鍵字"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={searching}
            />
            <Button variant="contained" onClick={handleSearch} disabled={searching} sx={{ minWidth: 96 }}>
              {searching ? <CircularProgress size={20} color="inherit" /> : "搜尋"}
            </Button>
          </Box>

          {searching && (
            <Box display="flex" alignItems="center" justifyContent="center" minHeight="150px">
              <CircularProgress />
              <Typography sx={{ ml: 2 }}>搜尋中...</Typography>
            </Box>
          )}

          {!searching && hasSearched && results.length === 0 && (
            <Typography color="text.secondary" sx={{ py: 4, textAlign: "center" }}>
              查無符合「{keyword}」的任務
            </Typography>
          )}

          {!searching && results.length > 0 && (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell padding="checkbox" sx={{ width: 64, pr: 3 }}>
                    <Checkbox
                      checked={allSelected}
                      indeterminate={someSelected && !allSelected}
                      onChange={handleToggleAll}
                    />
                  </TableCell>
                  <TableCell sx={{ pl: 3 }}>任務名稱</TableCell>
                  <TableCell>建立時間</TableCell>
                  <TableCell>本地狀態</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {results.map((row) => (
                  <TableRow key={row.sendtask_uuid} hover>
                    <TableCell padding="checkbox" sx={{ width: 64, pr: 3 }}>
                      <Checkbox
                        checked={selectedUuids.includes(row.sendtask_uuid)}
                        onChange={handleToggleRow(row.sendtask_uuid)}
                      />
                    </TableCell>
                    <TableCell sx={{ pl: 3 }}>{row.sendtask_id}</TableCell>
                    <TableCell>{formatDate(row.sendtask_create_ut, "datetime")}</TableCell>
                    <TableCell>
                      {row.exists_locally ? (
                        <Chip label="已存在" color="success" size="small" />
                      ) : (
                        <Chip label="尚未建立" variant="outlined" size="small" />
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </DialogContent>
        <Divider />
        <DialogActions sx={{ px: 3, py: 1.5, justifyContent: "space-between" }}>
          <Typography variant="body2" color="text.secondary">
            {selectedUuids.length > 0 ? `已勾選 ${selectedUuids.length} 筆任務` : ""}
          </Typography>
          <Box display="flex" gap={1}>
            <Button onClick={handleClose} disabled={submitting}>
              關閉
            </Button>
            <Button
              variant="contained"
              onClick={handleUpdateSelected}
              disabled={selectedUuids.length === 0 || submitting}
              startIcon={submitting ? <CircularProgress size={16} color="inherit" /> : null}
            >
              更新所選任務
            </Button>
          </Box>
        </DialogActions>
      </Dialog>
    </ThemeProvider>
  );
};

export default CheckTaskByNameDialog;
