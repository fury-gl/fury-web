import "./styles.css";

import vtkWSLinkClient from 'vtk.js/Sources/IO/Core/WSLinkClient';
import vtkRemoteView from 'vtk.js/Sources/Rendering/Misc/RemoteView';
import { connectImageStream } from 'vtk.js/Sources/Rendering/Misc/RemoteView';
import vtkURLExtract from 'vtk.js/Sources/Common/Core/URLExtract';

import SmartConnect from 'wslink/src/SmartConnect';

vtkWSLinkClient.setSmartConnectClass(SmartConnect);

document.body.style.padding = '0';
document.body.style.margin = '0';

const divRenderer = document.createElement('div');
document.body.appendChild(divRenderer);

divRenderer.style.position = 'relative';
divRenderer.style.width = '100vw';
divRenderer.style.height = '100vh';
divRenderer.style.overflow = 'hidden';

// loading
const divLoading = document.createElement('div');
const txtLoading = document.createElement('h2');
txtLoading.innerHTML = "Loading...";
divLoading.classList.add("loader");
txtLoading.classList.add("loadertxt");
divRenderer.appendChild(divLoading);
divRenderer.appendChild(txtLoading);
divRenderer.classList.add("parent");


const view = vtkRemoteView.newInstance({
  rpcWheelEvent: 'viewport.mouse.zoom.wheel',
});
view.setContainer(divRenderer);
// Default of .5 causes 2x size labels on high-DPI screens.
// 1 good for demo, not for production.
if (location.hostname.split('.')[0] === 'localhost') {
    view.setInteractiveRatio(1);
} else {
    // Scaled image compared to the clients view resolution
    view.setInteractiveRatio(1);
}
view.setInteractiveQuality(100); // jpeg quality

window.addEventListener('resize', view.resize);

const clientToConnect = vtkWSLinkClient.newInstance();

// Error
clientToConnect.onConnectionError((httpReq) => {
  const message =
    (httpReq && httpReq.response && httpReq.response.error) ||
    `Connection error`;
  console.error(message);
  console.log(httpReq);
  txtLoading.innerHTML = message;
});

// Close
clientToConnect.onConnectionClose((httpReq) => {
  const message =
    (httpReq && httpReq.response && httpReq.response.error) ||
    `Connection close`;
  console.error(message);
  console.log(httpReq);
  txtLoading.innerHTML = message;
});

// hint: if you use the launcher.py and ws-proxy just leave out sessionURL
// (it will be provided by the launcher)
const baseConfig = { application: 'sdf', };
const userParams = vtkURLExtract.extractURLParameters();
const config = Object.assign({}, baseConfig, userParams);


// Connect
clientToConnect
  .connect(config)
  .then((validClient) => {
    connectImageStream(validClient.getConnection().getSession());
    const session = validClient.getConnection().getSession();
    view.setSession(session);
    view.setViewId(-1);
    view.render();

    divRenderer.removeChild(divLoading);
    divRenderer.removeChild(txtLoading);
    divRenderer.classList.remove("parent");
  })
  .catch((error) => {
    console.error(error);
    txtLoading.innerHTML = message;
    divRenderer.appendChild(divLoading);
    divRenderer.appendChild(txtLoading);
    divRenderer.classList.add("parent");
  });