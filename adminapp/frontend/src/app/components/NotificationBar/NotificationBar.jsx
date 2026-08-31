import { Fragment, useCallback, useEffect, useState } from "react";
// import { Link } from "react-router-dom";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Icon from "@mui/material/Icon";
import Badge from "@mui/material/Badge";
import Button from "@mui/material/Button";
import Drawer from "@mui/material/Drawer";
import styled from "@mui/material/styles/styled";
import IconButton from "@mui/material/IconButton";
import ThemeProvider from "@mui/material/styles/ThemeProvider";
import Notifications from "@mui/icons-material/Notifications";
import Clear from "@mui/icons-material/Clear";
import Refresh from "@mui/icons-material/Refresh";
import {
  Chip,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tab,
  Tabs,
  Typography
} from "@mui/material";
import axios from "axios";

import useAuth from "app/hooks/useAuth";
import useSettings from "app/hooks/useSettings";
import useNotification from "app/hooks/useNotification";
import { getTimeDifference } from "app/utils/utils.js";
import { topBarHeight } from "app/utils/constant";
import { themeShadows } from "../MatxTheme/themeColors";
import { Paragraph, Small } from "../Typography";

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

const NotificationCard = styled(Box)(({ theme }) => ({
  position: "relative",
  "&:hover": {
    "& .messageTime": { display: "none" },
    "& .deleteButton": { opacity: "1" }
  },
  "& .messageTime": { color: theme.palette.text.secondary },
  "& .icon": { fontSize: "1.25rem" }
}));

const DeleteButton = styled(IconButton)(() => ({
  opacity: "0",
  position: "absolute",
  right: 5,
  marginTop: 9,
  marginRight: "24px",
  background: "rgba(0, 0, 0, 0.01)"
}));

const CardLeftContent = styled("div")(({ theme }) => ({
  padding: "12px 8px",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  background: "rgba(0, 0, 0, 0.01)",
  "& small": {
    fontWeight: "500",
    marginLeft: "16px",
    color: theme.palette.text.secondary
  }
}));

const Heading = styled("span")(({ theme }) => ({
  fontWeight: "500",
  marginLeft: "16px",
  color: theme.palette.text.secondary
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
  const [activeTab, setActiveTab] = useState("notifications");
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [jobsError, setJobsError] = useState("");
  const { deleteNotification, clearNotifications, notifications } = useNotification();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedNotification, setSelectedNotification] = useState(null);

  const handleDrawerToggle = () => setPanelOpen((open) => !open);

  const fetchJobs = useCallback(async (showLoading = false) => {
    if (activeTab === "notifications") return;

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
    if (!panelOpen || activeTab === "notifications") return undefined;

    fetchJobs(true);
    const intervalId = window.setInterval(() => fetchJobs(false), 2000);
    return () => window.clearInterval(intervalId);
  }, [panelOpen, activeTab, fetchJobs]);

  const handleNotificationClick = (notification) => {
    setSelectedNotification(notification);
    setDialogOpen(true);
    setPanelOpen(false);
  };

  const handleDialogClose = () => {
    setDialogOpen(false);
    setSelectedNotification(null);
  };

  return (
    <Fragment>
      <IconButton onClick={handleDrawerToggle}>
        <Badge color="secondary" badgeContent={notifications?.length}>
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
              <h5>通知與更新任務</h5>
            </Notification>

            <Tabs
              value={activeTab}
              onChange={(_, value) => setActiveTab(value)}
              variant="fullWidth"
              sx={{ borderBottom: 1, borderColor: "divider", mb: 2 }}>
              <Tab value="notifications" label="通知" />
              <Tab value="manual" label="手動更新" />
              <Tab value="scheduler" label="系統排程" />
            </Tabs>

            {activeTab === "notifications" && (
              <>
                {notifications?.map((notification) => (
                  <NotificationCard key={notification.id}>
                    <DeleteButton
                      size="small"
                      className="deleteButton"
                      onClick={(event) => {
                        event.stopPropagation();
                        deleteNotification(notification.id);
                      }}>
                      <Clear className="icon" />
                    </DeleteButton>

                    <Box
                      onClick={() => handleNotificationClick(notification)}
                      sx={{ textDecoration: "none", cursor: "pointer" }}>
                      <Card sx={{ mx: 2, mb: 2 }} elevation={3}>
                        <CardLeftContent>
                          <Box display="flex">
                            <Icon className="icon" color={notification.icon?.color || "primary"}>
                              {notification.icon?.name || "notifications"}
                            </Icon>
                            <Heading>{notification.heading}</Heading>
                          </Box>

                          <Small className="messageTime">
                            {getTimeDifference(new Date(notification.timestamp))} ago
                          </Small>
                        </CardLeftContent>

                        <Box px={2} pt={1} pb={2}>
                          <Paragraph m={0}>{notification.title}</Paragraph>
                          <Small color="text.secondary">{notification.subtitle}</Small>
                        </Box>
                      </Card>
                    </Box>
                  </NotificationCard>
                ))}

                {!!notifications?.length && (
                  <Button fullWidth onClick={clearNotifications}>
                    清除通知
                  </Button>
                )}
              </>
            )}

            {activeTab !== "notifications" && (
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
                          <Typography variant="subtitle2">{job.type}</Typography>
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
            )}
          </Box>
        </Drawer>

        {/* Notification Details Dialog */}
        {selectedNotification && (
          <Dialog open={dialogOpen} onClose={handleDialogClose} maxWidth="sm" fullWidth>
            <DialogTitle>
              <Box display="flex" alignItems="center">
                <Icon color={selectedNotification.icon?.color || "primary"} sx={{ mr: 1 }}>
                  {selectedNotification.icon?.name || "notifications"}
                </Icon>
                {selectedNotification.heading || "通知詳情"}
              </Box>
            </DialogTitle>
            <DialogContent>
              <Box py={2}>
                <Typography variant="h6" gutterBottom>
                  {selectedNotification.title}
                </Typography>
                <Typography variant="body1" color="textSecondary" paragraph>
                  {selectedNotification.subtitle}
                </Typography>
                <Typography variant="caption" color="textSecondary" display="block">
                  時間: {formatTaipeiTime(selectedNotification.timestamp)}
                </Typography>
                {selectedNotification.details && (
                  <Typography variant="body2" color="textPrimary" display="block" sx={{ mt: 2, whiteSpace: "pre-wrap" }}>
                    {selectedNotification.details}
                  </Typography>
                )}
                {selectedNotification.path && (
                  <Typography variant="caption" color="textSecondary" display="block" sx={{ mt: 1 }}>
                    相關路徑: {selectedNotification.path}
                  </Typography>
                )}
              </Box>
            </DialogContent>
            <DialogActions>
              <Button onClick={handleDialogClose} color="primary">
                關閉
              </Button>
            </DialogActions>
          </Dialog>
        )}
      </ThemeProvider>
    </Fragment>
  );
}
