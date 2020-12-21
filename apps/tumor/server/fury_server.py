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
from fury_protocol import FuryProtocol
from pyMCDS_cells import pyMCDS_cells
from vtk.util import numpy_support
from vtk.web import protocols
from vtk.web import wslink as vtk_wslink
from wslink import server


import argparse
import numpy as np
import os
import vtk


def change_clipping_plane_x(slider):
    global low_ranges, high_ranges
    values = slider._values
    r1, r2 = values
    low_ranges[0] = r1
    high_ranges[0] = r2


def change_clipping_plane_y(slider):
    global low_ranges, high_ranges
    values = slider._values
    r1, r2 = values
    low_ranges[1] = r1
    high_ranges[1] = r2


def change_clipping_plane_z(slider):
    global low_ranges, high_ranges
    values = slider._values
    r1, r2 = values
    low_ranges[2] = r1
    high_ranges[2] = r2


@vtk.calldata_type(vtk.VTK_OBJECT)
def vtk_shader_callback(caller, event, calldata=None):
    global low_ranges, high_ranges
    if calldata is not None:
        calldata.SetUniform3f('lowRanges', low_ranges)
        calldata.SetUniform3f('highRanges', high_ranges)


def win_callback(obj, event):
    global size
    global panel
    if size != obj.GetSize():
        size_old = size
        size = obj.GetSize()
        size_change = [size[0] - size_old[0], 0]
        panel.re_align(size_change)


class _WebTumor(vtk_wslink.ServerProtocol):

    # Application configuration
    authKey = 'wslink-secret'
    view = None

    @staticmethod
    def build_label(text, font_size=14, bold=False):
        label = ui.TextBlock2D()
        label.message = text
        label.font_size = font_size
        label.font_family = 'Arial'
        label.justification = 'left'
        label.bold = bold
        label.italic = False
        label.shadow = False
        label.actor.GetTextProperty().SetBackgroundColor(0, 0, 0)
        label.actor.GetTextProperty().SetBackgroundOpacity(0.0)
        label.color = (1, 1, 1)
        return label

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

        # Tell the C++ web app to use no encoding.
        # ParaViewWebPublishImageDelivery must be set to decode=False to match.
        # RAW instead of base64
        self.getApplication().SetImageEncoding(0)

        # Update authentication key to use
        self.updateSecret(_WebTumor.authKey)

        # Create default pipeline (Only once for all the session)
        if not _WebTumor.view:
            output_path = os.path.abspath(os.path.dirname(__file__))
            print(output_path)
            xml_file = os.path.join(output_path, 'output00000246.xml')
            mcds = pyMCDS_cells(xml_file, output_path=output_path)  # 23123 cells
            ncells = len(mcds.data['discrete_cells']['ID'])

            centers = np.zeros((ncells, 3))
            centers[:, 0] = mcds.data['discrete_cells']['position_x']
            centers[:, 1] = mcds.data['discrete_cells']['position_y']
            centers[:, 2] = mcds.data['discrete_cells']['position_z']

            colors = np.zeros((ncells, 3))
            # default color: yellow
            colors[:, 0] = 1
            colors[:, 1] = 1
            colors[:, 2] = 0
            cell_phase = mcds.data['discrete_cells']['current_phase']
            # cell_phase = cell_phase[idx_keep]

            cycle_model = mcds.data['discrete_cells']['cycle_model']
            # cycle_model = cycle_model[idx_keep]

            cell_type = mcds.data['discrete_cells']['cell_type']
            # cell_type = cell_type[idx_keep]

            onco = mcds.data['discrete_cells']['oncoprotein']
            # onco = onco[idx_keep]
            onco_min = onco.min()
            print('onco min, max= ', onco.min(), onco.max())
            onco_range = onco.max() - onco.min()

            # e.g., 14.0 100.0
            print('cell_phase min, max= ', cell_phase.min(), cell_phase.max())

            # This coloring is only approximately correct, but at least it shows
            # variation in cell colors
            for idx in range(ncells):
                if cell_type[idx] == 1:
                    colors[idx, 0] = 1
                    colors[idx, 1] = 1
                    colors[idx, 2] = 0
                    # self.yval1 = np.array([(np.count_nonzero((mcds[idx].data['discrete_cells']['cell_type'] == 1) & (mcds[idx].data['discrete_cells']['cycle_model'] < 100) == True)) for idx in range(ds_count)] )
                if cycle_model[idx] < 100:
                    # rgb[idx, 0] = 0.5
                    # rgb[idx, 1] = 0.5
                    colors[idx, 0] = 1.0 - (onco[idx] - onco_min)/onco_range
                    # rgb[idx,1] = (onco[idx] - onco_min)/onco_range
                    colors[idx, 1] = colors[idx, 0]
                    colors[idx, 2] = 0
                elif cycle_model[idx] == 100:
                    colors[idx, 0] = 1
                    colors[idx, 1] = 0
                    colors[idx, 2] = 0
                elif cycle_model[idx] > 100:
                    colors[idx, 0] = 0.54  # 139./255
                    colors[idx, 1] = 0.27  # 69./255
                    colors[idx, 2] = 0.075  # 19./255

            radius = mcds.data['discrete_cells']['total_volume'] * .75 / np.pi
            radius = np.cbrt(radius)

            # FURY specific code
            scene = window.Scene()

            range_centers = \
                """        
                uniform vec3 lowRanges;
                uniform vec3 highRanges;

                bool isVisible(vec3 center)
                {
                    bool xValidation = lowRanges.x <= center.x && 
                                       center.x <= highRanges.x;
                    bool yValidation = lowRanges.y <= center.y && 
                                       center.y <= highRanges.y;
                    bool zValidation = lowRanges.z <= center.z && 
                                       center.z <= highRanges.z;
                    return xValidation || yValidation || zValidation;
                }
                """

            fake_sphere = \
                """
                if(!isVisible(centerVertexMCVSOutput))
                    discard;
                float len = length(point);
                float radius = 1.;
                if(len > radius)
                    discard;
                vec3 normalizedPoint = normalize(vec3(point.xy, sqrt(1. - len)));
                vec3 direction = normalize(vec3(1., 1., 1.));
                float df_1 = max(0, dot(direction, normalizedPoint));
                float sf_1 = pow(df_1, 24);
                fragOutput0 = vec4(max(df_1 * color, sf_1 * vec3(1)), 1);
                """

            spheres_actor = actor.billboard(
                centers, colors, scales=radius, fs_dec=range_centers,
                fs_impl=fake_sphere)

            scene.add(spheres_actor)

            min_centers = np.min(centers, axis=0)
            max_centers = np.max(centers, axis=0)

            global low_ranges, high_ranges
            low_ranges = np.percentile(centers, 50, axis=0)
            high_ranges = max_centers

            spheres_mapper = spheres_actor.GetMapper()
            spheres_mapper.AddObserver(vtk.vtkCommand.UpdateShaderEvent,
                                       vtk_shader_callback)

            show_m = window.ShowManager(scene, reset_camera=False,
                                        order_transparent=True)
            show_m.initialize()

            global panel
            panel = ui.Panel2D((256, 144), position=(40, 5), color=(1, 1, 1),
                               opacity=.1, align='right')

            slider_clipping_plane_label_x = _WebTumor.build_label(
                'X Clipping Plane')
            slider_clipping_plane_thrs_x = ui.LineDoubleSlider2D(
                line_width=3, outer_radius=5, length=115,
                initial_values=(low_ranges[0], high_ranges[0]),
                min_value=min_centers[0], max_value=max_centers[0],
                font_size=12, text_template="{value:.0f}")

            slider_clipping_plane_label_y = _WebTumor.build_label(
                'Y Clipping Plane')
            slider_clipping_plane_thrs_y = ui.LineDoubleSlider2D(
                line_width=3, outer_radius=5, length=115,
                initial_values=(low_ranges[1], high_ranges[1]),
                min_value=min_centers[1], max_value=max_centers[1],
                font_size=12, text_template="{value:.0f}")

            slider_clipping_plane_label_z = _WebTumor.build_label(
                'Z Clipping Plane')
            slider_clipping_plane_thrs_z = ui.LineDoubleSlider2D(
                line_width=3, outer_radius=5, length=115,
                initial_values=(low_ranges[2], high_ranges[2]),
                min_value=min_centers[2], max_value=max_centers[2],
                font_size=12, text_template="{value:.0f}")

            slider_clipping_plane_thrs_x.on_change = change_clipping_plane_x
            slider_clipping_plane_thrs_y.on_change = change_clipping_plane_y
            slider_clipping_plane_thrs_z.on_change = change_clipping_plane_z

            panel.add_element(slider_clipping_plane_label_x, (.01, .85))
            panel.add_element(slider_clipping_plane_thrs_x, (.48, .85))
            panel.add_element(slider_clipping_plane_label_y, (.01, .55))
            panel.add_element(slider_clipping_plane_thrs_y, (.48, .55))
            panel.add_element(slider_clipping_plane_label_z, (.01, .25))
            panel.add_element(slider_clipping_plane_thrs_z, (.48, .25))

            scene.add(panel)

            global size
            size = scene.GetSize()

            show_m.add_window_callback(win_callback)

            # For debugging purposes
            #show_m.render()

            ren_win = show_m.window

            # VTK Web application specific
            _WebTumor.view = ren_win
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
    _WebTumor.authKey = args.authKey

    # Start server
    server.start_webserver(options=args, protocol=_WebTumor)
