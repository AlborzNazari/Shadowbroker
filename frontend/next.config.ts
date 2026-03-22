import type { NextConfig } from "next";

// /api/* requests are proxied to the backend by the catch-all route handler at
// src/app/api/[...path]/route.ts, which reads BACKEND_URL at request time.
// Do NOT add rewrites for /api/* here — next.config is evaluated at build time,
// so any URL baked in here ignores the runtime BACKEND_URL env var.

const nextConfig: NextConfig = {
  transpilePackages: ['react-map-gl', 'mapbox-gl', 'maplibre-gl'],
  output: "standalone",
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          {
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              // MapLibre GL / WebGL requires 'unsafe-eval' for shader compilation
              "script-src 'self' 'unsafe-eval' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              // MapLibre tiles, Sentinel imagery, CCTV camera images, external data
              "img-src 'self' data: blob: https: http:",
              // WebGL workers use blob: URLs
              "worker-src 'self' blob:",
              "child-src 'self' blob:",
              // API calls to backend + tile servers + external feeds
              "connect-src 'self' http://localhost:8000 ws://localhost:8000 https: http:",
              "font-src 'self' data:",
              "media-src 'self' https: http:",
              "frame-src 'self'",
            ].join("; "),
          },
        ],
      },
    ];
  },
};

export default nextConfig;
