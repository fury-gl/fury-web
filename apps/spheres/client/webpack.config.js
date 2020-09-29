var path = require('path');
var vtkRules = require('vtk.js/Utilities/config/dependency.js').webpack.core.rules;

var entry = path.join(__dirname, './src/index.js');
const sourcePath = path.join(__dirname, './src');
const outputPath = path.join(__dirname, './../www');

module.exports = {
    entry,
    output: {path: outputPath, filename: 'FuryWebClient.js'},
    module: {
        rules: [{test: /\.html$/, loader: 'html-loader'}].concat(vtkRules)
    },
    resolve: {modules: [path.resolve(__dirname, 'node_modules'), sourcePath]}
};