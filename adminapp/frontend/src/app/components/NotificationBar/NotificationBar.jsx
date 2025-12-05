import { Fragment, useState } from "react";
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
import { Dialog, DialogTitle, DialogContent, DialogActions, Typography } from "@mui/material";

import useSettings from "app/hooks/useSettings";
import useNotification from "app/hooks/useNotification";
import { getTimeDifference } from "app/utils/utils.js";
import { sideNavWidth, topBarHeight } from "app/utils/constant";
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

export default function NotificationBar({ container }) {
  const { settings } = useSettings();
  const [panelOpen, setPanelOpen] = useState(false);
  const { deleteNotification, clearNotifications, notifications } = useNotification();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedNotification, setSelectedNotification] = useState(null);

  const handleDrawerToggle = () => setPanelOpen(!panelOpen);

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
          <Box sx={{ width: sideNavWidth }}>
            <Notification>
              <Notifications color="primary" />
              <h5>Notifications</h5>
            </Notification>

            {notifications?.map((notification) => (
              <NotificationCard key={notification.id}>
                <DeleteButton
                  size="small"
                  className="deleteButton"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteNotification(notification.id);
                  }}>
                  <Clear className="icon" />
                </DeleteButton>

                <Box
                  onClick={() => handleNotificationClick(notification)}
                  sx={{ textDecoration: "none", cursor: "pointer" }}>
                  <Card sx={{ mx: 2, mb: 3 }} elevation={3}>
                    <CardLeftContent>
                      <Box display="flex">
                        <Icon className="icon" color={notification.icon?.color || "primary"}>
                          {notification.icon?.name || "notifications"}
                        </Icon>
                        <Heading>{notification.heading}</Heading>
                      </Box>

                      <Small className="messageTime">
                        {getTimeDifference(new Date(notification.timestamp))}
                        ago
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
                Clear Notifications
              </Button>
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
                  時間: {new Date(selectedNotification.timestamp).toLocaleString()}
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
