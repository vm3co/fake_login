import { createContext, useEffect, useReducer } from "react";
import { useSnackbar } from 'notistack';
import { jwtDecode } from "jwt-decode";
import axios from "axios";
// GLOBAL CUSTOM COMPONENTS
import Loading from "app/components/MatxLoading";

const isValidToken = (accessToken) => {
  if (!accessToken) return false;

  try {
    const decodedToken = jwtDecode(accessToken);
    
    // 檢查 token 是否過期
    const currentTime = Date.now() / 1000;
    if (decodedToken.exp && decodedToken.exp < currentTime) {
      console.log("Token expired");
      return false;
    }
    
    return decodedToken?.username ? true : false;
  } catch (error) {
    console.error("Token decode error:", error);
    return false;
  }
};

const setSession = (accessToken) => {
  if (accessToken) {
    localStorage.setItem("accessToken", accessToken);
    axios.defaults.headers.common.Authorization = `Bearer ${accessToken}`;
  } else {
    localStorage.removeItem("accessToken");
    delete axios.defaults.headers.common.Authorization;
  }
};

// 設定使用者相關的 cookie
const setUserCookies = (user) => {
  if (!user) return;

  // 根據使用者類型設定不同的 cookie
  if (user.user_type === "user" || user.user_type === "admin") {
    // 一般使用者或管理員：設定 orgs 和 acct_uuid
    const orgs = user.orgs || [];
    document.cookie = `orgs=${encodeURIComponent(JSON.stringify(orgs))}; path=/;`;
    document.cookie = `acct_uuid=${encodeURIComponent(user.acct_uuid)}; path=/;`;
    
    // 清除客戶相關的 cookie（如果存在）
    document.cookie = "sendtasks=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";

  } else if (user.user_type === "customer") {
    // 客戶：設定 sendtasks 和 acct_uuid
    const sendtasks = user.sendtasks || [];
    document.cookie = `sendtasks=${encodeURIComponent(JSON.stringify(sendtasks))}; path=/;`;
    document.cookie = `acct_uuid=${encodeURIComponent(user.acct_uuid)}; path=/;`;
    
    // 清除一般使用者相關的 cookie（如果存在）
    document.cookie = "orgs=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  }
};

// 清除所有使用者相關的 cookie
const clearUserCookies = () => {
  document.cookie = "orgs=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.cookie = "acct_uuid=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.cookie = "sendtasks=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
};

const reducer = (state, action) => {
  switch (action.type) {
    case "INIT": {
      const { isAuthenticated, user } = action.payload;
      return { ...state, user, isAuthenticated, isInitialized: true };
    }
    case "LOGIN": {
      const { user } = action.payload;
      return { ...state, user, isAuthenticated: true };
    }
    case "LOGOUT": {
      return { ...state, isAuthenticated: false, user: null };
    }
    case "REGISTER": {
      const { user } = action.payload;
      return { ...state, isAuthenticated: true, user };
    }
    default: {
      return state;
    }
  }
};

const initialState = {
  user: null,
  isInitialized: false,
  isAuthenticated: false
};


const AuthContext = createContext({
  ...initialState,
  method: "JWT"
});

export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, initialState);
  const { enqueueSnackbar } = useSnackbar();

  const login = async (username, password) => {
    try {
      const { data } = await axios.post("/api/auth/login", { username, password });

      if (data.status !== "success") {
        enqueueSnackbar(data.message || "登入失敗，請檢查帳號密碼是否正確", { variant: 'error' });
        return;
      }

      const { accessToken, user } = data;

      if (!accessToken) {
        enqueueSnackbar("登入失敗：無法從伺服器獲取授權。", { variant: 'error' });
        return;
      }

      setSession(accessToken);
      setUserCookies(user);
      dispatch({ type: "LOGIN", payload: { user } });

    } catch (error) {
      console.error("登入錯誤:", error);
      enqueueSnackbar("登入過程中發生錯誤，請稍後再試", { variant: 'error' });
    }
  };

  const register = async (username, password) => {
    try {
      const { data } = await axios.post("/api/auth/register", { username, password });
      if (data.status !== "success") {
        enqueueSnackbar(data.message || "註冊失敗，請檢查輸入的資料是否正確", { variant: 'error' });
        return;
      }
      
      const { accessToken, user } = data;

      setSession(accessToken);

      // 註冊成功後設定相應的 cookie
      setUserCookies(user);

      dispatch({ type: "REGISTER", payload: { user } });
    } catch (error) {
      console.error("註冊錯誤:", error);
      enqueueSnackbar("註冊過程中發生錯誤，請稍後再試", { variant: 'error' });
    }
  };

  const logout = () => {
    setSession(null);
    // 清除所有使用者相關的 cookie
    clearUserCookies();
    dispatch({ type: "LOGOUT" });
  };

  // 手動更新使用者 cookie（用於資料更新時）
  const updateUserCookies = (updatedUser) => {
    if (updatedUser) {
      setUserCookies(updatedUser);
      dispatch({ type: "LOGIN", payload: { user: updatedUser } });
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const accessToken = window.localStorage.getItem("accessToken");
        
        if (accessToken && isValidToken(accessToken)) {
          setSession(accessToken);

          const response = await axios.get("/api/auth/profile");
          const { user } = response.data;

          if (!user) {
            console.error("User data not found in response");
            throw new Error("User data not found");
          }

          setUserCookies(user);
          dispatch({ type: "INIT", payload: { isAuthenticated: true, user } });

        } else {
          setSession(null);
          clearUserCookies();
          dispatch({ type: "INIT", payload: { isAuthenticated: false, user: null } });
        }
      } catch (err) {
        console.error("Auth initialization error:", err);
        setSession(null);
        clearUserCookies();
        dispatch({ type: "INIT", payload: { isAuthenticated: false, user: null } });
      }
    })();
  }, []);

  if (!state.isInitialized) return <Loading />;

  return (
    <AuthContext.Provider 
      value={{ 
        ...state, 
        method: "JWT", 
        login, 
        logout, 
        register,
        updateUserCookies  // 提供更新 cookie 的方法
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
