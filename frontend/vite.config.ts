import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const allowedFrameOrigins =
    env.VITE_FRAME_SRC_ALLOWLIST ||
    process.env.VITE_FRAME_SRC_ALLOWLIST ||
    "http://localhost:8000 http://127.0.0.1:8000 http://localhost:8080 http://127.0.0.1:8080 http://localhost:8081 http://127.0.0.1:8081 http://localhost:8082 http://127.0.0.1:8082 https://lms.vibesandbox.live https://quiz.digielvestech.in http://localhost:5173 http://127.0.0.1:5173 http://localhost:5174 http://127.0.0.1:5174 http://localhost:6395 http://127.0.0.1:6395 https://hrms.vibesandbox.live https://*.vibesandbox.live https://excelreports.vibecopilot.ai";

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

  return {
    plugins: [react()],
    server: {
      port: 6392,
      strictPort: true,
      headers: {
        "Content-Security-Policy": cspHeader,
        "Permissions-Policy": permissionsPolicy,
      },
    },
    preview: {
      port: 6392,
      strictPort: true,
      headers: {
        "Content-Security-Policy": cspHeader,
        "Permissions-Policy": permissionsPolicy,
      },
    },
  };
});
