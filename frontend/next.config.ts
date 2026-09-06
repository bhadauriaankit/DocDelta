import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // "standalone" produces a self-contained server bundle in .next/standalone
  // with only the node_modules it actually needs traced in — this keeps the
  // Docker production image small instead of shipping the full node_modules.
  output: "standalone",
};

export default nextConfig;
