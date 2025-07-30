import { memo, useContext } from "react";
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
import { useCheckTasks } from "app/hooks/useCheckTasks";
import { useCheckTodayCreateTasks } from "app/hooks/useCheckTodayCreateTasks";
import { SendtaskListContext } from "app/contexts/SendtaskListContext";

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
  const theme = useTheme();
  const { settings, updateSettings } = useSettings();
  const { logout, user } = useAuth();
  const isMdScreen = useMediaQuery(theme.breakpoints.down("md"));

  const { refresh, isCheckingSends, setIsCheckingSends } = useContext(SendtaskListContext);
  const { fetchCheckTasks } = useCheckTasks({ refresh, setIsCheckingSends });
  const { fetchCheckTodayCreateTasks } = useCheckTodayCreateTasks({ refresh, setIsCheckingSends });
  const { controllerRef, createController } = useAbortOnUnmount();


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

  const fetchUpdataMtmpl = async () => {
    // 彈出確認視窗
    if (!window.confirm("確定要執行郵件樣板更新嗎？")) {
        return;
    }

    // 先中止前一個請求
    if (controllerRef.current) {
        controllerRef.current.abort();
    }

    setIsCheckingSends(true);
    // 建立新的 controller
    const controller = createController();
        await axios.post("/api/update_mtmpl", {}, {
            signal: controller.signal,
        })
            .then((res) => res.data)
            .then(result => {
              if (result.status === 'success') {
                  const { added, removed } = result.data;
                  const addedTitles = added.map(item => `- ${item.mtmpl_title}`).join("\n");
                  const removedTitles = removed.map(item => `- ${item.mtmpl_title}`).join("\n");
                  const message = `郵件樣板同步完成！\n\n新增 ${added.length} 筆：\n${addedTitles || "(無)"}\n\n移除 ${removed.length} 筆：\n${removedTitles || "(無)"}`;
                  alert(message);
              } else {
                  alert(`更新失敗: ${result.message}`);
              } 
                setIsCheckingSends(false);
            })
            .catch((err) => {
            if (err.name === "AbortError") {
                // 請求被中止，不顯示錯誤
            } else {
                console.error("更新郵件樣板時發生錯誤", err);
                alert("網路錯誤，更新失敗，請稍後再試");
            }
            setIsCheckingSends(false);
        });
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


          {/* <IconBox>
            <StyledIconButton>
              <MailOutline />
            </StyledIconButton>

            <StyledIconButton>
              <WebAsset />
            </StyledIconButton>

            <StyledIconButton>
              <StarOutline />
            </StyledIconButton>
          </IconBox> */}
        </Box>

        <Box display="flex" alignItems="center">
          {isCheckingSends && (
            <Span sx={{ color: "blue", marginRight: 2, whiteSpace: "nowrap" }}>
              任務列表更新中...
            </Span>
          )}
          {/* <MatxSearchBox />

          <NotificationProvider>
            <NotificationBar />
          </NotificationProvider>

          <ShoppingCart /> */}

          <MatxMenu
            menuButton={
              <UserMenu>
                <Span>
                  Hi <strong>{user.name}</strong>
                </Span>

                {/* <Avatar src={user.avatar} sx={{ cursor: "pointer" }} /> */}
              </UserMenu>
            }>
            <StyledItem 
              onClick={isCheckingSends ? undefined : fetchCheckTodayCreateTasks}
              disabled={isCheckingSends}
              sx={{
                opacity: isCheckingSends ? 0.5 : 1,
                cursor: isCheckingSends ? 'not-allowed' : 'pointer',
                '&:hover': {
                  backgroundColor: isCheckingSends ? 'transparent' : 'action.hover'
                }
              }}
            >
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>檢查今日建立任務</Span>
            </StyledItem>

            <StyledItem 
              onClick={isCheckingSends ? undefined : fetchUpdataMtmpl}
              disabled={isCheckingSends}
              sx={{
                opacity: isCheckingSends ? 0.5 : 1,
                cursor: isCheckingSends ? 'not-allowed' : 'pointer',
                '&:hover': {
                  backgroundColor: isCheckingSends ? 'transparent' : 'action.hover'
                }
              }}
            >
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>更新郵件樣板列表</Span>
            </StyledItem>

            <StyledItem
              onClick={isCheckingSends ? undefined : fetchCheckTasks}
              disabled={isCheckingSends}
              sx={{
                opacity: isCheckingSends ? 0.5 : 1,
                cursor: isCheckingSends ? 'not-allowed' : 'pointer',
                '&:hover': {
                  backgroundColor: isCheckingSends ? 'transparent' : 'action.hover'
                }
              }}
            >
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>更新任務列表</Span>
            </StyledItem>

            {/* <StyledItem>
              <Link to="/page-layouts/user-profile">
                <Person />
                <Span sx={{ marginInlineStart: 1 }}>Profile</Span>
              </Link>
            </StyledItem>

            <StyledItem>
              <Settings />
              <Span sx={{ marginInlineStart: 1 }}>Settings</Span>
            </StyledItem> */}

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
