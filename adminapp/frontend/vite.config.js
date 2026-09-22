import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:80',
        changeOrigin: true,

        // rewrite: (path) => path.replace(/^\/api/, '/admin/api'),

        configure: (proxy) => {
          proxy.on('error', (err) => {
            console.log('proxy error', err);
          });
        }
      }
    }
  },
  resolve: {
    alias: {
      app: path.resolve(__dirname, "src/app")
    }
  }
});