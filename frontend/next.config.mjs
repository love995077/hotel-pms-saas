/** @type {import('next').NextConfig} */
const nextConfig = {
  // The browser only ever talks to this origin; Next forwards /api to FastAPI.
  // That keeps the backend off the public CORS surface.
  async rewrites() {
    const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
