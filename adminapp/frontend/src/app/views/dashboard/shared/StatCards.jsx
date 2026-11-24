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
import { getTodayTaskState, isTodayTaskWarning } from "../utils/todayTaskStatus";

// STYLED COMPONENTS
const StyledCard = styled(Card, {
  shouldForwardProp: (prop) => prop !== "selected" && prop !== "interactionDisabled"
})(({ theme, selected, interactionDisabled }) => ({
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  justifyContent: "space-between",
  padding: "24px !important",
  background: selected && !interactionDisabled ? theme.palette.primary.light : theme.palette.background.paper,
  cursor: interactionDisabled ? "default" : "pointer",
  transition: "all 0.3s ease",
  border: selected && !interactionDisabled ? `2px solid ${theme.palette.primary.main}` : "1px solid transparent",
  opacity: interactionDisabled ? 0.65 : 1,
  "&:hover": {
    background: interactionDisabled
      ? theme.palette.background.paper
      : selected
        ? theme.palette.primary.light
        : theme.palette.grey[100],
    transform: interactionDisabled ? "none" : "translateY(-2px)",
    boxShadow: interactionDisabled ? theme.shadows[6] : theme.shadows[8]
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

export default function StatCards({ setShowTodayOnly, taskState, setTaskState, filtersDisabled = false }) {
  const { todayTasks, statsData } = useContext(SendtaskListContext);

  const stateCounts = todayTasks.reduce((counts, row) => {
    const stats = statsData[row.sendtask_uuid] || {};
    const state = getTodayTaskState(stats);
    counts[state] += 1;
    if (isTodayTaskWarning(stats)) counts.warning += 1;
    return counts;
  }, { doing: 0, notyet: 0, done: 0, warning: 0 });

  const cardList = [
    { id: "doing", name: "今日執行中", amount: stateCounts.doing, Icon: AssignmentLate },
    { id: "notyet", name: "今日尚未開始", amount: stateCounts.notyet, Icon: AssignmentLate },
    { id: "done", name: "今日已完成", amount: stateCounts.done, Icon: AssignmentLate },
    { id: "warning", name: "今日異常任務", amount: stateCounts.warning, Icon: AssignmentLate },
  ];

  const handleCardClick = (value) => {
    if (filtersDisabled) return;

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
            interactionDisabled={filtersDisabled}
            aria-disabled={filtersDisabled}
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
