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
    <Fragment>
      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid size={{ md: 12, xs: 12 }} >
            <StatCards
              setShowTodayOnly={setShowTodayOnly}
              taskState={taskState}
              setTaskState={setTaskState}
            />
            {/* <StatCards2 /> */}

            {/* <H4>Ongoing Projects</H4>
            <RowCards /> */}
          </Grid>

          {/* <Grid size={{ md: 4, xs: 12 }}>
            <Card sx={{ px: 3, py: 2, mb: 3 }}>
              <Title>今日任務</Title>
              <SubTitle>{todayTasks.length}</SubTitle>

              <DoughnutChart
                height="150px"
                // color={[palette.primary.dark, palette.primary.main, palette.primary.light]}
                color={["#0080FF", "#02F78E", "#CE0000"]}
              />
            </Card>

            <UpgradeCard />
            <Campaigns />
          </Grid> */}

          <Grid size={{ md: 12, xs: 12 }}>
            {/* <H4>Top Selling Products</H4> */}
            {/* <Title>{ showTodayOnly ? "今日任務列表" : "全部任務列表" }</Title>*/}
            {/* <Switch
              checked={showTodayOnly}
              onChange={(e) => {
                setShowTodayOnly(e.target.checked);
              }}
              color="primary"
            />  */}
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
            {/* <TopSellingTable /> */}
          </Grid>
        </Grid>
      </ContentBox>
    </Fragment>
  );
}
