const { NextFederationPlugin } = require('@module-federation/nextjs-mf');

module.exports = {
  webpack(config, options) {
    config.plugins.push(
      new NextFederationPlugin({
        name: 'profile',
        filename: 'static/chunks/remoteEntry.js',
        exposes: {
          './ProfileApp': './components/ProfileApp',
        },
        shared: {},
      })
    );
    return config;
  },
  output: 'standalone',
};
