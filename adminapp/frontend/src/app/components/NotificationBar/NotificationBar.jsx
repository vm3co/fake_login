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
import Error from "@mui/icons-material/Error";
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
import { useJob } from "app/contexts/JobContext";
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
  queued: { label: "排隊中", color: "warning" },
  claiming: { label: "準備執行", color: "info" },
  pending: { label: "等待中", color: "warning" },
  running: { label: "執行中", color: "info" },
  cancel_requested: { label: "正在取消", color: "warning" },
  completed: { label: "已完成", color: "success" },
  partial: { label: "部分完成", color: "warning" },
  failed: { label: "失敗", color: "error" },
  cancelled: { label: "已取消", color: "default" },
  interrupted: { label: "已中斷", color: "error" }
};

const ITEM_STATUS_META = {
  pending: { label: "等待中", color: "warning" },
  running: { label: "更新中", color: "info" },
  completed: { label: "完成", color: "success" },
  skipped: { label: "已排除", color: "default" },
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

const TaskItemList = ({ title, tasks, color }) => {
  if (!tasks?.length) return null;

  return (
    <Box sx={{ mt: 1.25 }}>
      <Typography variant="caption" color={color} fontWeight={600} display="block" mb={0.5}>
        {title}
      </Typography>
      {tasks.map((task) => {
        const itemStatus = ITEM_STATUS_META[task.status] || { label: task.status, color: "default" };
        return (
          <Box key={task.sendtask_uuid} display="flex" alignItems="center" justifyContent="space-between" gap={1} py={0.35}>
            <Typography variant="caption" sx={{ minWidth: 0, overflowWrap: "anywhere" }}>
              {task.sendtask_id}
            </Typography>
            <Chip size="small" variant="outlined" label={itemStatus.label} color={itemStatus.color} />
          </Box>
        );
      })}
    </Box>
  );
};

export default function NotificationBar({ container }) {
  const { settings } = useSettings();
  const { user } = useAuth();
  const {
    manualJobs,
    activeCount,
    unseenCompletedCount,
    hasUnseenFailure,
    jobsLoading: manualJobsLoading,
    refreshManualJobs,
    markManualJobsSeen,
  } = useJob();
  const [panelOpen, setPanelOpen] = useState(false);
  const [activeTab, setActiveTab] = useState("manual");
  const [schedulerJobs, setSchedulerJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState("");

  const handleDrawerToggle = () => setPanelOpen((open) => !open);

  const fetchJobs = useCallback(async (showLoading = false) => {
    if (activeTab === "manual") {
      return refreshManualJobs({ silent: !showLoading });
    }
    if (showLoading) setJobsLoading(true);
    setJobsError("");
    try {
      const response = await axios.get("/api/jobs", {
        params: { source: activeTab === "manual" ? "manual" : "scheduler" }
      });
      setSchedulerJobs(Array.isArray(response.data) ? response.data : []);
    } catch (error) {
      console.error("Error fetching jobs:", error);
      setJobsError(error.response?.data?.detail || "無法載入任務紀錄");
    } finally {
      if (showLoading) setJobsLoading(false);
    }
  }, [activeTab, refreshManualJobs]);

  useEffect(() => {
    if (!panelOpen) return undefined;

    fetchJobs(true);
    if (activeTab === "manual") markManualJobsSeen();
    if (activeTab === "scheduler") {
      const intervalId = window.setInterval(() => fetchJobs(false), 5000);
      return () => window.clearInterval(intervalId);
    }
    return undefined;
  }, [panelOpen, activeTab, fetchJobs, markManualJobsSeen]);

  const cancelJob = async (jobId) => {
    try {
      await axios.post(`/api/jobs/${jobId}/cancel`);
      fetchJobs(false);
    } catch (error) {
      setJobsError(error.response?.data?.detail || "無法取消任務");
    }
  };

  const jobs = activeTab === "manual" ? manualJobs : schedulerJobs;
  const displayLoading = activeTab === "manual" ? manualJobsLoading : jobsLoading;

  return (
    <Fragment>
      <IconButton onClick={handleDrawerToggle}>
        <Box sx={{ position: "relative", display: "inline-flex" }}>
          <Badge
            color={hasUnseenFailure ? "error" : "success"}
            badgeContent={hasUnseenFailure ? <Error sx={{ fontSize: 14 }} /> : unseenCompletedCount}
            invisible={!hasUnseenFailure && unseenCompletedCount === 0}>
            <Notifications sx={{ color: "text.primary" }} />
          </Badge>
          {activeCount > 0 && (
            <CircularProgress
              size={13}
              thickness={6}
              sx={{ position: "absolute", right: -5, bottom: -4, color: "info.main", bgcolor: "background.paper", borderRadius: "50%" }}
            />
          )}
        </Box>
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

                {displayLoading && !jobs.length && (
                  <Box display="flex" justifyContent="center" py={5}>
                    <CircularProgress size={28} />
                  </Box>
                )}

                {jobsError && (
                  <Typography color="error" variant="body2" py={2}>
                    {jobsError}
                  </Typography>
                )}

                {!displayLoading && !jobsError && !jobs.length && (
                  <Typography color="text.secondary" textAlign="center" py={5}>
                    尚無任務紀錄
                  </Typography>
                )}

                {jobs.map((job) => {
                  const status = STATUS_META[job.status] || { label: job.status, color: "default" };
                  const isRunning = ["claiming", "running"].includes(job.status);
                  const isActive = ["queued", "claiming", "running", "cancel_requested"].includes(job.status);
                  const duplicateItems = job.items?.filter((item) => item.reason === "duplicate_active") || [];
                  const failedItems = job.items?.filter((item) => item.status === "failed") || [];
                  const activeItems = job.items?.filter((item) => !["skipped", "failed"].includes(item.status)) || [];
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
                        {job.blocked_by_display_name && (
                          <Typography variant="caption" color="warning.main" display="block" mt={0.75}>
                            系統正在等待或執行「{job.blocked_by_display_name}」，此任務排隊中
                          </Typography>
                        )}
                        {activeTab === "manual" && job.requested_count > 0 && (
                          <Box display="flex" flexWrap="wrap" gap={0.75} mt={1}>
                            <Chip size="small" label={`要求更新 ${job.requested_count} 筆`} />
                            <Chip size="small" color="info" variant="outlined" label={`實際執行 ${job.accepted_count} 筆`} />
                            {job.excluded_count > 0 && (
                              <Chip size="small" color="warning" variant="outlined" label={`重複排除 ${job.excluded_count} 筆`} />
                            )}
                          </Box>
                        )}
                        {activeTab === "manual" && isActive && job.owner_username === user?.name && job.status !== "cancel_requested" && (
                          <Button
                            color="error"
                            size="small"
                            variant="outlined"
                            sx={{ mt: 1 }}
                            onClick={() => cancelJob(job.job_id)}>
                            取消更新
                          </Button>
                        )}
                        {activeTab === "manual" && isActive && (
                          <>
                            <TaskItemList title="等待／正在更新" tasks={activeItems} color="info.main" />
                            <TaskItemList title="已排除重複" tasks={duplicateItems} color="warning.main" />
                            <TaskItemList title="更新失敗" tasks={failedItems} color="error.main" />
                          </>
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
