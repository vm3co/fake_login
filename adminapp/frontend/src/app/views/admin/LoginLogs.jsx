import {
    Box,
    Card,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    styled,
    Typography
} from "@mui/material";
import { Breadcrumb, SimpleCard } from "app/components";
import { useEffect, useState } from "react";
import axios from "axios";

const Container = styled("div")(({ theme }) => ({
    margin: "30px",
    [theme.breakpoints.down("sm")]: { margin: "16px" },
    "& .breadcrumb": {
        marginBottom: "30px",
        [theme.breakpoints.down("sm")]: { marginBottom: "16px" }
    }
}));

const LoginLogs = () => {
    const [logs, setLogs] = useState([]);

    useEffect(() => {
        // 取得資料
        const fetchLogs = async () => {
            try {
                const accessToken = window.localStorage.getItem("accessToken");
                const response = await axios.get("/api/auth/logs", {
                    headers: {
                        Authorization: `Bearer ${accessToken}`
                    }
                });
                setLogs(response.data);
            } catch (error) {
                console.error("Error fetching logs:", error);
            }
        };

        fetchLogs();
    }, []);

    return (
        <Container>
            <Box className="breadcrumb">
                <Breadcrumb routeSegments={[{ name: "平台設定", path: "/admin/logs" }, { name: "登入登出紀錄" }]} />
            </Box>

            <SimpleCard title="登入登出紀錄 (最近 100 筆)">
                <Box overflow="auto">
                    <Table sx={{ whiteSpace: "pre", minWidth: 600 }}>
                        <TableHead>
                            <TableRow>
                                <TableCell>使用者</TableCell>
                                <TableCell>動作</TableCell>
                                <TableCell>狀態</TableCell>
                                <TableCell>IP 位址</TableCell>
                                <TableCell>詳細資訊</TableCell>
                                <TableCell>時間</TableCell>
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {logs.map((log) => (
                                <TableRow key={log.id}>
                                    <TableCell>{log.username}</TableCell>
                                    <TableCell>
                                        {log.action === "login" ? "登入" : "登出"}
                                    </TableCell>
                                    <TableCell>
                                        <Typography color={log.status === "success" ? "green" : "red"}>
                                            {log.status === "success" ? "成功" : "失敗"}
                                        </Typography>
                                    </TableCell>
                                    <TableCell>{log.ip_address}</TableCell>
                                    <TableCell>{log.details}</TableCell>
                                    <TableCell>
                                        {new Date(log.create_time).toLocaleString("zh-TW")}
                                    </TableCell>
                                </TableRow>
                            ))}
                        </TableBody>
                    </Table>
                </Box>
            </SimpleCard>
        </Container>
    );
};

export default LoginLogs;
