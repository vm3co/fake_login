import { useContext } from "react";
import AuthContext from "app/contexts/JWTAuthContext";
import navigations from "app/navigations";

export default function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }

  const userType = context.user?.user_type;

  const filteredNavigations = navigations.filter((nav) => {
    // platform_admin：只看平台設定
    if (userType === "platform_admin") {
      return nav.auth === "platform_admin";
    }
    // admin (.env 超級管理員)：看除了平台設定以外的所有項目
    if (userType === "admin") {
      return nav.auth !== "platform_admin";
    }
    // 其他使用者：只看沒有 auth 限制的項目
    return !nav.auth;
  });

  return { ...context, navigations: filteredNavigations };
}
