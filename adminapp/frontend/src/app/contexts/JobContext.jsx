import { createContext, useContext } from 'react';
import axios from 'axios';
import { useSnackbar } from 'notistack';

const JobContext = createContext({
    startJob: () => Promise.resolve(false),
});

export const useJob = () => useContext(JobContext);

export const JobProvider = ({ children }) => {
    const { enqueueSnackbar } = useSnackbar();

    const startJob = async (jobType, params = {}) => {
        try {
            const { data } = await axios.post('/api/jobs/start', { job_type: jobType, params });
            const excludedCount = data.excluded?.length || 0;
            enqueueSnackbar(
                excludedCount
                    ? `開始更新，${excludedCount} 筆重複任務已排除；詳情請到小鈴鐺觀看`
                    : '開始更新，詳情請到小鈴鐺觀看',
                { variant: excludedCount ? 'warning' : 'info' }
            );
            window.dispatchEvent(new CustomEvent('jobsChanged'));
            return data;
        } catch (error) {
            console.error('Failed to start job:', error);
            enqueueSnackbar(`無法啟動任務: ${error.response?.data?.detail || error.message}`, { variant: 'error' });
            return false;
        }
    };

    return (
        <JobContext.Provider value={{ startJob }}>
            {children}
        </JobContext.Provider>
    );
};
