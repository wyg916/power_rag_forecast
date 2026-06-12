import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget = process.env.VITE_API_PROXY_TARGET || process.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  build: {
    chunkSizeWarningLimit: 1400,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('echarts-for-react')) return 'vendor-echarts-react';
          if (id.includes('echarts')) return 'vendor-echarts';
          if (id.includes('zrender')) return 'vendor-zrender';
          if (id.includes('antd') || id.includes('@ant-design') || id.includes('/rc-') || id.includes('@rc-component')) return 'vendor-antd';
          return undefined;
        }
      }
    }
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': apiProxyTarget
    }
  }
});
