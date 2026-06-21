import type { NextConfig } from "next";

// Set NEXT_EXPORT=true for the Cloudflare Pages build (static export, no Node server).
// In dev we keep the rewrite proxy so the client can call relative /api/* without CORS.
const isExport = process.env.NEXT_EXPORT === "true";

const nextConfig: NextConfig = {
  ...(isExport ? { output: "export" } : {}),
  images: { unoptimized: true },
  async rewrites() {
    if (isExport) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_URL ?? "http://127.0.0.1:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
