import vtkWSLinkClient from 'vtk.js/Sources/IO/Core/WSLinkClient';
import vtkRemoteView from 'vtk.js/Sources/Rendering/Misc/RemoteView';
import { connectImageStream } from 'vtk.js/Sources/Rendering/Misc/RemoteView';

import SmartConnect from 'wslink/src/SmartConnect';

vtkWSLinkClient.setSmartConnectClass(SmartConnect);

$( 'document.body' ).css({backgroundColor: "gray", margin: '0px', padding: '0px',
    height: '100%', width: '100%'});

const $divRenderer = $( '<div id="fury"></div>' );
//$( 'document.body' ).append( $divRenderer );

//$divRenderer.height(100);
//$divRenderer.width(100);

//divRenderer.style.position = 'relative';
//divRenderer.style.overflow = 'hidden';