import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Static export only — there is no server in this project.
  output: "export",
  images: { unoptimized: true },
  webpack: (config) => {
    // The engine is a wasm bundle imported from src/wasm.
    config.experiments = { ...config.experiments, asyncWebAssembly: true, layers: true };
    return config;
  },
};

export default nextConfig;
