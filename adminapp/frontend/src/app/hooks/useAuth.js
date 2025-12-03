import { useContext } from "react";
// import AuthContext from "app/contexts/FirebaseAuthContext";
import AuthContext from "app/contexts/JWTAuthContext";
import navigations from "app/navigations";

export default function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }


  const filteredNavigations = navigations.filter((nav) => {
    // 根據使用者身分過濾導覽項目
    if (nav.auth === "admin") {
      return context.user?.name === "admin@acercsi.com";
    }
    return true;
  });

  // 回傳原始 context 內容，並加上過濾後的導覽項目
  return { ...context, navigations: filteredNavigations };
}
