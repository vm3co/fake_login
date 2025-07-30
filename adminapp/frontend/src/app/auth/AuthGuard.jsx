import { useEffect } from "react";
import { Navigate, useLocation } from "react-router-dom";
// HOOK
import useAuth from "app/hooks/useAuth";

export default function AuthGuard({ children }) {
  const { isAuthenticated, user } = useAuth();
  const { pathname } = useLocation();

  useEffect(() => {
    // 根據使用者類型進行路由重導
    if (isAuthenticated && user) {
      if (user.user_type === "customer") {
        // 客戶只能訪問特定頁面
        const allowedCustomerPaths = ["/customer", "/customer/profile"];
        if (!allowedCustomerPaths.some(path => pathname.startsWith(path))) {
          // 重導到客戶專用頁面
          window.location.href = "/customer";
          return;
        }
      }
    }
  }, [isAuthenticated, user, pathname]);

  return (
    <>
      {isAuthenticated ? (
        children
      ) : (
        <Navigate replace to="/session/signin" state={{ from: pathname }} />
      )}
    </>
  );
}
