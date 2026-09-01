import { Fragment, useCallback, useEffect, useState } from "react";
// import { Link } from "react-router-dom";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Badge from "@mui/material/Badge";
import Button from "@mui/material/Button";
import Drawer from "@mui/material/Drawer";
import styled from "@mui/material/styles/styled";
import IconButton from "@mui/material/IconButton";
import ThemeProvider from "@mui/material/styles/ThemeProvider";
import Notifications from "@mui/icons-material/Notifications";
import Refresh from "@mui/icons-material/Refresh";
import {
  Chip,
  CircularProgress,
  Tab,
  Tabs,
  Typography
} from "@mui/material";
import axios from "axios";

import useAuth from "app/hooks/useAuth";
import useSettings from "app/hooks/useSettings";
import { topBarHeight } from "app/utils/constant";
import { themeShadows } from "../MatxTheme/themeColors";

const Notification = styled("div")(() => ({
  padding: "16px",
  marginBottom: "16px",
  display: "flex",
  alignItems: "center",
  height: topBarHeight,
  boxShadow: themeShadows[6],
  "& h5": {
    marginLeft: "8px",
    marginTop: 0,
    marginBottom: 0,
    fontWeight: "500"
  }
}));

const STATUS_META = {
  pending: { label: "等待中", color: "warning" },
  running: { label: "執行中", color: "info" },
  completed: { label: "已完成", color: "success" },
  partial: { label: "部分完成", color: "warning" },
  failed: { label: "失敗", color: "error" },
  cancelled: { label: "已取消", color: "default" }
};

const formatTaipeiTime = (value) => value
  ? new Date(value).toLocaleString("zh-TW", { timeZone: "Asia/Taipei" })
  : "--";

const TaskResultList = ({ title, tasks, color }) => {
  if (!tasks?.length) return null;

  return (
    <Box sx={{ mt: 1 }}>
      <Typography variant="caption" color={color} display="block">
        {title}
      </Typography>
      {tasks.map((task) => (
        <Typography key={task.sendtask_uuid} variant="caption" display="block" sx={{ pl: 1 }}>
          {task.sendtask_id}{task.reason ? ` (${task.reason})` : ""}
        </Typography>
      ))}
    </Box>
  );
};

export default function NotificationBar({ container }) {
  const { settings } = useSettings();
  const { user } = useAuth();
  const [panelOpen, setPanelOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("manual");
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState("");

  const handleDrawerToggle = () => setPanelOpen((open) => !open);

  const fetchJobs = useCallback(async (showLoading = false) => {
    if (showLoading) setJobsLoading(true);
    setJobsError("");
    try {
      const response = await axios.get("/api/jobs", {
        params: { source: activeTab === "manual" ? "manual" : "scheduler" }
      });
      setJobs(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error("Error fetching jobs:", error);
      setJobsError(error.response?.data?.detail || "無法載入任務紀錄");
    } finally {
      if (showLoading) setJobsLoading(false);
    }
  }, [activeTab]);

  useEffect(() => {
    if (!panelOpen) return undefined;

    fetchJobs(true);
    const intervalId = window.setInterval(() => fetchJobs(false), 2000);
    return () => window.clearInterval(intervalId);
  }, [panelOpen, activeTab, fetchJobs]);

  const cancelJob = async (jobId) => {
    try {
      await axios.post(`/api/jobs/${jobId}/cancel`);
      fetchJobs(false);
    } catch (error) {
      setJobsError(error.response?.data?.detail || "無法取消任務");
    }
  };

  const activeManualCount = jobs.filter((job) => ["pending", "running"].includes(job.status)).length;

  return (
    <Fragment>
      <IconButton onClick={handleDrawerToggle}>
        <Badge color="secondary" badgeContent={activeManualCount}>
          <Notifications sx={{ color: "text.primary" }} />
        </Badge>
      </IconButton>

      <ThemeProvider theme={settings.themes[settings.activeTheme]}>
        <Drawer
          width={"100px"}
          container={container}
          variant="temporary"
          anchor={"right"}
          open={panelOpen}
          onClose={handleDrawerToggle}
          ModalProps={{ keepMounted: true }}>
          <Box sx={{ width: { xs: "100vw", sm: 420 }, maxWidth: "100vw" }}>
            <Notification>
              <Notifications color="primary" />
              <h5>更新任務</h5>
            </Notification>

            <Tabs
              value={activeTab}
              onChange={(_, value) => setActiveTab(value)}
              variant="fullWidth"
              sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
              <Tab value="manual" label="手動更新" />
              <Tab value="scheduler" label="系統排程" />
            </Tabs>
            {
              <Box px={2} pb={3}>
                <Box display="flex" alignItems="center" justifyContent="space-between" mb={1.5}>
                  <Typography variant="body2" color="text.secondary">
                    執行中與最近 100 筆紀錄
                  </Typography>
                  <IconButton size="small" onClick={() => fetchJobs(true)} title="重新整理">
                    <Refresh fontSize="small" />
                  </IconButton>
                </Box>

                {jobsLoading && !jobs.length && (
                  <Box display="flex" justifyContent="center" py={5}>
                    <CircularProgress size={28} />
                  </Box>
                )}

                {jobsError && (
                  <Typography color="error" variant="body2" py={2}>
                    {jobsError}
                  </Typography>
                )}

                {!jobsLoading && !jobsError && !jobs.length && (
                  <Typography color="text.secondary" textAlign="center" py={5}>
                    尚無任務紀錄
                  </Typography>
                )}

                {jobs.map((job) => {
                  const status = STATUS_META[job.status] || { label: job.status, color: "default" };
                  const isRunning = ["pending", "running"].includes(job.status);
                  return (
                    <Card key={job.job_id} variant="outlined" sx={{ mb: 1.5 }}>
                      <Box p={1.75}>
                        <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
                          <Typography variant="subtitle2">{job.display_name || job.type}</Typography>
                          <Chip
                            size="small"
                            label={status.label}
                            color={status.color}
                            icon={isRunning ? <CircularProgress size={12} /> : undefined}
                          />
                        </Box>
                        {activeTab === "manual" && user?.admin_role === true && (
                          <Typography variant="caption" color="text.secondary" display="block" mt={0.75}>
                            啟動者：{job.owner_username}
                          </Typography>
                        )}
                        {activeTab === "manual" && isRunning && (
                          <Button
                            color="error"
                            size="small"
                            variant="outlined"
                            sx={{ mt: 1 }}
                            onClick={() => cancelJob(job.job_id)}>
                            取消更新
                          </Button>
                        )}
                        {activeTab === "manual" && job.items?.length > 0 && (
                          <TaskResultList
                            title={isRunning ? "正在更新任務" : "任務項目"}
                            tasks={job.items}
                            color={isRunning ? "info.main" : "text.secondary"}
                          />
                        )}
                        <Typography variant="caption" color="text.secondary" display="block" mt={0.5}>
                          開始：{formatTaipeiTime(job.start_time)}
                        </Typography>
                        {job.finished_at && (
                          <Typography variant="caption" color="text.secondary" display="block">
                            完成：{formatTaipeiTime(job.finished_at)}
                          </Typography>
                        )}
                        {job.error && (
                          <Typography variant="body2" color="error" sx={{ mt: 1, whiteSpace: "pre-wrap" }}>
                            {job.error}
                          </Typography>
                        )}
                        {job.type === "更新任務統計" && job.result ? (
                          <>
                            <TaskResultList
                              title="已更新任務"
                              tasks={job.result.successful_tasks}
                              color="success.main"
                            />
                            <TaskResultList
                              title="跳過任務"
                              tasks={job.result.skipped_tasks}
                              color="warning.main"
                            />
                            <TaskResultList
                              title="更新失敗任務"
                              tasks={job.result.failed_tasks}
                              color="error.main"
                            />
                          </>
                        ) : job.result && (
                          <Typography
                            component="pre"
                            variant="caption"
                            sx={{ mt: 1, mb: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                            {JSON.stringify(job.result, null, 2)}
                          </Typography>
                        )}
                      </Box>
                    </Card>
                  );
                })}
              </Box>
            }
          </Box>
        </Drawer>
      </ThemeProvider>
    </Fragment>
  );
}
