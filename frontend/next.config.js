/** @type {import('next').NextConfig} */
const nextConfig = {
  // Deprecated: Next.js no longer supports the `eslint` config here.
  // Use `next lint` or set NEXT_DISABLE_ESLINT=1 in your build environment.
  // eslint: {
  //   // WARNING: This allows production builds to successfully complete even if
  //   // your project has ESLint errors.
  //   ignoreDuringBuilds: true,
  // },
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'img.clerk.com',
      },
      {
        protocol: 'https',
        hostname: 'images.clerk.dev',
      },
    ],
  },
  async redirects() {
    return [
      {
        source: '/v2',
        destination: '/',
        permanent: false,
      },
      {
        source: '/v2/:path*',
        destination: '/:path*',
        permanent: false,
      },
    ];
  },
}

module.exports = nextConfig 