import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import { useSnackbar } from 'notistack';
import useAuth from 'app/hooks/useAuth';

const ACTIVE_STATUSES = new Set(['queued', 'claiming', 'running', 'cancel_requested']);
const FAILED_STATUSES = new Set(['failed', 'interrupted']);
const TERMINAL_STATUSES = new Set(['completed', 'partial', 'failed', 'cancelled', 'interrupted']);

const JobContext = createContext({
    manualJobs: [],
    activeCount: 0,
    unseenCompletedCount: 0,
    hasUnseenFailure: false,
    jobsLoading: false,
    startJob: () => Promise.resolve(false),
    refreshManualJobs: () => Promise.resolve(),
    markManualJobsSeen: () => {},
});

export const useJob = () => useContext(JobContext);

const jobSummary = (job) => {
    const result = job.result || {};
    const succeeded = result.updated_count ?? result.successful_tasks?.length ?? 0;
    const skipped = result.skipped_count ?? result.skipped_tasks?.length ?? 0;
    const failed = result.failed_count ?? result.failed_tasks?.length ?? 0;
    if (job.status === 'completed') return [`更新完成：成功 ${succeeded} 筆，跳過 ${skipped} 筆`, 'success'];
    if (job.status === 'partial') return [`更新部分完成：成功 ${succeeded} 筆，失敗 ${failed} 筆`, 'warning'];
    if (job.status === 'failed') return [`更新失敗：${job.error || `${failed} 筆任務無法更新`}`, 'error'];
    if (job.status === 'interrupted') return ['更新已中斷，請重新送出任務', 'error'];
    return [`更新已取消：已完成 ${succeeded} 筆，其餘停止`, 'info'];
};

export const JobProvider = ({ children }) => {
    const { enqueueSnackbar } = useSnackbar();
    const { isAuthenticated, user } = useAuth();
    const [manualJobs, setManualJobs] = useState([]);
    const [jobsLoading, setJobsLoading] = useState(false);
    const [seenSequence, setSeenSequence] = useState(0);
    const manualJobsRef = useRef([]);
    const previousItemsRef = useRef(new Map());
    const previousJobsRef = useRef(new Map());
    const initializedRef = useRef(false);
    const timeoutRef = useRef(null);
    const refreshInFlightRef = useRef(null);
    const refreshQueuedRef = useRef(false);
    const username = user?.name;
    const seenStorageKey = username ? `jobCenter:lastSeen:${username}` : null;

    const fetchManualJobs = useCallback(async ({ silent = true } = {}) => {
        if (!isAuthenticated || !username) return [];
        if (!silent) setJobsLoading(true);
        try {
            const { data } = await axios.get('/api/jobs', { params: { source: 'manual' } });
            const visibleJobs = (Array.isArray(data) ? data : []).filter((job) => job.owner_username === username);
            const nextItems = new Map();
            const nextJobs = new Map();
            const completedUuids = new Set();

            visibleJobs.forEach((job) => {
                nextJobs.set(job.job_id, job.status);
                (job.items || []).forEach((item) => {
                    const key = `${job.job_id}:${item.sendtask_uuid}`;
                    nextItems.set(key, item.status);
                    const previousStatus = previousItemsRef.current.get(key);
                    if (initializedRef.current && item.status === 'completed' && previousStatus !== 'completed') {
                        completedUuids.add(item.sendtask_uuid);
                    }
                });

                const previousStatus = previousJobsRef.current.get(job.job_id);
                if (initializedRef.current && TERMINAL_STATUSES.has(job.status) && ACTIVE_STATUSES.has(previousStatus)) {
                    const [message, variant] = jobSummary(job);
                    enqueueSnackbar(message, { variant });
                }
            });

            if (completedUuids.size) {
                window.dispatchEvent(new CustomEvent('jobItemsCompleted', {
                    detail: { uuids: [...completedUuids] }
                }));
            }

            previousItemsRef.current = nextItems;
            previousJobsRef.current = nextJobs;
            initializedRef.current = true;
            manualJobsRef.current = visibleJobs;
            setManualJobs(visibleJobs);
            return visibleJobs;
        } catch (error) {
            console.error('Failed to refresh manual jobs:', error);
            return [];
        } finally {
            if (!silent) setJobsLoading(false);
        }
    }, [enqueueSnackbar, isAuthenticated, username]);

    const refreshManualJobs = useCallback(async (options = {}) => {
        if (refreshInFlightRef.current) {
            refreshQueuedRef.current = true;
            return refreshInFlightRef.current;
        }

        const runRefresh = async () => {
            let jobs = [];
            do {
                refreshQueuedRef.current = false;
                jobs = await fetchManualJobs(options);
            } while (refreshQueuedRef.current);
            return jobs;
        };

        refreshInFlightRef.current = runRefresh();
        try {
            return await refreshInFlightRef.current;
        } finally {
            refreshInFlightRef.current = null;
        }
    }, [fetchManualJobs]);

    useEffect(() => {
        if (!seenStorageKey) {
            setSeenSequence(0);
            return;
        }
        setSeenSequence(Number(window.localStorage.getItem(seenStorageKey) || 0));
        initializedRef.current = false;
        previousItemsRef.current = new Map();
        previousJobsRef.current = new Map();
        refreshInFlightRef.current = null;
        refreshQueuedRef.current = false;
    }, [seenStorageKey]);

    useEffect(() => {
        if (!isAuthenticated || !username) {
            manualJobsRef.current = [];
            setManualJobs([]);
            return undefined;
        }

        let cancelled = false;

        const pollAndSchedule = async () => {
            const jobs = await refreshManualJobs();
            if (cancelled) return;
            const hasActive = jobs.some((job) => ACTIVE_STATUSES.has(job.status));
            const hasUnseen = jobs.some((job) => TERMINAL_STATUSES.has(job.status) && job.queue_position > seenSequence);
            const delay = document.hidden ? 30000 : hasActive ? 2000 : hasUnseen ? 15000 : 60000;
            timeoutRef.current = window.setTimeout(pollAndSchedule, delay);
        };
        pollAndSchedule();

        const syncNow = () => {
            if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
            pollAndSchedule();
        };
        const handleVisibility = () => { if (!document.hidden) syncNow(); };
        window.addEventListener('focus', syncNow);
        window.addEventListener('jobsChanged', syncNow);
        document.addEventListener('visibilitychange', handleVisibility);
        return () => {
            cancelled = true;
            if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
            window.removeEventListener('focus', syncNow);
            window.removeEventListener('jobsChanged', syncNow);
            document.removeEventListener('visibilitychange', handleVisibility);
        };
    }, [isAuthenticated, refreshManualJobs, seenSequence, username]);

    const markManualJobsSeen = useCallback(() => {
        const latestSequence = manualJobsRef.current.reduce(
            (maximum, job) => Math.max(maximum, job.queue_position || 0),
            0
        );
        setSeenSequence(latestSequence);
        if (seenStorageKey) window.localStorage.setItem(seenStorageKey, String(latestSequence));
    }, [seenStorageKey]);

    const startJob = async (jobType, params = {}) => {
        try {
            const { data } = await axios.post('/api/jobs/start', { job_type: jobType, params });
            const acceptedCount = data.accepted?.length || 0;
            const excludedCount = data.excluded?.length || 0;
            let message = '更新任務已送出，詳情請到小鈴鐺查看';
            let variant = 'info';
            if (!acceptedCount && excludedCount) {
                message = `未啟動新的更新：${excludedCount} 筆任務皆已在其他工作中處理`;
                variant = 'warning';
            } else if (excludedCount) {
                message = `更新任務已送出：執行 ${acceptedCount} 筆，排除重複 ${excludedCount} 筆`;
                variant = 'warning';
            }
            enqueueSnackbar(message, { variant });
            window.dispatchEvent(new CustomEvent('jobsChanged'));
            return data;
        } catch (error) {
            console.error('Failed to start job:', error);
            enqueueSnackbar(`無法啟動任務: ${error.response?.data?.detail || error.message}`, { variant: 'error' });
            return false;
        }
    };

    const activeCount = manualJobs.filter((job) => ACTIVE_STATUSES.has(job.status)).length;
    const unseenTerminalJobs = manualJobs.filter((job) => (
        TERMINAL_STATUSES.has(job.status) && (job.queue_position || 0) > seenSequence
    ));
    const hasUnseenFailure = unseenTerminalJobs.some((job) => FAILED_STATUSES.has(job.status));
    const unseenCompletedCount = unseenTerminalJobs.filter((job) => !FAILED_STATUSES.has(job.status)).length;

    return (
        <JobContext.Provider value={{
            manualJobs,
            activeCount,
            unseenCompletedCount,
            hasUnseenFailure,
            jobsLoading,
            startJob,
            refreshManualJobs,
            markManualJobsSeen,
        }}>
            {children}
        </JobContext.Provider>
    );
};
