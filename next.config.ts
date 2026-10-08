import type { NextConfig } from "next";

// Static export for GitHub Pages (https://jagon7.github.io/jagon-space-station/).
// PAGES_BASE_PATH is set by the deploy workflow; leave it unset for local dev.
const basePath = process.env.PAGES_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  basePath,
  images: { unoptimized: true },
};

export default nextConfig;
