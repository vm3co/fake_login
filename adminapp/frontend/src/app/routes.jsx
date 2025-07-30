import { lazy } from "react";
import { Navigate } from "react-router-dom";

import AuthGuard from "./auth/AuthGuard";
import { authRoles } from "./auth/authRoles";

import Loadable from "./components/Loadable";
import MatxLayout from "./components/MatxLayout/MatxLayout";
import CustomerLayout from "./components/CustomerLayout/CustomerLayout";
import sessionRoutes from "./views/sessions/session-routes";
import materialRoutes from "app/views/material-kit/MaterialRoutes";

// DASHBOARD PAGE
const Analytics = Loadable(lazy(() => import("app/views/dashboard/Analytics")));
// CUSTOMERS PAGE
const Customers = Loadable(lazy(() => import("app/views/customers/Customers")));
// CHANGE PASSWORD PAGE
const ChangePassword = Loadable(lazy(() => import("app/views/changePassword/ChangePassword")));

// CUSTOMER PAGE
const Customer = Loadable(lazy(() => import("app/views/customer/Customer")));

const routes = [
  { path: "/", element: <Navigate to="dashboard/default" /> },
  {
    element: (
      <AuthGuard>
        <MatxLayout />
      </AuthGuard>
    ),
    children: [
      ...materialRoutes,
      // dashboard route
      { path: "/dashboard/default", element: <Analytics />, auth: authRoles.admin },
      // customers route
      { path: "/customers", element: <Customers />, auth: authRoles.admin },
      // change password route
      { path: "/change-password", element: <ChangePassword />, auth: authRoles.admin }
    ]
  },

  // 客戶專用路由
  {
    path: "/customer",
    element: (
      <AuthGuard>
        <CustomerLayout />
      </AuthGuard>
    ),
    children: [
      { path: "", element: <Customer /> }
      // 其他客戶專用路由...
    ]
  },

  // session pages route
  ...sessionRoutes
];

export default routes;
