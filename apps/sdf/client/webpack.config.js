const path = require('path');
const HtmlWebpackPlugin = require('html-webpack-plugin');

var vtkRules = require('vtk.js/Utilities/config/dependency.js').webpack.core.rules;
const plugins = [
  new HtmlWebpackPlugin({
    inject: 'body',
  }),
];

var entry = path.join(__dirname, './src/index.js');
const sourcePath = path.join(__dirname, './src');
const outputPath = path.join(__dirname, '../www');

module.exports = {
  plugins,
  entry,
  output: {
    path: outputPath,
    filename: 'sdfFuryWebClient.js',
    libraryTarget: 'umd',
  },
  module: {
    rules: [
     { test: entry,
       loader: "expose-loader?sdfFuryWebClient" },
     { test: /\.css$/,
       use: [ 'style-loader', 'css-loader']
    }
    ].concat(vtkRules),
  },
  resolve: {modules: [path.resolve(__dirname, 'node_modules'), sourcePath]},
  devServer: {
    contentBase: './dist/',
    port: 9999,
  },
};