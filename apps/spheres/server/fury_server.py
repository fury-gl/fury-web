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


from fury import actor, window
from vtk.web import protocols
from vtk.web import wslink as vtk_wslink
from wslink import server


import argparse
import numpy as np
import vtk


class _WebSpheres(vtk_wslink.ServerProtocol):

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

        # Tell the C++ web app to use no encoding.
        # ParaViewWebPublishImageDelivery must be set to decode=False to match.
        # RAW instead of base64
        self.getApplication().SetImageEncoding(0)

        # Update authentication key to use
        self.updateSecret(_WebSpheres.authKey)

        # Create default pipeline (Only once for all the session)
        if not _WebSpheres.view:
            # FURY specific code
            scene = window.Scene()
            scene.background((1, 1, 1))

            n_points = 10000
            translate = 100
            centers = translate * np.random.rand(n_points, 3) - translate / 2
            colors = 255 * np.random.rand(n_points, 3)
            radius = np.random.rand(n_points)
            fake_sphere = \
                """
                float len = length(point);
                float radius = 1.;
                if(len > radius)
                    {discard;}

                vec3 normalizedPoint = normalize(vec3(point.xy, sqrt(1. - len)));
                vec3 direction = normalize(vec3(1., 1., 1.));
                float df_1 = max(0, dot(direction, normalizedPoint));
                float sf_1 = pow(df_1, 24);
                fragOutput0 = vec4(max(df_1 * color, sf_1 * vec3(1)), 1);
                """
            spheres_actor = actor.billboard(centers, colors=colors,
                                            scales=radius, fs_impl=fake_sphere)

            scene.add(spheres_actor)
            scene.add(actor.axes())

            showm = window.ShowManager(scene)
            # For debugging purposes
            #showm.render()

            ren_win = showm.window

            ren_win_interactor = vtk.vtkRenderWindowInteractor()
            ren_win_interactor.SetRenderWindow(ren_win)
            ren_win_interactor.GetInteractorStyle().\
                SetCurrentStyleToTrackballCamera()
            ren_win_interactor.EnableRenderOff()

            # VTK Web application specific
            _WebSpheres.view = ren_win
            self.getApplication().GetObjectIdMap().SetActiveObject(
                'VIEW', ren_win)


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
    _WebSpheres.authKey = args.authKey

    # Start server
    server.start_webserver(options=args, protocol=_WebSpheres)
