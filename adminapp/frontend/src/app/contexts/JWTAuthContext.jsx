import { createContext, useEffect, useReducer } from "react";
import { jwtDecode } from "jwt-decode";
import axios from "axios";
// GLOBAL CUSTOM COMPONENTS
import Loading from "app/components/MatxLoading";

const initialState = {
  user: null,
  isInitialized: false,
  isAuthenticated: false
};

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
    
    return decodedToken?.email ? true : false;
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

const AuthContext = createContext({
  ...initialState,
  method: "JWT"
});

export const AuthProvider = ({ children }) => {
  const [state, dispatch] = useReducer(reducer, initialState);

  const login = async (email, password) => {
    const { data } = await axios.post("/api/auth/login", { email, password });
    // 如果data.status回傳不是success，則彈跳視窗提示帳號密碼錯誤
    if (data.status !== "success") {
      alert(data.msg || "登入失敗，請檢查帳號密碼是否正確");
      return;
    }

    const { accessToken, user } = data;

    setSession(accessToken);

    // orgs 存成 cookie
    const orgs = user.orgs || [];
    document.cookie = `orgs=${encodeURIComponent(JSON.stringify(orgs))}; path=/;`;
    
    dispatch({ type: "LOGIN", payload: { user } });
  };

  const register = async (email, password) => {
    const { data } = await axios.post("/api/auth/register", { email, password });
    if (data.status !== "success") {
      alert(data.msg || "註冊失敗，請檢查輸入的資料是否正確");
      return;
    }
    
    const { accessToken, user } = data;

    setSession(accessToken);

    dispatch({ type: "REGISTER", payload: { user } });
  };

  const logout = () => {
    setSession(null);
    // 清除 orgs cookie
    document.cookie = "orgs=; path=/;";
    dispatch({ type: "LOGOUT" });
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

          dispatch({
            type: "INIT",
            payload: { isAuthenticated: true, user }
          });
        } else {
          console.log("Invalid or missing token");
          dispatch({
            type: "INIT",
            payload: { isAuthenticated: false, user: null }
          });
        }
      } catch (err) {
        console.error("Auth initialization error:", err);
        // 清除無效的 token
        setSession(null);
        dispatch({
          type: "INIT",
          payload: { isAuthenticated: false, user: null }
        });
      }
    })();
  }, []);

  if (!state.isInitialized) return <Loading />;

  return (
    <AuthContext.Provider value={{ ...state, method: "JWT", login, logout, register }}>
      {children}
    </AuthContext.Provider>
  );
};

export default AuthContext;
