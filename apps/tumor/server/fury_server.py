r"""
This module is a VTK/FURY Web server application. The following command line
illustrates how to use it:

$ vtkpython .../vtk_server.py

Any VTK Web executable script comes with a set of standard arguments that can
be overriden if need be:
    --host localhost
        Interface on which the HTTP server will listen.
    --port 8080
        Port number on which the HTTP server will listen.
    --content /path-to-web-content/
        Directory that you want to serve as static web content. By default,
        this variable is empty which means that we rely on another server to
        deliver the static content and the current process only focuses on the
        WebSocket connectivity of clients.
    --authKey wslink-secret
        Secret key that should be provided by the client to allow it to make
        any WebSocket communication. The client will assume if none is given
        that the server expects "wslink-secret" as the secret key.
"""


from fury import actor, ui, window
from fury_protocol import FuryProtocol, TumorProtocol
from vtk.web import protocols
from vtk.web import wslink as vtk_wslink
from wslink import server


import argparse


class _WebTumor(vtk_wslink.ServerProtocol):

    # Application configuration
    authKey = 'wslink-secret'
    view = None

    def initialize(self):
        # Bring used components
        self.registerVtkWebProtocol(protocols.vtkWebMouseHandler())
        self.registerVtkWebProtocol(protocols.vtkWebViewPort())
        # Image delivery
        # 1. Original method where the client ask for each image individually
        #self.registerVtkWebProtocol(protocols.vtkWebViewPortImageDelivery())
        # 2. Improvement on the initial protocol to allow images to be pushed
        # from the server without any client request (i.e.: animation, LOD, …)
        self.registerVtkWebProtocol(protocols.vtkWebPublishImageDelivery(
            decode=False))
        # Protocol for sending geometry for the vtk.js synchronized render
        # window
        # For local rendering using vtk.js
        #self.registerVtkWebProtocol(protocols.vtkWebViewPortGeometryDelivery())
        #self.registerVtkWebProtocol(protocols.vtkWebLocalRendering())

        # Custom API
        self.registerVtkWebProtocol(FuryProtocol())
        self.registerVtkWebProtocol(TumorProtocol())

        # Tell the C++ web app to use no encoding.
        # ParaViewWebPublishImageDelivery must be set to decode=False to match.
        # RAW instead of base64
        self.getApplication().SetImageEncoding(0)

        # Update authentication key to use
        self.updateSecret(_WebTumor.authKey)

        # Create default pipeline (Only once for all the session)
        if not _WebTumor.view:

            # FURY specific code
            scene = window.Scene()
            show_m = window.ShowManager(scene, reset_camera=False,
                                        order_transparent=True)
            show_m.initialize()

            # For debugging purposes
            # show_m.render()

            ren_win = show_m.window

            # VTK Web application specific
            _WebTumor.view = ren_win
            self.getApplication().GetObjectIdMap().SetActiveObject(
                'VIEW', ren_win)
            self.setSharedObject("SHOWM", show_m)
            # self.getApplication().GetObjectIdMap().SetActiveObject(
            #     'SHOWM', show_m)


# =============================================================================
# Main: Parse args and start server
# =============================================================================
if __name__ == "__main__":
    description = 'FURY/Web High Performance Spheres web-application'

    # Create argument parser
    parser = argparse.ArgumentParser(description=description)

    # Add default arguments
    server.add_arguments(parser)

    # Extract arguments
    args = parser.parse_args()

    # Configure our current application
    _WebTumor.authKey = args.authKey

    # Start server
    server.start_webserver(options=args, protocol=_WebTumor)
