import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  base: '/console/',
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/openapi.json': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) {
            return undefined;
          }
          if (id.includes('react-router-dom') || id.includes('react-dom') || id.includes('/react/')) {
            return 'react-core';
          }
          if (
            id.includes('/antd/') ||
            id.includes('@ant-design/') ||
            id.includes('/rc-') ||
            id.includes('@rc-component/')
          ) {
            return 'antd-core';
          }
          if (id.includes('@ant-design/icons')) {
            return 'antd-icons';
          }
          if (id.includes('/recharts/')) {
            return 'charts';
          }
          if (id.includes('/react-markdown/')) {
            return 'markdown';
          }
          if (id.includes('/axios/')) {
            return 'network';
          }
          if (id.includes('/dayjs/')) {
            return 'time';
          }
          if (id.includes('/zustand/')) {
            return 'state';
          }
          return undefined;
        },
      },
    },
  },
});
