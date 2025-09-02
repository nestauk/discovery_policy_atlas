/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // WARNING: This allows production builds to successfully complete even if
    // your project has ESLint errors.
    ignoreDuringBuilds: true,
  },
  images: {
    domains: ['img.clerk.com', 'images.clerk.dev'],
  },
}

module.exports = nextConfig 