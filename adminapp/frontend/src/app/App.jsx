import { useRoutes } from "react-router-dom";
import CssBaseline from "@mui/material/CssBaseline";
// ROOT THEME PROVIDER
import { MatxTheme } from "./components";
// ALL CONTEXTS
import SettingsProvider from "./contexts/SettingsContext";
// import { AuthProvider } from "./contexts/FirebaseAuthContext";
import { AuthProvider } from "./contexts/JWTAuthContext";
// ROUTES
import routes from "./routes";
// Global styles
import "./App.css";
// FAKE SERVER
import "../__api__";


export default function App() {
  const content = useRoutes(routes);

  return (
    <SettingsProvider>
      <AuthProvider>
        <MatxTheme>
          <CssBaseline />
          {content}
        </MatxTheme>
      </AuthProvider>
    </SettingsProvider>
  );
}
