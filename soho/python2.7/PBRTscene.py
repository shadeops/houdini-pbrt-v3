import hou
import soho

import PBRTapi as api
from PBRTwranglers import *
from PBRTplugins import PBRTParam

def render(cam, now, obj_list, light_list):

    # For now we will not be using wranglers
    wrangler = None

    api.Comment('Rendering %s' % soho.getOutputDriver().getName())
    print

    api.Film(*wrangle_film(cam, wrangler, now))
    api.Filter(*wrangle_filter(cam, wrangler, now))
    api.Sampler(*wrangle_sampler(cam, wrangler, now))
    api.Integrator(*wrangle_integrator(cam, wrangler, now))
    api.Accelerator(*wrangle_accelerator(cam, wrangler, now))

    print

    # wrangle_camera will output api.Transforms
    api.Comment(cam.getName())
    api.Camera(*wrangle_camera(cam, wrangler, now))

    print

    api.WorldBegin()

    for light in light_list:
        api.Comment(light.getName())
        api.AttributeBegin()
        wrangle_light(light, wrangler, now)
        api.AttributeEnd()

    for obj in obj_list:
        api.Comment(obj.getName())

    api.TransformBegin()
    api.Translate(0,1.5,0)
    api.TransformEnd()
    api.Rotate(90,1,0,0)
    api.Shape('disk', [PBRTParam('float', 'radius', [10])])
    api.WorldEnd()

    return
