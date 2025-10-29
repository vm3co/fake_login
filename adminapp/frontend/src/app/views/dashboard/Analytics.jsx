import { styled } from "@mui/material/styles";
import { Fragment, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid2";

import StatCards from "./shared/StatCards";
import ShowTodayTasks from "./shared/ShowTodayTasks";
import ShowAllTasks from "./shared/ShowAllTasks";
import { SendtaskListProvider } from "app/contexts/SendtaskListContext";


// STYLED COMPONENTS
const ContentBox = styled("div")(({ theme }) => ({
  margin: "2rem",
  [theme.breakpoints.down("sm")]: { margin: "1rem" }
}));




// const Title = styled("span")(() => ({
//   fontSize: "1rem",
//   fontWeight: "500",
//   marginRight: ".5rem",
//   textTransform: "capitalize"
// }));

// const SubTitle = styled("span")(({ theme }) => ({
//   fontSize: "0.875rem",
//   color: theme.palette.primary.main
// }));


// const H4 = styled("h4")(({ theme }) => ({
//   fontSize: "1rem",
//   fontWeight: "500",
//   marginBottom: "1rem",
//   textTransform: "capitalize",
//   color: theme.palette.text.secondary
// }));

export default function Analytics() {
  // const { palette } = useTheme();
  // const { todayTasks } = useContext(SendtaskListContext);
  const [showTodayOnly, setShowTodayOnly] = useState(true);
  const [taskState, setTaskState] = useState("all");

  return (
    <SendtaskListProvider>
      <Fragment>
        <ContentBox className="analytics">
          <Grid container spacing={3}>
            <Grid size={{ md: 12, xs: 12 }} >
              <StatCards
                setShowTodayOnly={setShowTodayOnly}
                taskState={taskState}
                setTaskState={setTaskState}
              />
            </Grid>
            <Grid size={{ md: 12, xs: 12 }}>
              <Box display="flex" justifyContent="center" mb={2}>
                <Button
                  variant={showTodayOnly ? "outlined" : "contained"}
                  color="primary"
                  onClick={() => setShowTodayOnly(false)}
                  sx={{ mx: 1 }}
                >
                  全部任務
                </Button>
                <Button
                  variant={showTodayOnly ? "contained" : "outlined"}
                  color="primary"
                  onClick={() => setShowTodayOnly(true)}
                  sx={{ mx: 1 }}
                >
                  今日任務
                </Button>
              </Box>
              {showTodayOnly ? (
                <ShowTodayTasks
                  taskState={taskState}
                  setTaskState={setTaskState}
                />
              ) : (
                <ShowAllTasks />
              )}
            </Grid>
          </Grid>
        </ContentBox>
      </Fragment>
    </SendtaskListProvider>
  );
}
