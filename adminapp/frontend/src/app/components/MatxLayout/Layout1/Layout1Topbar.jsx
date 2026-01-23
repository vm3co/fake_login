import { memo, useContext } from "react";
import { useSnackbar } from 'notistack';
// import { Link } from "react-router-dom";
import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import MenuItem from "@mui/material/MenuItem";
import IconButton from "@mui/material/IconButton";
import AssignmentTurnedIn from "@mui/icons-material/AssignmentTurnedIn";
import styled from "@mui/material/styles/styled";
import useTheme from "@mui/material/styles/useTheme";
import useMediaQuery from "@mui/material/useMediaQuery";
import Menu from "@mui/icons-material/Menu";
import PowerSettingsNew from "@mui/icons-material/PowerSettingsNew";

import useAuth from "app/hooks/useAuth";
import useSettings from "app/hooks/useSettings";
import { useJob } from "app/contexts/JobContext";
import { NotificationProvider } from "app/contexts/NotificationContext";
import NotificationBar from "app/components/NotificationBar/NotificationBar";

import { Span } from "app/components/Typography";
import { MatxMenu } from "app/components";
import { themeShadows } from "app/components/MatxTheme/themeColors";
import { topBarHeight } from "app/utils/constant";
import useAbortOnUnmount from "app/hooks/useAbortOnUnmount";
import axios from "axios";


// STYLED COMPONENTS
const StyledIconButton = styled(IconButton)(({ theme }) => ({
  color: theme.palette.text.primary
}));

const TopbarRoot = styled("div")({
  top: 0,
  zIndex: 96,
  height: topBarHeight,
  boxShadow: themeShadows[8],
  transition: "all 0.3s ease"
});

const TopbarContainer = styled("div")(({ theme }) => ({
  padding: "8px",
  paddingLeft: 18,
  paddingRight: 20,
  height: "100%",
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  background: theme.palette.primary.main,
  [theme.breakpoints.down("sm")]: { paddingLeft: 16, paddingRight: 16 },
  [theme.breakpoints.down("xs")]: { paddingLeft: 14, paddingRight: 16 }
}));

const UserMenu = styled("div")({
  padding: 4,
  display: "flex",
  borderRadius: 24,
  cursor: "pointer",
  alignItems: "center",
  "& span": { margin: "0 8px" }
});

const StyledItem = styled(MenuItem)(({ theme }) => ({
  display: "flex",
  alignItems: "center",
  minWidth: 185,
  "& a": {
    width: "100%",
    display: "flex",
    alignItems: "center",
    textDecoration: "none"
  },
  "& span": { marginRight: "10px", color: theme.palette.text.primary }
}));

// const IconBox = styled("div")(({ theme }) => ({
//   display: "inherit",
//   [theme.breakpoints.down("md")]: { display: "none !important" }
// }));

const Layout1Topbar = () => {
  const { enqueueSnackbar } = useSnackbar();
  const theme = useTheme();
  const { settings, updateSettings } = useSettings();
  const { logout, user } = useAuth();
  const isMdScreen = useMediaQuery(theme.breakpoints.down("md"));

  const { startJob, currentJob } = useJob();

  // 檢查是否有正在運行的任務 (為了禁用按鈕)
  const isJobRunning = currentJob && ["running", "pending"].includes(currentJob.status);

  const updateSidebarMode = (sidebarSettings) => {
    updateSettings({ layout1Settings: { leftSidebar: { ...sidebarSettings } } });
  };

  const handleSidebarToggle = () => {
    let { layout1Settings } = settings;
    let mode;
    if (isMdScreen) {
      mode = layout1Settings.leftSidebar.mode === "close" ? "mobile" : "close";
    } else {
      mode = layout1Settings.leftSidebar.mode === "full" ? "close" : "full";
    }
    updateSidebarMode({ mode });
  };

  const handleUpdateMtmpl = async () => {
    if (!window.confirm("確定要執行郵件樣板更新嗎？")) return;
    startJob("update_mtmpl");
  };

  const handleCheckTodayCreateTasks = async () => {
    if (!window.confirm("確定要執行檢查今日建立任務嗎？")) return;
    // 傳入 user.orgs 以確保後端能正確過濾
    startJob("refresh_today_create_task", { orgs: user.orgs });
  };

  const handleCheckTasks = async () => {
    if (!window.confirm("確定要執行任務列表更新嗎？")) return;
    // 傳入 user.orgs 以確保後端能正確過濾
    startJob("check_sendtasks", { orgs: user.orgs });
  };


  return (
    <TopbarRoot>
      <TopbarContainer>
        <Box display="flex">
          <StyledIconButton onClick={handleSidebarToggle}>
            <Menu />
          </StyledIconButton>

          <Box display="flex" ml="auto" alignItems="center">
            <Typography variant="h4" component="h6" sx={{ mr: 2, fontWeight: 'bold', fontFamily: 'Noto Sans TC, sans-serif' }}>
              社交工程管理系統
            </Typography>
          </Box>
        </Box>

        <Box display="flex" alignItems="center">
          {/* 使用 JobContext 的全域通知，這邊不再需要額外的 Span */}

          <NotificationProvider>
            <NotificationBar />
          </NotificationProvider>

          <MatxMenu
            menuButton={
              <UserMenu>
                <Span>
                  Hi <strong>{user.name}</strong>
                </Span>
              </UserMenu>
            }>
            <StyledItem
              onClick={isJobRunning ? undefined : handleCheckTodayCreateTasks}
              disabled={isJobRunning}
              sx={{
                opacity: isJobRunning ? 0.5 : 1,
                cursor: isJobRunning ? 'not-allowed' : 'pointer',
                '&:hover': {
                  backgroundColor: isJobRunning ? 'transparent' : 'action.hover'
                }
              }}
            >
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>檢查今日建立任務</Span>
            </StyledItem>

            <StyledItem
              onClick={isJobRunning ? undefined : handleUpdateMtmpl}
              disabled={isJobRunning}
              sx={{
                opacity: isJobRunning ? 0.5 : 1,
                cursor: isJobRunning ? 'not-allowed' : 'pointer',
                '&:hover': {
                  backgroundColor: isJobRunning ? 'transparent' : 'action.hover'
                }
              }}
            >
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>更新郵件樣板列表</Span>
            </StyledItem>

            <StyledItem
              onClick={isJobRunning ? undefined : handleCheckTasks}
              disabled={isJobRunning}
              sx={{
                opacity: isJobRunning ? 0.5 : 1,
                cursor: isJobRunning ? 'not-allowed' : 'pointer',
                '&:hover': {
                  backgroundColor: isJobRunning ? 'transparent' : 'action.hover'
                }
              }}
            >
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>更新任務列表</Span>
            </StyledItem>

            <StyledItem onClick={logout}>
              <PowerSettingsNew />
              <Span sx={{ marginInlineStart: 1 }}>Logout</Span>
            </StyledItem>
          </MatxMenu>
        </Box>
      </TopbarContainer>
    </TopbarRoot>
  );
};

export default memo(Layout1Topbar);
