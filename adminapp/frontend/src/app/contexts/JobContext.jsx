import React, { createContext, useState, useEffect, useContext, useRef, useCallback } from 'react';
import axios from 'axios';
import { useSnackbar } from 'notistack';
import { Box, Button, Typography, CircularProgress } from '@mui/material';
import useAuth from 'app/hooks/useAuth';
import NotificationContext from './NotificationContext';

const JobContext = createContext({
    currentJob: null,
    startJob: () => Promise.resolve(),
    cancelJob: () => Promise.resolve(),
});

export const useJob = () => useContext(JobContext);

export const JobProvider = ({ children }) => {
    const [currentJob, setCurrentJob] = useState(null);
    const { enqueueSnackbar, closeSnackbar } = useSnackbar();
    const snackbarKey = useRef(null);
    const lastProcessedJobId = useRef(null);
    const { isAuthenticated } = useAuth();
    const { getNotifications } = useContext(NotificationContext);
    const isFirstPoll = useRef(true);
    const timeoutRef = useRef(null);

    const cancelJob = useCallback(async () => {
        try {
            await axios.post('/api/jobs/cancel');
            enqueueSnackbar("正在取消任務...", { variant: 'info' });
        } catch (error) {
            console.error("Failed to cancel job:", error);
            enqueueSnackbar("無法取消任務", { variant: 'error' });
        }
    }, [enqueueSnackbar]);

    const checkStatus = useCallback(async () => {
        if (!isAuthenticated) return;

        try {
            const res = await axios.get('/api/jobs/current');
            const job = res.data;

            if (job) {
                // If we have already processed this job's final state, skip it
                if (job.job_id === lastProcessedJobId.current && ['completed', 'failed', 'cancelled'].includes(job.status)) {
                    return;
                }

                // On first poll, if job is already finished, don't show notification, just track it
                if (isFirstPoll.current) {
                    isFirstPoll.current = false;
                    if (['completed', 'failed', 'cancelled'].includes(job.status)) {
                        lastProcessedJobId.current = job.job_id;
                        return;
                    }
                }
                isFirstPoll.current = false;

                setCurrentJob(job);

                if (job.status === 'completed') {
                    lastProcessedJobId.current = job.job_id;
                    enqueueSnackbar(`任務完成: ${job.type}`, { variant: 'success' });
                    getNotifications(); // Refresh notifications panel
                    setCurrentJob(null);
                    window.dispatchEvent(new CustomEvent('jobCompleted', { detail: job }));
                    if (snackbarKey.current) {
                        closeSnackbar(snackbarKey.current);
                        snackbarKey.current = null;
                    }
                } else if (job.status === 'failed') {
                    lastProcessedJobId.current = job.job_id;
                    enqueueSnackbar(`任務失敗: ${job.error}`, { variant: 'error' });
                    setCurrentJob(null);
                    window.dispatchEvent(new CustomEvent('jobFailed', { detail: job }));
                    if (snackbarKey.current) {
                        closeSnackbar(snackbarKey.current);
                        snackbarKey.current = null;
                    }
                } else if (job.status === 'cancelled') {
                    lastProcessedJobId.current = job.job_id;
                    enqueueSnackbar(`任務已取消`, { variant: 'info' });
                    setCurrentJob(null);
                    if (snackbarKey.current) {
                        closeSnackbar(snackbarKey.current);
                        snackbarKey.current = null;
                    }
                } else if (job.status === 'running' || job.status === 'pending') {
                    // Show persistent notification if not already shown
                    if (!snackbarKey.current) {
                        const key = enqueueSnackbar(
                            <Box display="flex" alignItems="center">
                                <CircularProgress size={20} sx={{ mr: 1, color: 'white' }} />
                                <Typography variant="body2" sx={{ mr: 2 }}>
                                    {job.message || '後端更新中請稍等...'}
                                </Typography>
                                <Button
                                    color="inherit"
                                    size="small"
                                    variant="outlined"
                                    onClick={() => cancelJob()}
                                    sx={{ borderColor: 'rgba(255,255,255,0.5)', color: 'white' }}
                                >
                                    取消
                                </Button>
                            </Box>,
                            {
                                variant: 'info',
                                persist: true,
                                anchorOrigin: { vertical: 'bottom', horizontal: 'right' }
                            }
                        );
                        snackbarKey.current = key;
                    }

                    // Smart Polling: schedule next check in 2 seconds
                    if (timeoutRef.current) clearTimeout(timeoutRef.current);
                    timeoutRef.current = setTimeout(checkStatus, 2000);
                }
            } else {
                // No job running
                if (currentJob) {
                    setCurrentJob(null);
                }
                if (snackbarKey.current) {
                    closeSnackbar(snackbarKey.current);
                    snackbarKey.current = null;
                }
            }
        } catch (error) {
            console.error("Error checking job status:", error);
        }
    }, [isAuthenticated, enqueueSnackbar, closeSnackbar, getNotifications, cancelJob]);

    // Check status on mount or auth change
    useEffect(() => {
        checkStatus();

        return () => {
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            if (snackbarKey.current) closeSnackbar(snackbarKey.current);
        };
    }, [checkStatus]);

    const startJob = async (jobType, params = {}) => {
        if (currentJob) {
            enqueueSnackbar("後端更新中請稍等", { variant: 'warning' });
            return false;
        }

        try {
            await axios.post('/api/jobs/start', { job_type: jobType, params });
            // Start polling immediately
            if (timeoutRef.current) clearTimeout(timeoutRef.current);
            checkStatus();
            return true;
        } catch (error) {
            console.error("Failed to start job:", error);
            enqueueSnackbar(`無法啟動任務: ${error.response?.data?.detail || error.message}`, { variant: 'error' });
            return false;
        }
    };

    return (
        <JobContext.Provider value={{ currentJob, startJob, cancelJob }}>
            {children}
        </JobContext.Provider>
    );
};
