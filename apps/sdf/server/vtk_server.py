r"""
    This module is a ParaViewWeb server application.
    The following command line illustrates how to use it::
        $ vtkpython .../server.py
    Any ParaViewWeb executable script comes with a set of standard arguments that can be overrides if need be::
        --port 8080
            Port number on which the HTTP server will listen.
        --content /path-to-web-content/
            Directory that you want to serve as static web content.
            By default, this variable is empty which means that we rely on another
            server to deliver the static content and the current process only
            focuses on the WebSocket connectivity of clients.
        --authKey vtkweb-secret
            Secret key that should be provided by the client to allow it to make
            any WebSocket communication. The client will assume if none is given
            that the server expects "vtkweb-secret" as secret key.
"""
import os
import random
import sys
import argparse
import json

# Try handle virtual env if provided
if '--virtual-env' in sys.argv:
    virtualEnvPath = sys.argv[sys.argv.index('--virtual-env') + 1]
    virtualEnv = virtualEnvPath + '/bin/activate_this.py'
    if 'execfile' in dir():
        execfile(virtualEnv, dict(__file__=virtualEnv))
    else:
        exec(open(virtualEnv).read(), dict(__file__=virtualEnv))

# from __future__ import absolute_import, division, print_function

from wslink import server
from wslink import register as exportRpc

from vtk.web import wslink as vtk_wslink
from vtk.web import protocols as vtk_protocols

import vtk
import base64
import time
# import Twisted reactor for later callback
from twisted.internet import reactor

import numpy as np
from fury import actor, window


# =============================================================================
#
# Provide publish-based Image delivery mechanism
#
# =============================================================================

class vtkWebPublishImageDelivery(vtk_protocols.vtkWebProtocol):
    def __init__(self, decode=True):
        super(vtkWebPublishImageDelivery, self).__init__()
        self.trackingViews = {}
        self.lastStaleTime = 0
        self.staleHandlerCount = 0
        self.deltaStaleTimeBeforeRender = 0.5  # 0.5s
        self.decode = decode
        self.viewsInAnimations = []
        self.targetFrameRate = 30.0
        self.minFrameRate = 12.0
        self.maxFrameRate = 30.0

    def pushRender(self, vId, ignoreAnimation=False):
        if vId not in self.trackingViews:
            return

        if not self.trackingViews[vId]["enabled"]:
            return

        if not ignoreAnimation and len(self.viewsInAnimations) > 0:
            return

        if "originalSize" not in self.trackingViews[vId]:
            view = self.getView(vId)
            self.trackingViews[vId]["originalSize"] = list(view.GetSize())

        if "ratio" not in self.trackingViews[vId]:
            self.trackingViews[vId]["ratio"] = 1

        ratio = self.trackingViews[vId]["ratio"]
        mtime = self.trackingViews[vId]["mtime"]
        quality = self.trackingViews[vId]["quality"]
        size = [int(s * ratio)
                for s in self.trackingViews[vId]["originalSize"]]

        reply = self.stillRender({"view": vId,
                                  "mtime": mtime,
                                  "quality": quality,
                                  "size": size})
        stale = reply["stale"]
        if reply["image"]:
            # depending on whether the app has encoding enabled:
            if self.decode:
                reply["image"] = base64.standard_b64decode(reply["image"])

            reply["image"] = self.addAttachment(reply["image"])
            reply["format"] = "jpeg"
            # save mtime for next call.
            self.trackingViews[vId]["mtime"] = reply["mtime"]
            # echo back real ID, instead of -1 for 'active'
            reply["id"] = vId
            self.publish('viewport.image.push.subscription', reply)
        if stale:
            self.lastStaleTime = time.time()
            if self.staleHandlerCount == 0:
                self.staleHandlerCount += 1
                reactor.callLater(self.deltaStaleTimeBeforeRender,
                                  lambda: self.renderStaleImage(vId))
        else:
            self.lastStaleTime = 0

    def renderStaleImage(self, vId):
        self.staleHandlerCount -= 1

        if self.lastStaleTime != 0:
            delta = (time.time() - self.lastStaleTime)
            if delta >= self.deltaStaleTimeBeforeRender:
                self.pushRender(vId)
            else:
                self.staleHandlerCount += 1
                reactor.callLater(self.deltaStaleTimeBeforeRender - delta + 0.001, lambda: self.renderStaleImage(vId))

    def animate(self):
        if len(self.viewsInAnimations) == 0:
            return

        nextAnimateTime = time.time() + 1.0 / self.targetFrameRate
        for vId in self.viewsInAnimations:
            self.pushRender(vId, True)

        nextAnimateTime -= time.time()

        if self.targetFrameRate > self.maxFrameRate:
            self.targetFrameRate = self.maxFrameRate

        if nextAnimateTime < 0:
            if nextAnimateTime < -1.0:
                self.targetFrameRate = 1
            if self.targetFrameRate > self.minFrameRate:
                self.targetFrameRate -= 1.0
            reactor.callLater(0.001, lambda: self.animate())
        else:
            if self.targetFrameRate < self.maxFrameRate and nextAnimateTime > 0.005:
                self.targetFrameRate += 1.0
            reactor.callLater(nextAnimateTime, lambda: self.animate())

    @exportRpc("viewport.image.animation.fps.max")
    def setMaxFrameRate(self, fps=30):
        self.maxFrameRate = fps

    @exportRpc("viewport.image.animation.fps.get")
    def getCurrentFrameRate(self):
        return self.targetFrameRate

    @exportRpc("viewport.image.animation.start")
    def startViewAnimation(self, viewId='-1'):
        sView = self.getView(viewId)
        realViewId = str(self.getGlobalId(sView))

        self.viewsInAnimations.append(realViewId)
        if len(self.viewsInAnimations) == 1:
            self.animate()

    @exportRpc("viewport.image.animation.stop")
    def stopViewAnimation(self, viewId='-1'):
        sView = self.getView(viewId)
        realViewId = str(self.getGlobalId(sView))

        if realViewId in self.viewsInAnimations:
            self.viewsInAnimations.remove(realViewId)

    @exportRpc("viewport.image.push")
    def imagePush(self, options):
        sView = self.getView(options["view"])
        realViewId = str(self.getGlobalId(sView))
        # Make sure an image is pushed
        self.getApplication().InvalidateCache(sView)
        self.pushRender(realViewId)

    # Internal function since the reply[image] is not
    # JSON(serializable) it can not be an RPC one
    def stillRender(self, options):
        """
        RPC Callback to render a view and obtain the rendered image.
        """
        beginTime = int(round(time.time() * 1000))
        view = self.getView(options["view"])
        size = view.GetSize()[0:2]
        resize = size != options.get("size", size)
        if resize:
            size = options["size"]
            if size[0] > 10 and size[1] > 10:
                view.SetSize(size)
        t = 0
        if options and "mtime" in options:
            t = options["mtime"]
        quality = 100
        if options and "quality" in options:
            quality = options["quality"]
        localTime = 0
        if options and "localTime" in options:
            localTime = options["localTime"]
        reply = {}
        app = self.getApplication()
        if t == 0:
            app.InvalidateCache(view)
        if self.decode:
            stillRender = app.StillRenderToString
        else:
            stillRender = app.StillRenderToBuffer
        reply_image = stillRender(view, t, quality)

        # Check that we are getting image size we have set if not wait until we
        # do. The render call will set the actual window size.
        tries = 10
        while resize and list(view.GetSize()) != size \
              and size != [0, 0] and tries > 0:
            app.InvalidateCache(view)
            reply_image = stillRender(view, t, quality)
            tries -= 1

        if not resize and options and ("clearCache" in options) and options["clearCache"]:
            app.InvalidateCache(view)
            reply_image = stillRender(view, t, quality)

        reply["stale"] = app.GetHasImagesBeingProcessed(view)
        reply["mtime"] = app.GetLastStillRenderToMTime()
        reply["size"] = view.GetSize()[0:2]
        reply["memsize"] = reply_image.GetDataSize() if reply_image else 0
        reply["format"] = "jpeg;base64" if self.decode else "jpeg"
        reply["global_id"] = str(self.getGlobalId(view))
        reply["localTime"] = localTime
        if self.decode:
            reply["image"] = reply_image
        else:
            # Convert the vtkUnsignedCharArray into a bytes object, required by Autobahn websockets
            reply["image"] = memoryview(reply_image).tobytes() if reply_image else None

        endTime = int(round(time.time() * 1000))
        reply["workTime"] = (endTime - beginTime)

        return reply

    @exportRpc("viewport.image.push.observer.add")
    def addRenderObserver(self, viewId):
        sView = self.getView(viewId)
        if not sView:
            return {'error': 'Unable to get view with id %s' % viewId}

        realViewId = str(self.getGlobalId(sView))

        if not realViewId in self.trackingViews:
            observerCallback = lambda *args, **kwargs: self.pushRender(realViewId)
            startCallback = lambda *args, **kwargs: self.startViewAnimation(realViewId)
            stopCallback = lambda *args, **kwargs: self.stopViewAnimation(realViewId)
            tag = self.getApplication().AddObserver('UpdateEvent', observerCallback)
            tagStart = self.getApplication().AddObserver('StartInteractionEvent', startCallback)
            tagStop = self.getApplication().AddObserver('EndInteractionEvent', stopCallback)
            # TODO: do we need
            # self.getApplication().AddObserver('ResetActiveView', resetActiveView())
            self.trackingViews[realViewId] = {'tags': [tag, tagStart, tagStop],
                                              'observerCount': 1,
                                              'mtime': 0,
                                              'enabled': True,
                                              'quality': 100}
        else:
            # There is an observer on this view already
            self.trackingViews[realViewId]['observerCount'] += 1

        self.pushRender(realViewId)
        return {'success': True, 'viewId': realViewId}

    @exportRpc("viewport.image.push.observer.remove")
    def removeRenderObserver(self, viewId):
        sView = self.getView(viewId)
        if not sView:
            return {'error': 'Unable to get view with id %s' % viewId}

        realViewId = str(self.getGlobalId(sView))

        observerInfo = None
        if realViewId in self.trackingViews:
            observerInfo = self.trackingViews[realViewId]

        if not observerInfo:
            return {'error': 'Unable to find subscription for view %s' % realViewId}

        observerInfo['observerCount'] -= 1

        if observerInfo['observerCount'] <= 0:
            for tag in observerInfo['tags']:
                self.getApplication().RemoveObserver(tag)
            del self.trackingViews[realViewId]

        return { 'result': 'success' }

    @exportRpc("viewport.image.push.quality")
    def setViewQuality(self, viewId, quality, ratio=1):
        sView = self.getView(viewId)
        if not sView:
            return {'error': 'Unable to get view with id %s' % viewId}

        realViewId = str(self.getGlobalId(sView))
        observerInfo = None
        if realViewId in self.trackingViews:
            observerInfo = self.trackingViews[realViewId]

        if not observerInfo:
            return {'error': 'Unable to find subscription for view %s' % realViewId}

        observerInfo['quality'] = quality
        observerInfo['ratio'] = ratio

        # Update image size right now!
        if "originalSize" in self.trackingViews[realViewId]:
            size = [int(s * ratio) for s in self.trackingViews[realViewId]["originalSize"]]
            if hasattr(sView, 'SetSize'):
                sView.SetSize(size)
            else:
                sView.ViewSize = size

        return {'result': 'success'}

    @exportRpc("viewport.image.push.original.size")
    def setViewSize(self, viewId, width, height):
        sView = self.getView(viewId)
        if not sView:
            return {'error': 'Unable to get view with id %s' % viewId}

        realViewId = str(self.getGlobalId(sView))
        observerInfo = None
        if realViewId in self.trackingViews:
            observerInfo = self.trackingViews[realViewId]

        if not observerInfo:
            return {'error': 'Unable to find subscription for view %s' % realViewId}

        observerInfo['originalSize'] = [width, height]

        return {'result': 'success'}

    @exportRpc("viewport.image.push.enabled")
    def enableView(self, viewId, enabled):
        sView = self.getView(viewId)
        if not sView:
            return {'error': 'Unable to get view with id %s' % viewId}

        realViewId = str(self.getGlobalId(sView))
        observerInfo = None
        if realViewId in self.trackingViews:
            observerInfo = self.trackingViews[realViewId]

        if not observerInfo:
            return {'error': 'Unable to find subscription for view %s' % realViewId}

        observerInfo['enabled'] = enabled

        return {'result': 'success'}

    @exportRpc("viewport.image.push.invalidate.cache")
    def invalidateCache(self, viewId):
        sView = self.getView(viewId)
        if not sView:
            return {'error': 'Unable to get view with id %s' % viewId}

        self.getApplication().InvalidateCache(sView)
        self.getApplication().InvokeEvent('UpdateEvent')
        return {'result': 'success'}


# -------------------------------------------------------------------------
# ViewManager
# -------------------------------------------------------------------------

class MouseWheel(vtk_protocols.vtkWebProtocol):

    @exportRpc("viewport.mouse.zoom.wheel")
    def updateZoomFromWheel(self, event):
        if 'Start' in event["type"]:
            self.getApplication().InvokeEvent('StartInteractionEvent')

        renderWindow = self.getView(event['view'])
        if renderWindow and 'spinY' in event:
            zoomFactor = 1.0 - event['spinY'] / 10.0

            camera = renderWindow.GetRenderers().GetFirstRenderer().GetActiveCamera()
            fp = camera.GetFocalPoint()
            pos = camera.GetPosition()
            delta = [fp[i] - pos[i] for i in range(3)]
            camera.Zoom(zoomFactor)

            pos2 = camera.GetPosition()
            camera.SetFocalPoint([pos2[i] + delta[i] for i in range(3)])
            renderWindow.Modified()

        if 'End' in event["type"]:
            self.getApplication().InvokeEvent('EndInteractionEvent')


# =============================================================================
# Server class
# =============================================================================

class _Server(vtk_wslink.ServerProtocol):
    # Defaults
    authKey = "wslink-secret"
    view = None

    @staticmethod
    def add_arguments(parser):
        parser.add_argument("--virtual-env", default=None,
                            help="Path to virtual environment to use")
        parser.add_argument("--data", default="/pvw/data", help="path to data directory to list, or else multiple directories given as 'name1=path1|name2=path2|...'", dest="path")
        parser.add_argument("--load-centers", default=None, help="Centers File to load if any based on data-dir base path", dest="centers")
        parser.add_argument("--load-sims", default=None, help="Simulations File to load if any based on data-dir base path", dest="sims")

    @staticmethod
    def configure(args):
        # Standard args
        _Server.authKey = args.authKey
        _Server.dataDir = args.path
        if args.centers:
            _Server.centersToLoad = os.path.join(args.path, args.centers)
        if args.sims:
            _Server.simsToLoad = os.path.join(args.path, args.sims)

    def initialize(self):
        # Bring used components
        self.registerVtkWebProtocol(vtk_protocols.vtkWebMouseHandler())
        self.registerVtkWebProtocol(vtk_protocols.vtkWebViewPort())
        self.registerVtkWebProtocol(vtkWebPublishImageDelivery(decode=False))

        # Custom API
        self.registerVtkWebProtocol(MouseWheel())

        # tell the C++ web app to use no encoding.
        # ParaViewWebPublishImageDelivery must be set to decode=False to match.
        self.getApplication().SetImageEncoding(0)

        # Update authentication key to use
        self.updateSecret(_Server.authKey)

        if not _Server.view:
            scene = window.Scene()
            scene.background((1, 1, 1))

            if os.path.isfile(_Server.centersToLoad):
                with open(_Server.centersToLoad) as f:
                    f_dict = json.loads(f.read())
                centers = np.array(f_dict["centers"])
                n_points = len(centers)
                colors = np.array(f_dict["colors"])
                directions = np.random.rand(n_points, 3)
            else:
                n_points = 10000
                translate = 100
                centers = translate * np.random.rand(n_points, 3) - translate / 2
                colors = 255 * np.random.rand(n_points, 3)

                directions = np.random.rand(n_points, 3)
            # scales = np.random.rand(n_points, 3)

            prim_type = ['sphere', 'ellipsoid', 'torus']
            primitive = [random.choice(prim_type) for _ in range(n_points)]

            sdf_actor = actor.sdf(centers, directions,
                                  colors, primitive)
            scene.add(sdf_actor)
            scene.add(actor.axes())

            showm = window.ShowManager(scene)

            renderWindow = showm.window
            showm.iren.EnableRenderOff()

            self.getApplication().GetObjectIdMap().SetActiveObject("VIEW", renderWindow)

# =============================================================================
# Main: Parse args and start serverviewId
# =============================================================================


if __name__ == "__main__":
    # Create argument parser
    parser = argparse.ArgumentParser(description="SDF example")

    # Add arguments
    server.add_arguments(parser)
    _Server.add_arguments(parser)
    args = parser.parse_args()
    _Server.configure(args)

    # Start server
    server.start_webserver(options=args, protocol=_Server, disableLogging=True)