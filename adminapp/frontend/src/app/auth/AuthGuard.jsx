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
          window.location.href = "/customer";
          return;
        }
      }
      if (user.user_type === "platform_admin") {
        // 平台管理員只能訪問 /admin/* 頁面
        if (!pathname.startsWith("/admin")) {
          window.location.href = "/admin/announcement";
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
