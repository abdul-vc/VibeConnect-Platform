import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const allowedFrameOrigins =
  process.env.VITE_FRAME_SRC_ALLOWLIST ||
  "http://localhost:8080 http://127.0.0.1:8080 https://hrms.vibesandbox.live https://*.vibesandbox.live https://excelreports.vibecopilot.ai";

const cspHeader = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self' data:",
  "img-src 'self' data: https:",
  "connect-src 'self' http://localhost:* http://127.0.0.1:* ws://localhost:* ws://127.0.0.1:*",
  `frame-src 'self' ${allowedFrameOrigins}`,
  "frame-ancestors 'none'",
  "object-src 'none'",
  "base-uri 'self'",
].join("; ");

const permissionsPolicy = "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()";

// https://vite.dev/config/ (reloaded env)
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 6392,
    strictPort: true,
    headers: {
      "Content-Security-Policy": cspHeader,
      "Permissions-Policy": permissionsPolicy,
    },
  },
  preview: {
    host: "0.0.0.0",
    port: 6392,
    strictPort: true,
    headers: {
      "Content-Security-Policy": cspHeader,
      "Permissions-Policy": permissionsPolicy,
    },
  },
});
