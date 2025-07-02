import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import Grid from "@mui/material/Grid2";
// import Tooltip from "@mui/material/Tooltip";
// import IconButton from "@mui/material/IconButton";
import { styled } from "@mui/material/styles";
// import Assignment from "@mui/icons-material/Assignment";
import AssignmentLate from "@mui/icons-material/AssignmentLate";
// import ArrowRightAlt from "@mui/icons-material/ArrowRightAlt";
import { Small } from "app/components/Typography";

import { useContext } from "react";
import { SendtaskListContext } from "app/contexts/SendtaskListContext";

// STYLED COMPONENTS
const StyledCard = styled(Card)(({ theme, selected }) => ({
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "24px !important",
  background: selected ? theme.palette.primary.light : theme.palette.background.paper,
  cursor: "pointer",
  transition: "all 0.3s ease",
  border: selected ? `2px solid ${theme.palette.primary.main}` : "1px solid transparent",
  "&:hover": {
    background: selected ? theme.palette.primary.light : theme.palette.grey[100],
    transform: "translateY(-2px)",
    boxShadow: theme.shadows[8]
  },
  [theme.breakpoints.down("sm")]: { padding: "16px !important" }
}));

const ContentBox = styled(Box)(({ theme }) => ({
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  "& small": { color: theme.palette.text.secondary },
  "& .icon": { opacity: 0.6, fontSize: "44px", color: theme.palette.primary.main }
}));

const Heading = styled("h6")(({ theme }) => ({
  margin: 0,
  marginTop: "4px",
  fontSize: "14px",
  fontWeight: "500",
  color: theme.palette.primary.main
}));

export default function StatCards({ setShowTodayOnly, taskState, setTaskState }) {
  const { todayTasks, statsData } = useContext(SendtaskListContext);
  
  // 執行中任務：今日尚未寄出>0 且 今日成功寄出>0 且 今日寄出失敗為0
  const runningCount = todayTasks.filter(row => {
    const stats = statsData[row.sendtask_uuid] || {};
    return Number(stats.todayunsend) > 0 && Number(stats.todaysuccess) > 0 && Number(stats.todaysend) - Number(stats.todaysuccess) === 0;
  });

  // 尚未開始任務：今日尚未寄出>0 且 今日成功寄出=0 且 今日寄出失敗=0
  const notStartedCount = todayTasks.filter(row => {
    const stats = statsData[row.sendtask_uuid] || {};
    return Number(stats.todayunsend) > 0 && Number(stats.todaysuccess) === 0 && Number(stats.todaysend) - Number(stats.todaysuccess) === 0;
  });

  // 已完成任務：今日尚未寄出=0 且 今日寄出失敗=0
  const completedCount = todayTasks.filter(row => {
    const stats = statsData[row.sendtask_uuid] || {};
    return Number(stats.todayunsend) === 0 && Number(stats.todaysend) - Number(stats.todaysuccess) === 0;
  });

  // 異常任務：今日寄出失敗非0
  const warningCount = todayTasks.filter(row => {
    const stats = statsData[row.sendtask_uuid] || {};
    return Number(stats.todaysend) - Number(stats.todaysuccess) > 0;
  });

  const cardList = [
    { id: "doing", name: "執行中", amount: runningCount.length, Icon: AssignmentLate },
    { id: "notyet", name: "尚未開始", amount: notStartedCount.length, Icon: AssignmentLate },
    { id: "done", name: "已完成", amount: completedCount.length, Icon: AssignmentLate },
    { id: "warning", name: "異常任務", amount: warningCount.length, Icon: AssignmentLate },
  ];

  const handleCardClick = (value) => {
    setShowTodayOnly(true); // 假設這個變數在其他地方定義，表示是否只顯示今天的任務
    // 如果點擊的是已選中的卡片，則切換回"全部"
    if (taskState === value) {
      setTaskState("all");
    } else {
      setTaskState(value);
    }
  };

  
  return (
    <Grid container spacing={3} sx={{ mb: "24px" }}>
      {cardList.map(({ amount, Icon, name, id }) => (
        <Grid  size={{ md: 3, xs: 6 }} key={name}>
          <StyledCard
            elevation={6}
            value={id}
            selected={taskState === id}
            onClick={() => handleCardClick(id)}
          >
            <ContentBox>
              <Icon className="icon" />

              <Box ml="12px">
                <Small>{name}</Small>
                <Heading>{amount} / {todayTasks.length}</Heading>
              </Box>
            </ContentBox>

            {/* <Tooltip title="View Details" placement="top">
              <IconButton>
                <ArrowRightAlt />
              </IconButton>
            </Tooltip> */}
          </StyledCard>
        </Grid>
      ))}
    </Grid>
  );
}
