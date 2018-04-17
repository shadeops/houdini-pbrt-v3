import sys
import time

import hou
import soho
import sohog

from soho import SohoParm
from sohog import SohoGeometry

import PBRTapi
reload(PBRTapi)
import PBRTplugins
reload(PBRTplugins)
import PBRTwranglers
reload(PBRTwranglers)
import PBRTscene
reload(PBRTscene)

clockstart = time.time()

control_parms = {
    # The time at which the scene is being rendered
    'now'     : SohoParm('state:time',  'real', [0], False,  key='now'),
    'fps'     : SohoParm('state:fps',   'real', [24], False, key='fps'),
    'camera'  : SohoParm('camera', 'string', ['/obj/cam1'], False),
}

parms = soho.evaluate(control_parms)

now     = parms['now'].Value[0]
camera  = parms['camera'].Value[0]
fps     = parms['fps'].Value[0]

options = {'state:precision' : 6}
if not soho.initialize(now, camera, options):
    soho.error("Unable to initialize rendering module with given camera")

object_selection = {
    # Candidate object selection
    'vobject'     : SohoParm('vobject', 'string',       ['*'], False),
    'alights'     : SohoParm('alights', 'string',       ['*'], False),

    'forceobject' : SohoParm('forceobject',     'string',       [''], False),
    'forcelights' : SohoParm('forcelights',     'string',       [''], False),

    'excludeobject' : SohoParm('excludeobject', 'string',       [''], False),
    'excludelights' : SohoParm('excludelights', 'string',       [''], False),

    'sololight'     : SohoParm('sololight',     'string',       [''], False),
}

for cam in soho.objectList('objlist:camera'):
    break
else:
    soho.error("Unable to find viewing camera for render")

objparms = cam.evaluate(object_selection, now)

stdobject = objparms['vobject'].Value[0]
stdlights = objparms['alights'].Value[0]
forceobject = objparms['forceobject'].Value[0]
forcelights = objparms['forcelights'].Value[0]
excludeobject = objparms['excludeobject'].Value[0]
excludelights = objparms['excludelights'].Value[0]
sololight = objparms['sololight'].Value[0]
forcelightsparm = 'forcelights'

if sololight:
    stdlights = excludelights = None
    forcelights = sololight
    forcelightsparm = 'sololight'

# First, we add objects based on their display flags or dimmer values
soho.addObjects(now, stdobject, stdlights, '', True)
soho.addObjects(now, forceobject, forcelights, '', False)
soho.removeObjects(now, excludeobject, excludelights, '')

# Lock off the objects we've selected
soho.lockObjects(now)

clockstart = time.time()

PBRTscene.render(cam, now, soho.objectList('objlist:instance'),
                           soho.objectList('objlist:light'))

