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


import PBRTapi as api
from PBRTplugins import PBRTParam
from PBRTwranglers import *


def geo_ids(geo):
    primcount = geo.globalValue('geo:primcount')[0]
    geoid_attrib = geo.attribute('geo:prim', 'intrinsic:geometryid')
    for prim in xrange(primcount):
        geoid = geo.value(geoid_attrib, prim)[0]
        yield str(geoid)

#for obj in soho.objectList('objlist:instance'):
#    soppath = []
#    obj.evalString('object:soppath', now, soppath)
#    print soppath
#    print obj.getName()
#    geo = SohoGeometry(soppath[0], now)
#    if geo.Handle < 0:
#        continue
#    splits = geo.partition('geo:partattrib', 'geo:primname')
#    packed_geo = splits.get('PackedGeometry')
#    if not packed_geo:
#        continue
#    packed_parts = packed_geo.partition('geo:partlist', geo_ids(packed_geo))
#    print 'hi'
#    print packed_parts
#    polys = packed_parts['22'].tesselate({})
#    print polys.globalValue('geo:primcount')[0]

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

#wrangler = getWrangler(cam, now, 'camera_wrangler')
wrangler = None
rop = soho.getOutputDriver()

api.Film(*wrangle_film(cam, wrangler, now))
api.Filter(*wrangle_filter(cam, wrangler, now))
api.Sampler(*wrangle_sampler(cam, wrangler, now))
api.Integrator(*wrangle_integrator(cam, wrangler, now))
api.Accelerator(*wrangle_accelerator(cam, wrangler, now))
api.Camera(*wrangle_camera(cam, wrangler, now))

print ''
api.WorldBegin()

api.LightSource('infinite')
api.Identity()

api.AttributeBegin()
api.Translate(5,0,0)
api.Shape('sphere', [PBRTParam('float', 'radius', [1])])
api.AttributeEnd()
api.Shape('sphere', [PBRTParam('float', 'radius', [1])])

api.WorldEnd()
