/** @type {import('next').NextConfig} */
const nextConfig = {
  // Enable standalone output for Docker builds
  output: process.env.DOCKER_BUILD ? 'standalone' : undefined,

  images: { unoptimized: true },

  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
    NEXT_PUBLIC_NODE_API_URL: process.env.NEXT_PUBLIC_NODE_API_URL || 'http://localhost:4000',
  },

  async redirects() {
    return [
      // Governance and inspections pages replaced by AI Chat and Grid Map
      { source: '/governance',  destination: '/dashboard', permanent: false },
      { source: '/inspections', destination: '/analysis',  permanent: false },
      { source: '/ghi',         destination: '/dashboard', permanent: false },
    ]
  },
}

module.exports = nextConfig
