from vtk.web import protocols
from wslink import register


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
