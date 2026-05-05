const { NextFederationPlugin } = require('@module-federation/nextjs-mf');

module.exports = {
  async rewrites() {
    return [
      // MFE remotes — proxied server-side so the browser stays on pulse.test
      { source: '/_mfe/feed/:path*',    destination: 'http://pulse-feed:3001/:path*' },
      { source: '/_mfe/profile/:path*', destination: 'http://pulse-profile:3002/:path*' },
      // Backend APIs — same-origin from the browser's perspective, no CORS needed
      { source: '/api/event-svc/:path*',  destination: 'http://event-svc:8080/:path*' },
      { source: '/api/ai-svc/:path*',     destination: 'http://ai-svc:8082/:path*' },
      { source: '/api/session-svc/:path*', destination: 'http://session-svc:8081/:path*' },
      { source: '/api/test-svc/:path*',   destination: 'http://test-svc:8090/:path*' },
    ];
  },
  webpack(config, options) {
    config.plugins.push(
      new NextFederationPlugin({
        name: 'shell',
        filename: 'static/chunks/remoteEntry.js',
        remotes: {
          feed: `feed@${process.env.NEXT_PUBLIC_FEED_MFE_URL || 'http://localhost:3001'}/_next/static/chunks/remoteEntry.js`,
          profile: `profile@${process.env.NEXT_PUBLIC_PROFILE_MFE_URL || 'http://localhost:3002'}/_next/static/chunks/remoteEntry.js`,
        },
        shared: {},
      })
    );
    return config;
  },
  output: 'standalone',
};
