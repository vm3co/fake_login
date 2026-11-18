import { styled } from "@mui/material/styles";
import { Fragment, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Grid from "@mui/material/Grid2";

import StatCards from "./shared/StatCards";
import ShowTodayTasks from "./shared/ShowTodayTasks";
import ShowAllTasks from "./shared/ShowAllTasks";
import ShowBackupTasks from "./shared/ShowBackupTasks";
import TaskDetail from './shared/TaskDetail_new';
import useAuth from 'app/hooks/useAuth';


// STYLED COMPONENTS
const ContentBox = styled("div")(({ theme }) => ({
  margin: "2rem",
  [theme.breakpoints.down("sm")]: { margin: "1rem" }
}));

export default function Analytics() {
  const [viewMode, setViewMode] = useState('today');
  const [backupDetail, setBackupDetail] = useState(null);
  const { user } = useAuth();
  const canManageBackups = user?.user_type === 'user' || user?.admin_role === true;
  const [taskState, setTaskState] = useState("all");
  const [showSelectedOnly, setShowSelectedOnly] = useState(false);

  const handleTaskListChange = (mode) => {
    setBackupDetail(null);
    setShowSelectedOnly(false);
    setViewMode(mode);
  };

  return (
    <Fragment>
      <ContentBox className="analytics">
        <Grid container spacing={3}>
          <Grid size={{ md: 12, xs: 12 }} >
            <StatCards
              setShowTodayOnly={() => setViewMode('today')}
              taskState={taskState}
              setTaskState={setTaskState}
              filtersDisabled={showSelectedOnly || viewMode === 'backups'}
            />
          </Grid>
          <Grid size={{ md: 12, xs: 12 }}>
            <Box display="flex" justifyContent="center" flexWrap="wrap" gap={1} mb={2}>
              <Button
                variant={viewMode === 'all' ? "contained" : "outlined"}
                color="primary"
                onClick={() => handleTaskListChange('all')}
                sx={{ mx: 1 }}
              >
                全部任務
              </Button>
              <Button
                variant={viewMode === 'today' ? "contained" : "outlined"}
                color="primary"
                onClick={() => handleTaskListChange('today')}
                sx={{ mx: 1 }}
              >
                今日任務
              </Button>
              {canManageBackups && user?.user_type !== 'customer' && <Button variant={viewMode === 'backups' ? 'contained' : 'outlined'}
                onClick={() => handleTaskListChange('backups')}>備援任務</Button>}
            </Box>
            {viewMode === 'backups' && canManageBackups && user?.user_type !== 'customer' ? <ShowBackupTasks onOpenBackup={setBackupDetail} /> : viewMode === 'today' ? (
              <ShowTodayTasks
                taskState={taskState}
                setTaskState={setTaskState}
                showSelectedOnly={showSelectedOnly}
                setShowSelectedOnly={setShowSelectedOnly}
              />
            ) : (
              <ShowAllTasks
                showSelectedOnly={showSelectedOnly}
                setShowSelectedOnly={setShowSelectedOnly}
              />
            )}
          </Grid>
        </Grid>
      </ContentBox>
      {viewMode === 'backups' && canManageBackups && user?.user_type !== 'customer' && <TaskDetail task={backupDetail}
        open={!!backupDetail} onClose={() => setBackupDetail(null)} />}
    </Fragment>
  );
}
