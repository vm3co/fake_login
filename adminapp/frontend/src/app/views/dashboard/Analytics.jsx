import { styled } from "@mui/material/styles";
import { Fragment, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid2";

import StatCards from "./shared/StatCards";
import ShowTodayTasks from "./shared/ShowTodayTasks";
import ShowAllTasks from "./shared/ShowAllTasks";


// STYLED COMPONENTS
const ContentBox = styled("div")(({ theme }) => ({
  margin: "2rem",
  [theme.breakpoints.down("sm")]: { margin: "1rem" }
}));

export default function Analytics() {
  const [showTodayOnly, setShowTodayOnly] = useState(true);
  const [taskState, setTaskState] = useState("all");

  return (
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
  );
}
