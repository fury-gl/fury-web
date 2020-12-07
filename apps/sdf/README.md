### Web client

You will need to install [Node.js](http://nodejs.org/) to build and serve the web client.

Navigate to _/client/_. Install the project dependencies by typing:

```bash
npm install
```

## Run

### Render server

Navigate to _/server/_. Run _vtk_server.py_ using `pvpython` by typing (on Windows):

```bash
"C:\Program Files\ParaView 5.5.2-Qt5-MPI-Windows-64bit/bin/pvpython.exe" vtk_server.py --port 1234
```

### Web client

Navigate to _/client/_. To serve the web client in development mode, type:

```bash
npm start
```

and open _localhost:9999_ in your web browser.

To build a production version of the web client, type:

```bash
npm run build
```

### Known issue

How to solve npm error “npm ERR! code ELIFECYCLE”

```bash
Step 1: $ npm cache clean --force

Step 2: Delete node_modules by $ rm -rf node_modules package-lock.json folder or delete it manually by going into the directory and right-click > delete / move to trash. Also, delete package-lock.json file too.

Step 3: npm install

To start again, $ npm start or npm run build
```