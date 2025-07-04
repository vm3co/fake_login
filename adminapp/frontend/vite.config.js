import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      injectRegister: "auto",
      registerType: "autoUpdate",
      workbox: { clientsClaim: true, skipWaiting: true }
    })
  ],
  build: {
    chunkSizeWarningLimit: 2000
  },
  resolve: {
    alias: {
      app: path.resolve(__dirname, "src/app")
    }
  },
});



//------------------------------------------------//

// // 測試模式


// import path from "path";
// import { defineConfig } from "vite";
// import react from "@vitejs/plugin-react";

// export default defineConfig({
//   plugins: [react()],
//   server: {
//     proxy: {
//       '/api': {
//         target: 'http://localhost:8091',  // 您的後端地址
//         changeOrigin: true,
//         // 如果後端還沒準備好，可以暫時模擬
//         configure: (proxy, options) => {
//           proxy.on('error', (err, req, res) => {
//             console.log('proxy error', err);
//           });
//         }
//       }
//     }
//   },
//   resolve: {
//     alias: {
//       app: path.resolve(__dirname, "src/app")  // 重要：加入這個路徑別名
//     }
//   }
// });