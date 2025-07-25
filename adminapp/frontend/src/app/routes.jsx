import { lazy } from "react";
import { Navigate } from "react-router-dom";

import AuthGuard from "./auth/AuthGuard";
import { authRoles } from "./auth/authRoles";

import Loadable from "./components/Loadable";
import MatxLayout from "./components/MatxLayout/MatxLayout";
import sessionRoutes from "./views/sessions/session-routes";
import materialRoutes from "app/views/material-kit/MaterialRoutes";

// DASHBOARD PAGE
const Analytics = Loadable(lazy(() => import("app/views/dashboard/Analytics")));
// CUSTOMER PAGE
const Customers = Loadable(lazy(() => import("app/views/customers/Customers")));

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
      // customer route
      { path: "/customers", element: <Customers />, auth: authRoles.admin },
    ]
  },

  // session pages route
  ...sessionRoutes
];

export default routes;
