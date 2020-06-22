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

from fury.utils import get_actor_from_polydata, set_polydata_triangles, \
        set_polydata_vertices, set_polydata_colors
from vtk.util.numpy_support import numpy_to_vtk
import vtk


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

            n_points = 1000000
            translate = 100
            colors = 255 * np.random.rand(n_points, 3)
            centers = translate * np.random.rand(n_points, 3) - translate / 2
            radius = np.random.rand(n_points) / 10

            polydata = vtk.vtkPolyData()

            verts = np.array([[0.0, 0.0, 0.0],
                              [0.0, 1.0, 0.0],
                              [1.0, 1.0, 0.0],
                              [1.0, 0.0, 0.0]])
            verts -= np.array([0.5, 0.5, 0])

            big_verts = np.tile(verts, (centers.shape[0], 1))
            big_cents = np.repeat(centers, verts.shape[0], axis=0)

            big_verts += big_cents

            # print(big_verts)

            big_scales = np.repeat(radius, verts.shape[0], axis=0)

            # print(big_scales)

            big_verts *= big_scales[:, np.newaxis]

            # print(big_verts)

            tris = np.array([[0, 1, 2], [2, 3, 0]], dtype='i8')

            big_tris = np.tile(tris, (centers.shape[0], 1))
            shifts = np.repeat(np.arange(0, centers.shape[0] * verts.shape[0],
                                         verts.shape[0]), tris.shape[0])

            big_tris += shifts[:, np.newaxis]

            # print(big_tris)

            big_cols = np.repeat(colors, verts.shape[0], axis=0)

            # print(big_cols)

            big_centers = np.repeat(centers, verts.shape[0], axis=0)

            # print(big_centers)

            big_centers *= big_scales[:, np.newaxis]

            # print(big_centers)

            set_polydata_vertices(polydata, big_verts)
            set_polydata_triangles(polydata, big_tris)
            set_polydata_colors(polydata, big_cols)

            vtk_centers = numpy_to_vtk(big_centers, deep=True)
            vtk_centers.SetNumberOfComponents(3)
            vtk_centers.SetName("center")
            polydata.GetPointData().AddArray(vtk_centers)

            canvas_actor = get_actor_from_polydata(polydata)
            canvas_actor.GetProperty().BackfaceCullingOff()

            mapper = canvas_actor.GetMapper()

            mapper.MapDataArrayToVertexAttribute(
                "center", "center", vtk.vtkDataObject.FIELD_ASSOCIATION_POINTS,
                -1)

            mapper.AddShaderReplacement(
                vtk.vtkShader.Vertex,
                "//VTK::ValuePass::Dec",
                True,
                """
                //VTK::ValuePass::Dec
                in vec3 center;

                out vec3 centeredVertexMC;
                """,
                False
            )

            mapper.AddShaderReplacement(
                vtk.vtkShader.Vertex,
                "//VTK::ValuePass::Impl",
                True,
                """
                //VTK::ValuePass::Impl
                centeredVertexMC = vertexMC.xyz - center;
                float scalingFactor = 1. / abs(centeredVertexMC.x);
                centeredVertexMC *= scalingFactor;

                vec3 cameraRight = vec3(MCVCMatrix[0][0], MCVCMatrix[1][0], 
                                        MCVCMatrix[2][0]);
                vec3 cameraUp = vec3(MCVCMatrix[0][1], MCVCMatrix[1][1], 
                                     MCVCMatrix[2][1]);
                vec2 squareVertices = vec2(.5, -.5);
                vec3 vertexPosition = center + cameraRight * squareVertices.x * 
                                      vertexMC.x + cameraUp * squareVertices.y * 
                                      vertexMC.y;
                gl_Position = MCDCMatrix * vec4(vertexPosition, 1.);
                gl_Position /= gl_Position.w;
                """,
                False
            )

            mapper.AddShaderReplacement(
                vtk.vtkShader.Fragment,
                "//VTK::ValuePass::Dec",
                True,
                """
                //VTK::ValuePass::Dec
                in vec3 centeredVertexMC;
                """,
                False
            )

            mapper.AddShaderReplacement(
                vtk.vtkShader.Fragment,
                "//VTK::Light::Impl",
                True,
                """
                // Renaming variables passed from the Vertex Shader
                vec3 color = vertexColorVSOutput.rgb;
                vec3 point = centeredVertexMC;
                float len = length(point);
                // VTK Fake Spheres
                float radius = 1.;
                if(len > radius)
                  discard;
                vec3 normalizedPoint = normalize(vec3(point.xy, sqrt(1. - len)));
                vec3 direction = normalize(vec3(1., -1., 1.));
                float df = max(0, dot(direction, normalizedPoint));
                float sf = pow(df, 24);
                fragOutput0 = vec4(max(df * color, sf * vec3(1)), 1);
                """,
                False
            )

            scene.add(canvas_actor)
            #scene.add(actor.axes())

            showm = window.ShowManager(scene)

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
