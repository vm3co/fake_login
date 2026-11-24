import { useState } from 'react';
import { Alert, Box, Typography } from '@mui/material';
import useAuth from 'app/hooks/useAuth';
import ShowBackupTasks from './shared/ShowBackupTasks';
import TaskDetail from './shared/TaskDetail_new';

export default function TaskHistory() {
  const { user } = useAuth();
  const [detail, setDetail] = useState(null);
  const allowed = user?.user_type !== 'customer' && user?.user_type !== 'platform_admin' &&
    (user?.user_type === 'user' || user?.admin_role === true);
  if (!allowed) return <Alert severity="error">無權查閱任務歷史版本</Alert>;
  return <Box sx={{ m: { xs: 2, sm: 4 }, minWidth: 0 }}>
    <Typography variant="h5" sx={{ mb: 3 }}>任務歷史版本</Typography>
    <ShowBackupTasks onOpenBackup={setDetail} />
    <TaskDetail task={detail} open={!!detail} onClose={() => setDetail(null)} />
  </Box>;
}