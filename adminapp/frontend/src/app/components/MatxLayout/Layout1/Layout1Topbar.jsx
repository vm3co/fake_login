import { memo, useState, useContext } from "react";
// import { Link } from "react-router-dom";
import Box from "@mui/material/Box";
// import Avatar from "@mui/material/Avatar";
import MenuItem from "@mui/material/MenuItem";
import IconButton from "@mui/material/IconButton";
import AssignmentTurnedIn from "@mui/icons-material/AssignmentTurnedIn";
// import Button from "@mui/material/Button";
import styled from "@mui/material/styles/styled";
import useTheme from "@mui/material/styles/useTheme";
import useMediaQuery from "@mui/material/useMediaQuery";
// import Home from "@mui/icons-material/Home";
import Menu from "@mui/icons-material/Menu";
// import Person from "@mui/icons-material/Person";
// import Settings from "@mui/icons-material/Settings";
// import WebAsset from "@mui/icons-material/WebAsset";
// import MailOutline from "@mui/icons-material/MailOutline";
// import StarOutline from "@mui/icons-material/StarOutline";
import PowerSettingsNew from "@mui/icons-material/PowerSettingsNew";

import useAuth from "app/hooks/useAuth";
import useSettings from "app/hooks/useSettings";
// import { NotificationProvider } from "app/contexts/NotificationContext";
import { useCheckTasks } from "app/hooks/useCheckTasks";
import { useCheckTodayCreateTasks } from "app/hooks/useCheckTodayCreateTasks";
import { SendtaskListContext } from "app/contexts/SendtaskListContext";

import { Span } from "app/components/Typography";
import { MatxMenu } from "app/components";
import { themeShadows } from "app/components/MatxTheme/themeColors";
import { topBarHeight } from "app/utils/constant";
// import ShoppingCart from "app/components/ShoppingCart";
// import { MatxSearchBox } from "app/components";
// import { NotificationBar } from "app/components/NotificationBar";


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

  const [isCheckingTasks, setIsCheckingTasks] = useState(false);
  const { refresh } = useContext(SendtaskListContext);
  const { fetchCheckTasks } = useCheckTasks({ refresh, setIsCheckingTasks });
  const { fetchCheckTodayCreateTasks } = useCheckTodayCreateTasks({ refresh, setIsCheckingTasks });

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

  return (
    <TopbarRoot>
      <TopbarContainer>
        <Box display="flex">
          <StyledIconButton onClick={handleSidebarToggle}>
            <Menu />
          </StyledIconButton>

          {/* <Box display="flex" ml="auto" alignItems="center">
            <Span sx={{ mr: 2 }}>
              Hi <strong>{user.name}</strong>
            </Span>
            <Button
              variant="outlined"
              color="secondary"
              onClick={logout}
            >
              Logout
            </Button>
          </Box> */}


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
          {isCheckingTasks && (
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
            <StyledItem onClick={fetchCheckTodayCreateTasks}>
              <AssignmentTurnedIn />
              <Span sx={{ marginInlineStart: 1 }}>檢查今日建立任務</Span>
            </StyledItem>
            <StyledItem onClick={fetchCheckTasks}>
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
