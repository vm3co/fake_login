import {
    Box,
    Button,
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableRow,
    TableSortLabel,
    TextField,
    InputAdornment,
    styled,
    Typography
} from "@mui/material";
import SearchIcon from "@mui/icons-material/Search";
import { Breadcrumb, SimpleCard } from "app/components";
import { useEffect, useState, useMemo } from "react";
import axios from "axios";

const Container = styled("div")(({ theme }) => ({
    margin: "30px",
    [theme.breakpoints.down("sm")]: { margin: "16px" },
    "& .breadcrumb": {
        marginBottom: "30px",
        [theme.breakpoints.down("sm")]: { marginBottom: "16px" }
    }
}));

// 將 UTC 時間轉為本地時間字串（Asia/Taipei）
// 若後端回傳的字串不帶時區資訊，補上 Z 讓瀏覽器識別為 UTC
const formatLocalTime = (utcString) => {
    if (!utcString) return "";
    // 若字串結尾不是 Z / + / - 時區標記，視為 UTC 補上 Z
    const normalized = /[Z+\-]/.test(utcString.slice(-6)) ? utcString : utcString + "Z";
    const date = new Date(normalized);
    return date.toLocaleString("zh-TW", { timeZone: "Asia/Taipei" });
};

// 比較函式，用於排序
const descendingComparator = (a, b, orderBy) => {
    let aVal = a[orderBy];
    let bVal = b[orderBy];
    // 時間欄位轉為數字比較
    if (orderBy === "create_time") {
        aVal = new Date(aVal).getTime();
        bVal = new Date(bVal).getTime();
    }
    if (bVal < aVal) return -1;
    if (bVal > aVal) return 1;
    return 0;
};

const getComparator = (order, orderBy) =>
    order === "desc"
        ? (a, b) => descendingComparator(a, b, orderBy)
        : (a, b) => -descendingComparator(a, b, orderBy);

// 可排序的表頭欄位定義
const headCells = [
    { id: "username", label: "使用者" },
    { id: "action", label: "動作" },
    { id: "status", label: "狀態" },
    { id: "ip_address", label: "IP 位址" },
    { id: "details", label: "詳細資訊" },
    { id: "create_time", label: "時間" }
];

const LoginLogs = () => {
    const [logs, setLogs] = useState([]);
    const [searchUser, setSearchUser] = useState("");
    // 預設以時間降序排序（最新在上）
    const [order, setOrder] = useState("desc");
    const [orderBy, setOrderBy] = useState("create_time");

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

    // 點選表頭處理排序
    const handleSort = (property) => {
        const isAsc = orderBy === property && order === "asc";
        setOrder(isAsc ? "desc" : "asc");
        setOrderBy(property);
    };

    // 過濾 + 排序後的資料
    const filteredLogs = useMemo(() => {
        const keyword = searchUser.trim().toLowerCase();
        const filtered = keyword
            ? logs.filter((log) =>
                (log.username || "").toLowerCase().includes(keyword)
            )
            : logs;
        return [...filtered].sort(getComparator(order, orderBy));
    }, [logs, searchUser, order, orderBy]);

    return (
        <Container>
            <Box className="breadcrumb">
                <Breadcrumb routeSegments={[{ name: "平台設定", path: "/admin/logs" }, { name: "登入登出紀錄" }]} />
            </Box>

            <SimpleCard title="登入登出紀錄 (最近 100 筆)">
                {/* 使用者搜尋欄 */}
                <Box mb={2} display="flex" alignItems="center" gap={1}>
                    <TextField
                        size="small"
                        variant="outlined"
                        placeholder="搜尋使用者..."
                        value={searchUser}
                        onChange={(e) => setSearchUser(e.target.value)}
                        InputProps={{
                            startAdornment: (
                                <InputAdornment position="start">
                                    <SearchIcon fontSize="small" />
                                </InputAdornment>
                            )
                        }}
                    />
                    <Button
                        size="small"
                        variant="outlined"
                        onClick={() => setSearchUser("")}
                        disabled={!searchUser}
                    >
                        清除
                    </Button>
                </Box>

                <Box overflow="auto">
                    <Table sx={{ whiteSpace: "pre", minWidth: 600 }}>
                        <TableHead>
                            <TableRow>
                                {headCells.map((cell) => (
                                    <TableCell
                                        key={cell.id}
                                        sortDirection={orderBy === cell.id ? order : false}
                                    >
                                        <TableSortLabel
                                            active={orderBy === cell.id}
                                            direction={orderBy === cell.id ? order : "asc"}
                                            onClick={() => handleSort(cell.id)}
                                        >
                                            {cell.label}
                                        </TableSortLabel>
                                    </TableCell>
                                ))}
                            </TableRow>
                        </TableHead>
                        <TableBody>
                            {filteredLogs.map((log) => (
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
                                        {formatLocalTime(log.create_time)}
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
