# -*- coding: utf-8 -*-
r"""
    This module is a VTK Web server application.
    The following command line illustrates how to use it::

        $ vtkpython .../vtk_server.py

    Any VTK Web executable script comes with a set of standard arguments that
    can be overriden if need be::
        --host localhost
             Interface on which the HTTP server will listen.

        --port 8080
             Port number on which the HTTP server will listen.

        --content /path-to-web-content/
             Directory that you want to serve as static web content.
             By default, this variable is empty which means that we rely on another server
             to deliver the static content and the current process only focuses on the
             WebSocket connectivity of clients.

        --authKey wslink-secret
             Secret key that should be provided by the client to allow it to make any
             WebSocket communication. The client will assume if none is given that the
             server expects "wslink-secret" as the secret key.
"""

# import to process args
import sys
import time
import os

# import vtk modules.
import numpy as np
import matplotlib
from fury import ui, window, actor, utils
from fury.io import load_polydata
import nibabel as nib
# from dipy.data import fetch_bundles_2_subjects, read_bundles_2_subjects
# from dipy.tracking.streamline import transform_streamlines, length
# from dipy.viz.app import horizon
import vtk
from vtk.web import protocols
from vtk.web import wslink as vtk_wslink
from wslink import server

import threading

try:
    import argparse
except ImportError:
    # since  Python 2.6 and earlier don't have argparse, we simply provide
    # the source for the same as _argparse and we use it instead.
    from vtk.util import _argparse as argparse

# =============================================================================
# Create custom ServerProtocol class to handle clients requests
# =============================================================================

global renderer, renderWindow, renderWindowInteractor

class _WebCone(vtk_wslink.ServerProtocol):

    # Application configuration
    view    = None
    authKey = "wslink-secret"

    def build_slider_demo(self):
        panel = ui.Panel2D(size=(500, 150), color=(1.0, 1.0, 1.0),
                           align="right", opacity=0.1)
        panel.center = (500, 400)

        ring_slider = ui.RingSlider2D(center=(740, 400), initial_value=0,
                                      text_template="{angle:5.1f}")
        ring_slider.default_color = (1, 0.5, 0)
        ring_slider.track.color = (0.8, 0.3, 0)
        ring_slider.active_color = (0.9, 0.4, 0)
        ring_slider.handle.color = (1, 0.5, 0)

        line_slider = ui.LineSlider2D(center=(500, 250), initial_value=0,
                                      min_value=-10, max_value=10)
        line_slider.default_color = (1, 0.5, 0)
        line_slider.track.color = (0.8, 0.3, 0)
        line_slider.active_color = (0.9, 0.4, 0)
        line_slider.handle.color = (1, 0.5, 0)

        def cube_maker(color=(1, 1, 1), size=(0.2, 0.2, 0.2), center=(0, 0, 0)):
            cube = vtk.vtkCubeSource()
            cube.SetXLength(size[0])
            cube.SetYLength(size[1])
            cube.SetZLength(size[2])
            if center is not None:
                cube.SetCenter(*center)
            cube_mapper = vtk.vtkPolyDataMapper()
            cube_mapper.SetInputConnection(cube.GetOutputPort())
            cube_actor = vtk.vtkActor()
            cube_actor.SetMapper(cube_mapper)
            if color is not None:
                cube_actor.GetProperty().SetColor(color)
            return cube_actor

        cube = cube_maker(color=(0, 0, 1), size=(20, 20, 20), center=(15, 0, 0))

        def rotate_cube(slider):
            angle = slider.value
            previous_angle = slider.previous_value
            rotation_angle = angle - previous_angle
            cube.RotateX(rotation_angle)

        ring_slider.on_change = rotate_cube

        def translate_cube(slider):
            value = slider.value
            cube.SetPosition(value, 0, 0)

        line_slider.on_change = translate_cube

        panel.add_element(ring_slider, (50, 20))
        panel.add_element(line_slider, (200, 70))

        return ('Slider Demo', [panel, cube])

    def build_brain_demo(self, showm):
        # path = "/Users/koudoro/Software/temp/"
        path = "/pvw/data/"
        # lh_path = os.path.join(path, "100307_white_lh.vtk")
        # rh_path = os.path.join(path, "100307_white_rh.vtk")
        # lh_pd = load_polydata(lh_path)
        # rh_pd = load_polydata(rh_path)
        left_fname = os.path.join(path, 'pial_left.gii')
        right_fname = os.path.join(path, 'pial_right.gii')

        left_gii = nib.load(left_fname)
        right_gii = nib.load(right_fname)

        left_pointset = left_gii.darrays[0].data  # NIFTI_INTENT_POINTSET   1008
        left_triangles = left_gii.darrays[1].data  # NIFTI_INTENT_TRIANGLE   1009
        right_pointset = right_gii.darrays[0].data
        right_triangles = right_gii.darrays[1].data

        left_poly = vtk.vtkPolyData()
        right_poly = vtk.vtkPolyData()

        utils.set_polydata_vertices(left_poly, left_pointset)
        utils.set_polydata_triangles(left_poly, left_triangles)
        utils.set_polydata_vertices(right_poly, right_pointset)
        utils.set_polydata_triangles(right_poly, right_triangles)

        lh_actor = utils.get_actor_from_polydata(left_poly)
        rh_actor = utils.get_actor_from_polydata(right_poly)

        text_block = ui.TextBlock2D(text='', font_size=15, bold=True,
                                    color=(1, 1, 1))

        panel = ui.Panel2D(size=(250, 30), position=(120, 30),
                           color=(.8, .8, .8), opacity=0.1)
        panel.add_element(text_block, (0.1, 0.1))

        picker = vtk.vtkCellPicker()
        # picker = window.vtk.vtkPointPicker()
        # print(picker.GetTolerance())
        picker.SetTolerance(0.01)

        dummy_sphere = actor.sphere(centers=np.array([[0, 0, 0]]),
                                    radii=1,
                                    colors=np.array([[1, 1, 0, 1.]]))

        prev_translation = (0, 0, 0)

        def highlight(obj, event):
            if not hasattr(obj, 'selected'):
                obj.selected = False

            selected = obj.selected
            color = obj.default_color if selected else (1.0, 1.0, 1.0)
            if event == "RightButtonPressEvent":
                obj.GetProperty().SetColor(color)
                obj.selected = not obj.selected

        def left_click_callback(obj, event):
            local_showm = left_click_callback.showm
            local_picker = left_click_callback.picker
            local_dummy_sphere = left_click_callback.dummy_sphere
            local_prev_translation = left_click_callback.prev_translation
            local_text_block = left_click_callback.text_block
            x, y, z = obj.GetCenter()
            event_pos = local_showm.iren.GetEventPosition()

            local_picker.Pick(event_pos[0], event_pos[1],
                              0, local_showm.scene)

            # cell_index = picker.GetCellId()
            point_index = local_picker.GetPointId()
            #text = 'Face ID ' + str(cell_index) + '\n' + 'Point ID ' + str(point_index)
            pos = np.round(local_picker.GetMapperPosition(), 3)
            text = str(point_index) + ' ' + str(pos)

            pi, pj, pk = local_prev_translation
            local_dummy_sphere.SetPosition(-pi, -pj, -pk)

            i, j, k = local_picker.GetMapperPosition()

            local_dummy_sphere.SetPosition(i, j, k)
            local_text_block.message = text
            # local_showm.render()
            local_showm.prev_translation = pos

        left_click_callback.showm = showm
        left_click_callback.picker = picker
        left_click_callback.prev_translation = prev_translation
        left_click_callback.text_block = text_block
        left_click_callback.dummy_sphere = dummy_sphere

        lh_actor.AddObserver('LeftButtonPressEvent', left_click_callback, 1)
        rh_actor.AddObserver('LeftButtonPressEvent', left_click_callback, 1)

        rh_actor.selected = False
        lh_actor.selected = False
        rh_actor.default_color = (1.0, 0.5, 0.0)
        lh_actor.default_color = (1.0, 0.0, 0.5)
        rh_actor.AddObserver('RightButtonPressEvent', highlight, 1)
        rh_actor.AddObserver('RightButtonReleaseEvent', highlight, 1)
        lh_actor.AddObserver('RightButtonPressEvent', highlight, 1)
        lh_actor.AddObserver('RightButtonReleaseEvent', highlight, 1)

        return ('Brain Demo', [panel, lh_actor, rh_actor, dummy_sphere])

    def build_bundle_demo(self):
        # fetch_bundles_2_subjects()
        # dix = read_bundles_2_subjects(subj_id='subj_1', metrics=['fa'],
        #                             bundles=['cg.left', 'cst.right'])
        # fa = dix['fa']
        # affine = dix['affine']
        # bundle = dix['cg.left']
        # bundle_native = transform_streamlines(bundle, np.linalg.inv(affine))

        # bundle_actor = actor.line(bundle_native)
        return ('Bundle Demo', [])  #[bundle_actor])

    def build_surface_demo(self, showm):
        xyzr = np.array([[0, 0, 0, 10], [100, 0, 0, 50], [200, 0, 0, 100]])

        colors = np.random.rand(*(xyzr.shape[0], 4))
        colors[:, 3] = 1

        # global text_block
        text_block = ui.TextBlock2D(text='', font_size=20, bold=True,
                                    color=(1, 1, 1))

        panel = ui.Panel2D(size=(350, 100), position=(150, 90),
                           color=(.6, .6, .6))
        panel.add_element(text_block, (0.2, 0.3))

        sphere_actor = actor.sphere(centers=0.5 * xyzr[:, :3],
                                    colors=colors[:],
                                    radii=xyzr[:, 3])

        # sphere_actor.GetProperty().SetRepresentationToWireframe()
        # sphere_actor.GetProperty().SetWireFrame(1)
        axes_actor = actor.axes(scale=(10, 10, 10))

        picker = vtk.vtkCellPicker()
        # picker = window.vtk.vtkPointPicker()
        # print(picker.GetTolerance())
        picker.SetTolerance(0.01)

        dummy_sphere = actor.sphere(centers=np.array([[0, 0, 0]]),
                                    radii=.1,
                                    colors=np.array([[1, 1, 0, 1.]]))

        prev_translation = (0, 0, 0)

        def left_click_callback(obj, event):
            local_showm = left_click_callback.showm
            local_picker = left_click_callback.picker
            local_dummy_sphere = left_click_callback.dummy_sphere
            local_text_block = left_click_callback.text_block
            x, y, z = obj.GetCenter()
            event_pos = local_showm.iren.GetEventPosition()

            local_picker.Pick(event_pos[0], event_pos[1],
                              0, local_showm.scene)

            # cell_index = picker.GetCellId()
            point_index = local_picker.GetPointId()
            #text = 'Face ID ' + str(cell_index) + '\n' + 'Point ID ' + str(point_index)
            pos = np.round(local_picker.GetMapperPosition(), 3)
            text = str(point_index) + ' ' + str(pos)

            pi, pj, pk = prev_translation
            local_dummy_sphere.SetPosition(-pi, -pj, -pk)

            i, j, k = local_picker.GetMapperPosition()

            local_dummy_sphere.SetPosition(i, j, k)
            local_text_block.message = text
            # local_showm.render()

            local_showm.prev_translation = pos

        left_click_callback.showm = showm
        left_click_callback.picker = picker
        left_click_callback.prev_translation = prev_translation
        left_click_callback.text_block = text_block
        left_click_callback.dummy_sphere = dummy_sphere
        sphere_actor.AddObserver('LeftButtonPressEvent', left_click_callback, 1)

        return ('Surface Demo', [panel, axes_actor, sphere_actor, dummy_sphere])

    def initialize(self):
        print(sys.version)
        global renderer, renderWindow, renderWindowInteractor  #, cone, mapper, actor

        # Bring used components
        self.registerVtkWebProtocol(protocols.vtkWebMouseHandler())
        self.registerVtkWebProtocol(protocols.vtkWebViewPort())
        self.registerVtkWebProtocol(protocols.vtkWebViewPortImageDelivery())
        # self.registerVtkWebProtocol(protocols.vtkWebPublishImageDelivery(decode=False))
        self.registerVtkWebProtocol(protocols.vtkWebViewPortGeometryDelivery())

        # Update authentication key to use
        self.updateSecret(_WebCone.authKey)

        # tell the C++ web app to use no encoding. vtkWebPublishImageDelivery must be set to decode=False to match.
        # self.getApplication().SetImageEncoding(0)

        # Create default pipeline (Only once for all the session)
        if not _WebCone.view:
            TEST_HORIZON = False

            if not TEST_HORIZON:
                showm = window.ShowManager()
                showm.initialize()

                slider_demo = self.build_slider_demo()
                brain_demo = self.build_brain_demo(showm)
                bundle_demo = self.build_bundle_demo()
                surface_demo = self.build_surface_demo(showm)

                examples = [slider_demo, brain_demo]
                examples_names = [name for name, act in examples]

                listbox = ui.ListBox2D(values=examples_names,
                                       position=(10, 300),
                                       size=(300, 80),
                                       multiselection=False)

                def hide_all_examples():
                    for _, l_act in examples:
                        for element in l_act:
                            if hasattr(element, 'add_to_scene'):
                                element.set_visibility(False)
                            else:
                                element.SetVisibility(False)

                def display_element():
                    hide_all_examples()
                    example = examples[examples_names.index(listbox.selected[0])]
                    for element in example[1]:
                        if hasattr(element, 'add_to_scene'):
                            element.set_visibility(True)
                        else:
                            element.SetVisibility(True)

                listbox.on_change = display_element
                listbox.panel.color = (1.0, 1.0, 1.0)
                listbox.panel.opacity = 0.3
                hide_all_examples()
                showm.scene.add(listbox)
                for _, l_act in examples:
                    for element in l_act:
                        showm.scene.add(element)

                # VTK specific code
                renderer = showm.scene
                renderWindow = showm.window
                renderWindowInteractor = showm.iren

            else:
                affine = np.diag([2., 1, 1, 1]).astype('f8')
                data = 255 * np.random.rand(150, 150, 150)
                images = [(data, affine)]
                from dipy.segment.tests.test_bundles import f1
                streamlines = f1.copy()
                tractograms = [streamlines]

                Horizon(tractograms, images=images, cluster=True, cluster_thr=5,
                        random_colors=False, length_lt=np.inf, length_gt=0,
                        clusters_lt=np.inf, clusters_gt=0,
                        world_coords=True)



            def calc_suare(numbers, showm):
                print("Calculate square numbers")
                for n in numbers:
                    time.sleep(1)
                    print("square:", n*n)
                    showm.scene.GetActiveCamera().Azimuth(10)
                    # showm.render()
                    # view = self.getApplication().GetObjectIdMap().GetActiveObject("VIEW")

            # arr = np.random.rand(100)
            # t1 = threading.Thread(target=calc_suare, args=(arr, showm))
            # t1.start()
            print("Auth-key {}".format(_WebCone.authKey))
            print('Initialization  --- OK')
            print('Starting FURY SERVER')
            # VTK Web application specific
            _WebCone.view = renderWindow
            self.getApplication().GetObjectIdMap().SetActiveObject("VIEW",
                                                                   renderWindow)

            # view = self.getApplication().GetObjectIdMap().GetActiveObject("VIEW")
            # import pdb; pdb.set_trace()

# =============================================================================
# Main: Parse args and start server
# =============================================================================


if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="VTK/Web Cone web-application")

    # Add default arguments
    server.add_arguments(parser)

    # Extract arguments
    args = parser.parse_args()

    # Configure our current application
    _WebCone.authKey = args.authKey

    # Start server
    server.start_webserver(options=args, protocol=_WebCone)
