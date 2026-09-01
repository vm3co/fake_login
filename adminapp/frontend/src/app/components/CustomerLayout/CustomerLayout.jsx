import { Box, AppBar, Toolbar, Typography, Button } from '@mui/material';
import { Outlet } from 'react-router-dom';
import Footer from "app/components/Footer";

import useAuth from 'app/hooks/useAuth';

export default function CustomerLayout() {
  const { user, logout } = useAuth();

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', minHeight: '100vh' }}>
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            社交工程客戶系統
          </Typography>
          <Box>
            <Typography 
              variant="h6" 
              component="div" 
              sx={{ 
                mr: 2, 
                fontWeight: 'bold', 
                fontFamily: 'Noto Sans TC, sans-serif' 
              }}
            >
              Hi, {user?.full_name || user?.name}
            </Typography>     
          </Box>     
          <Button color="inherit" onClick={logout}>
            登出
          </Button>
        </Toolbar>
      </AppBar>
      
      <Box component="main" sx={{ flexGrow: 1, p: 3 }}>
        <Outlet />
      </Box>
      
      <Footer />
    </Box>
  );
}