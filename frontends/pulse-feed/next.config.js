const { NextFederationPlugin } = require('@module-federation/nextjs-mf');

module.exports = {
  webpack(config, options) {
    config.plugins.push(
      new NextFederationPlugin({
        name: 'feed',
        filename: 'static/chunks/remoteEntry.js',
        exposes: {
          './FeedApp': './components/FeedApp',
        },
        shared: {},
      })
    );
    return config;
  },
  output: 'standalone',
};
