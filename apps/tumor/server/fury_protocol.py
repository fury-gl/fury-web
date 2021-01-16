import os
import json

import numpy as np
from fury import ui, actor
import vtk

from pyMCDS_cells import pyMCDS_cells
from vtk.web import protocols
from wslink import register


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


def read_xml_data(folder=None, filename='output00000246.xml'):
    output_path = folder or os.path.abspath(os.path.dirname(__file__))

    xml_file = os.path.join(output_path, filename)

    mcds = pyMCDS_cells(xml_file, output_path=output_path)

    ncells = len(mcds.data['discrete_cells']['ID'])

    centers = np.zeros((ncells, 3))
    centers[:, 0] = mcds.data['discrete_cells']['position_x']
    centers[:, 1] = mcds.data['discrete_cells']['position_y']
    centers[:, 2] = mcds.data['discrete_cells']['position_z']

    colors = np.zeros((ncells, 3))
    colors[:, 0] = 1
    colors[:, 1] = 1
    colors[:, 2] = 0

    cycle_model = mcds.data['discrete_cells']['cycle_model']

    cell_type = mcds.data['discrete_cells']['cell_type']

    onco = mcds.data['discrete_cells']['oncoprotein']
    onco_min = onco.min()
    onco_range = onco.max() - onco.min()

    # This coloring is only approximately correct, but at least it shows
    # variation in cell colors
    for idx in range(ncells):
        if cell_type[idx] == 1:
            colors[idx, 0] = 1
            colors[idx, 1] = 1
            colors[idx, 2] = 0
        if cycle_model[idx] < 100:
            colors[idx, 0] = 1.0 - (onco[idx] - onco_min) / onco_range
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

    return centers, colors, radius


_RANGE_CENTERS = \
    """
    uniform vec3 lowRanges;
    uniform vec3 highRanges;

    bool isVisible(vec3 center)
    {
        bool xValidation = lowRanges.x <= center.x && center.x <= highRanges.x;
        bool yValidation = lowRanges.y <= center.y && center.y <= highRanges.y;
        bool zValidation = lowRanges.z <= center.z && center.z <= highRanges.z;
        return xValidation || yValidation || zValidation;
    }
    """
_FAKE_SPHERE = \
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


class TumorProtocol(protocols.vtkWebProtocol):

    def __init__(self):
        super().__init__()

        self.xml_files = []
        self.bounds = None
        self.min_centers, self.max_centers = [0, 0, 0], [100, 100, 100]
        self.low_ranges, self.high_ranges = [25, 25, 25], [75, 75, 75]
        self.low_perc, self.high_perc = np.array([50, 50, 50]), \
            np.array([100, 100, 100])
        self.panel = None
        self.slider_clipping_plane_thrs_x = None
        self.slider_clipping_plane_thrs_y = None
        self.slider_clipping_plane_thrs_z = None
        self.slider_frame_thr = None
        self.spheres_actor = None
        self.size = None

    @register("tumor.reset")
    def reset(self):
        scene = self.getView('-1')
        scene.rm_all()
        self.xml_files = []
        self.create_visualization()

    @register("tumor.initialize")
    def create_visualization(self):
        ren_win = self.getView('-1')
        scene = ren_win.GetRenderers().GetFirstRenderer()
        showm = self.getSharedObject('SHOWM')

        self.panel = ui.Panel2D((480, 270), position=(-185, 5), color=(1, 1, 1),
                                opacity=.1, align='right')

        self.slider_frame_label = build_label('Frame')
        self.slider_frame_label.set_visibility(False)
        self.slider_frame_thr = ui.LineSlider2D(
            initial_value=0, min_value=0, max_value=1,
            length=260, line_width=3, outer_radius=8, font_size=16,
            text_template="{value:.0f}")
        self.slider_frame_thr.set_visibility(False)
        self.slider_frame_thr.on_change = self.change_frame
        self.slider_clipping_plane_label_x = build_label('X Clipping Plane')
        self.slider_clipping_plane_thrs_x = ui.LineDoubleSlider2D(
            line_width=3, outer_radius=5, length=115,
            initial_values=(self.low_ranges[0], self.high_ranges[0]),
            min_value=self.min_centers[0], max_value=self.max_centers[0],
            font_size=12, text_template="{value:.0f}")

        self.slider_clipping_plane_label_y = build_label('Y Clipping Plane')
        self.slider_clipping_plane_thrs_y = ui.LineDoubleSlider2D(
            line_width=3, outer_radius=5, length=115,
            initial_values=(self.low_ranges[1], self.high_ranges[1]),
            min_value=self.min_centers[1], max_value=self.max_centers[1],
            font_size=12, text_template="{value:.0f}")

        self.slider_clipping_plane_label_z = build_label('Z Clipping Plane')
        self.slider_clipping_plane_thrs_z = ui.LineDoubleSlider2D(
            line_width=3, outer_radius=5, length=115,
            initial_values=(self.low_ranges[2], self.high_ranges[2]),
            min_value=self.min_centers[2], max_value=self.max_centers[2],
            font_size=12, text_template="{value:.0f}")

        self.panel.add_element(self.slider_frame_label, (.04, .85))
        self.panel.add_element(self.slider_frame_thr, (.38, .85))
        self.panel.add_element(self.slider_clipping_plane_label_x, (.04, .55))
        self.panel.add_element(self.slider_clipping_plane_thrs_x, (.38, .55))
        self.panel.add_element(self.slider_clipping_plane_label_y, (.04, .35))
        self.panel.add_element(self.slider_clipping_plane_thrs_y, (.38, .35))
        self.panel.add_element(self.slider_clipping_plane_label_z, (.04, .15))
        self.panel.add_element(self.slider_clipping_plane_thrs_z, (.38, .15))

        scene.add(self.panel)
        self.size = scene.GetSize()
        showm.add_window_callback(self.win_callback)

    @register("tumor.update_view")
    def update_frame(self, data):
        print(data)
        data = json.loads(data)
        print(data)
        centers, colors, radius = read_xml_data()  # folder=folder,
                                                # filename=fname)
        print(len(centers))
        ren_win = self.getView('-1')
        scene = ren_win.GetRenderers().GetFirstRenderer()
        self.disconnect_sliders()
        if self.spheres_actor is not None:
            scene.rm(self.spheres_actor)

        self.spheres_actor = actor.billboard(centers, colors, scales=radius,
                                             fs_dec=_RANGE_CENTERS,
                                             fs_impl=_FAKE_SPHERE)

        spheres_mapper = self.spheres_actor.GetMapper()
        spheres_mapper.AddObserver(vtk.vtkCommand.UpdateShaderEvent,
                                   self.vtk_shader_callback)

        scene.add(self.spheres_actor)

        self.min_centers = np.min(centers, axis=0)
        self.max_centers = np.max(centers, axis=0)

        self.low_ranges = np.array([np.percentile(centers[:, i], v)
                                    for i, v in enumerate(self.low_perc)])
        self.high_ranges = np.array([np.percentile(centers[:, i], v)
                                     for i, v in enumerate(self.high_perc)])
        scene.ResetCamera()
        self.connect_sliders()

    def disconnect_sliders(self):
        self.slider_clipping_plane_thrs_x.on_change = lambda slider: None
        self.slider_clipping_plane_thrs_y.on_change = lambda slider: None
        self.slider_clipping_plane_thrs_z.on_change = lambda slider: None

    def connect_sliders(self):
        self.slider_clipping_plane_thrs_x.left_disk_value = self.low_ranges[0]
        self.slider_clipping_plane_thrs_x.right_disk_value = self.high_ranges[0]
        self.slider_clipping_plane_thrs_x.min_value = self.min_centers[0]
        self.slider_clipping_plane_thrs_x.max_value = self.max_centers[0]
        self.slider_clipping_plane_thrs_x.on_change = self.change_clipping_plane_x

        self.slider_clipping_plane_thrs_y.left_disk_value = self.low_ranges[1]
        self.slider_clipping_plane_thrs_y.right_disk_value = self.high_ranges[1]
        self.slider_clipping_plane_thrs_y.min_value = self.min_centers[1]
        self.slider_clipping_plane_thrs_y.max_value = self.max_centers[1]
        self.slider_clipping_plane_thrs_y.on_change = self.change_clipping_plane_y

        self.slider_clipping_plane_thrs_z.left_disk_value = self.low_ranges[2]
        self.slider_clipping_plane_thrs_z.right_disk_value = self.high_ranges[2]
        self.slider_clipping_plane_thrs_z.min_value = self.min_centers[2]
        self.slider_clipping_plane_thrs_z.max_value = self.max_centers[2]
        self.slider_clipping_plane_thrs_z.on_change = self.change_clipping_plane_z

        if len(self.xml_files) > 1:
            self.slider_frame_thr.set_visibility(True)
            self.slider_frame_label.set_visibility(True)

    def change_clipping_plane_x(self, slider):
        values = slider._values
        r1, r2 = values
        self.low_ranges[0] = r1
        self.high_ranges[0] = r2
        range_centers = self.max_centers[0] - self.min_centers[0]
        self.low_perc[0] = (r1 - self.min_centers[0]) / range_centers * 100
        self.high_perc[0] = (r2 - self.min_centers[0]) / range_centers * 100

    def change_clipping_plane_y(self, slider):
        values = slider._values
        r1, r2 = values
        self.low_ranges[1] = r1
        self.high_ranges[1] = r2
        range_centers = self.max_centers[1] - self.min_centers[1]
        self.low_perc[1] = (r1 - self.min_centers[1]) / range_centers * 100
        self.high_perc[1] = (r2 - self.min_centers[1]) / range_centers * 100

    def change_clipping_plane_z(self, slider):
        values = slider._values
        r1, r2 = values
        self.low_ranges[2] = r1
        self.high_ranges[2] = r2
        range_centers = self.max_centers[2] - self.min_centers[2]
        self.low_perc[2] = (r1 - self.min_centers[2]) / range_centers * 100
        self.high_perc[2] = (r2 - self.min_centers[2]) / range_centers * 100

    def change_frame(self, slider):
        idx_xml = int(slider.value)

        data = {}

        self.update_frame(idx_xml)

    @vtk.calldata_type(vtk.VTK_OBJECT)
    def vtk_shader_callback(self, caller, event, calldata=None):
        if calldata is not None:
            calldata.SetUniform3f('lowRanges', self.low_ranges)
            calldata.SetUniform3f('highRanges', self.high_ranges)

    def win_callback(self, obj, event):
        if self.size != obj.GetSize():
            size_old = self.size
            size = obj.GetSize()
            size_change = [size[0] - size_old[0], 0]
            self.panel.re_align(size_change)


class FuryProtocol(protocols.vtkWebProtocol):

    @register("viewport.mouse.zoom.wheel")
    def update_zoom_from_wheel(self, event):
        if 'Start' in event['type']:
            self.getApplication().InvokeEvent('StartInteractionEvent')

        ren_win = self.getView(event['view'])
        if ren_win and 'spinY' in event:
            zoom_factor = 1 - event['spinY'] / 10

            camera = ren_win.GetRenderers().GetFirstRenderer().\
                GetActiveCamera()
            fp = camera.GetFocalPoint()
            pos = camera.GetPosition()
            delta = [fp[i] - pos[i] for i in range(3)]
            camera.Zoom(zoom_factor)

            pos2 = camera.GetPosition()
            camera.SetFocalPoint([pos2[i] + delta[i] for i in range(3)])
            ren_win.Modified()

        if 'End' in event['type']:
            self.getApplication().InvokeEvent('EndInteractionEvent')

    @register("test_fury.update_views")
    def update_views(self, url):
        """Get folder via url and update rendering"""
        print(url)

    @register("test_fury.add_frame")
    def add_frames(self, centers):
        """Get folder via url and update rendering"""
        print(centers)
