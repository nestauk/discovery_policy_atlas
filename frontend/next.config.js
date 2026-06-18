/** @type {import('next').NextConfig} */
const nextConfig = {
  eslint: {
    // WARNING: This allows production builds to successfully complete even if
    // your project has ESLint errors.
    ignoreDuringBuilds: true,
  },
  // Keep Amplify's crypto deps out of the server bundle to avoid the
  // "Cannot get final name for export 'fromUtf8'" build error.
  serverExternalPackages: [
    '@aws-crypto',
    '@aws-amplify/adapter-nextjs',
    '@aws-amplify/core',
    'aws-amplify',
  ],
  images: {
    domains: ['img.clerk.com', 'images.clerk.dev'],
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