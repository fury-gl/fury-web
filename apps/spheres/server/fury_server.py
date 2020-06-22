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


class _WebSpheres(vtk_wslink.ServerProtocol):
    # Application configuration
    view = None
    authKey = "wslink-secret"

    def initialize(self):
        # Bring used components
        self.registerVtkWebProtocol(protocols.vtkWebMouseHandler())
        self.registerVtkWebProtocol(protocols.vtkWebViewPort())
        self.registerVtkWebProtocol(protocols.vtkWebViewPortImageDelivery())
        self.registerVtkWebProtocol(protocols.vtkWebViewPortGeometryDelivery())

        # Update authentication key to use
        self.updateSecret(_WebSpheres.authKey)

        # Create default pipeline (Only once for all the session)
        if not _WebSpheres.view:
            # FURY specific code
            scene = window.Scene()
            scene.background((1, 1, 1))
            centers = np.array([[2, 0, 0], [0, 2, 0], [0, 0, 0]])
            colors = np.array([[255, 0, 0], [0, 255, 0], [0, 0, 255]])
            scale = [1, 2, 1]

            n_sph = 10000
            fact = 16
            centers = fact * np.random.rand(n_sph, 3) - fact / 2
            colors = np.random.rand(n_sph, 3) * 255
            #scale = np.random.rand(n_sph)
            scale = 3

            fake_sphere = """
            float len = length(point);
            float radius = 1;
            if(len > radius)
                discard;
            
            vec3 normalizedPoint = normalize(vec3(point.xy, sqrt(1 - len)));
            vec3 direction = normalize(vec3(1, 1, 1));
            float df = max(0, dot(direction, normalizedPoint));
            float sf = pow(df, 24);
            fragOutput0 = vec4(max(df * color, sf * vec3(1)), 1);
            """

            billboard_actor = actor.billboard(centers,
                                              colors=colors.astype(np.uint8),
                                              scale=scale,
                                              fs_impl=fake_sphere)
            scene.add(billboard_actor)
            scene.add(actor.axes())
            scene.reset_camera()

            showm = window.ShowManager(scene)
            showm.render()

            renderWindow = showm.window

            # VTK Web application specific
            _WebSpheres.view = renderWindow
            self.getApplication().GetObjectIdMap().\
                SetActiveObject('VIEW', renderWindow)


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
