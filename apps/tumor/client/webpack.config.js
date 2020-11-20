var path = require('path');
var vtkRules = require('vtk.js/Utilities/config/dependency.js').webpack.core.rules;

// Generate the html file
const HtmlWebpackPlugin = require('html-webpack-plugin');
const plugins = [new HtmlWebpackPlugin({inject: 'body'})];

var entry = path.join(__dirname, './src/index.js');
const sourcePath = path.join(__dirname, './src');
const outputPath = path.join(__dirname, '../www');

module.exports = {
    plugins,
    entry,
    output: {path: outputPath, filename: 'FuryWebClient.js'},
    module: {
        rules: [{test: /\.html$/, loader: 'html-loader'},
                {test: /\.css$/, use: [ 'style-loader', 'css-loader']}
               ].concat(vtkRules)
    },
    resolve: {modules: [path.resolve(__dirname, 'node_modules'), sourcePath]}
};