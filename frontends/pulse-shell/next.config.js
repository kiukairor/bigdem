const { NextFederationPlugin } = require('@module-federation/nextjs-mf');

module.exports = {
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
