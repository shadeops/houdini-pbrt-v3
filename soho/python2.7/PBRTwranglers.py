import math

import hou
import soho

import PBRTapi as api
import PBRTgeo as Geo
from PBRTplugins import PBRTParam, ParamSet, BasePlugin

__all__ = ['wrangle_film', 'wrangle_sampler', 'wrangle_accelerator',
           'wrangle_integrator', 'wrangle_filter', 'wrangle_camera',
           'wrangle_light', 'wrangle_geo']

def _apiclosure(api_call, *args, **kwargs):
    def api_func():
        return api_call(*args, **kwargs)
    return api_func

def xform_to_api_srt(xform, scale=True, rotate=True, trans=True):
    xform = hou.Matrix4(xform)
    srt = xform.explode()
    if trans:
        api.Translate(*srt['translate'])
    if rotate:
        # TODO, be wary of -180 to 180 flips
        rot = srt['rotate']
        if rot.z():
            api.Rotate(rot[2],0,0,1)
        if rot.y():
            api.Rotate(rot[1],0,1,0)
        if rot.x():
            api.Rotate(rot[0],1,0,0)
    if scale:
        api.Scale(*srt['scale'])
    return

class SohoPBRT(soho.SohoParm):
    def to_pbrt(self, pbrt_type=None):
        # bounds not supported
        # shader not supported
        if pbrt_type is None:
            to_pbrt_type = {'real' : 'float',
                            'fpreal' : 'float',
                            'int' : 'integer'}
            pbrt_type = to_pbrt_type.get(self.Type, self.Type)
        pbrt_name = self.Key
        return PBRTParam(pbrt_type, pbrt_name, self.Value)

def get_transform(obj, now, invert=False, flipz=False):
    xform = []
    if not obj.evalFloat('space:world', now, xform):
        return None
    xform = hou.Matrix4(xform)
    if invert:
        xform = xform.inverted()
    if flipz:
        xform = xform*hou.hmath.buildScale(1,1,-1)
    return list(xform.asTuple())

def get_wrangler(obj, now, style):
    wrangler = obj.getDefaultedString(style, now, [''])[0]
    wrangler = '%s-PBRT' % wrangler
    if style == 'light_wrangler':
        wrangler = soho.LightWranglers.get(wrangler, None)
    elif style == 'camera_wrangler':
        wrangler = soho.CameraWranglers.get(wrangler, None)
    elif style == 'object_wrangler':
         wrangler = soho.ObjectWranglers.get(wrangler, None)
    else:
        wrangler = None  # Not supported at the current time

    if wrangler:
        wrangler = wrangler(obj, now, 'PBRT')
    else:
        wrangler = None
    return wrangler

def wrangle_plugin_parm(obj, parm_name, now):

    parm_selection = {
        parm_name : SohoPBRT(parm_name, 'string', [''], False)
    }
    parms = obj.evaluate(parm_selection, now)
    if not parms:
        return None
    plugin_path = parms[parm_name].Value[0]
    if not plugin_path:
        return None
    plugin = BasePlugin(plugin_path)
    return plugin.plugin_class, plugin.paramset

def wrangle_film(obj, wrangler, now):

    plug_nfo = wrangle_plugin_parm(obj, 'film_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    paramset = ParamSet()

    parm_selection = {
        'filename' : SohoPBRT('filename', 'string', ['pbrt.exr'], False),
        'maxsampleluminance' : SohoPBRT('maxsampleluminance', 'float', [1e38], True),
        'diagonal' : SohoPBRT('diagonal', 'float', [35], True),
    }
    parms = obj.evaluate(parm_selection, now)
    for parm_name,parm in parms.iteritems():
        paramset.add(parm.to_pbrt())

    parm_selection = {
        'res' : SohoPBRT('res', 'integer', [1280, 720], False),
    }
    parms = obj.evaluate(parm_selection, now)
    paramset.add(PBRTParam('integer','xresolution',parms['res'].Value[0]))
    paramset.add(PBRTParam('integer','yresolution',parms['res'].Value[1]))

    crop_region = obj.getCameraCropWindow(wrangler, now)
    if crop_region != [0.0, 1.0, 0.0, 1.0]:
        paramset.add(PBRTParam('float','cropwindow',crop_region))

    return ('image', paramset)

def wrangle_filter(obj, wrangler, now):

    plug_nfo = wrangle_plugin_parm(obj, 'filter_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    parm_selection = {
        'filter' : SohoPBRT('filter', 'string', ['gaussian'], False),
        'filter_width' : SohoPBRT('filter_width', 'float', [2.0, 2.0], False),
        'alpha' : SohoPBRT('gauss_alpha', 'float', [2.0], True, key='alpha'),
        'B' : SohoPBRT('mitchell_B', 'float', [0.333333], True, key='B'),
        'C' : SohoPBRT('mitchell_C', 'float', [0.333333], True, key='C'),
        'tau' : SohoPBRT('sinc_tau', 'float', [3], True, key='tau'),
    }
    parms = obj.evaluate(parm_selection, now)

    filter_name = parms['filter'].Value[0]
    paramset = ParamSet()
    xwidth = parms['filter_width'].Value[0]
    ywidth = parms['filter_width'].Value[1]
    paramset.add(PBRTParam('float','xwidth',xwidth))
    paramset.add(PBRTParam('float','ywidth',ywidth))

    if filter_name == 'gaussian' and 'alpha' in parms:
        paramset.add(parms['alpha'].to_pbrt())
    if filter_name == 'mitchell' and 'mitchell_B' in parms:
        paramset.add(parms['B'].to_pbrt())
    if filter_name == 'mitchell' and 'mitchell_C' in parms:
        paramset.add(parms['C'].to_pbrt())
    if filter_name == 'sinc' and 'tau' in parms:
        paramset.add(parms['tau'].to_pbrt())
    return (filter_name, paramset)

def wrangle_sampler(obj, wrangler, now):

    plug_nfo = wrangle_plugin_parm(obj, 'sampler_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    parm_selection = {
        'sampler' : SohoPBRT('sampler', 'string', ['halton'], False),
        'pixelsamples' : SohoPBRT('pixelsamples', 'integer', [16], False),
        'jitter' : SohoPBRT('jitter', 'bool', [1], False),
        'samples' : SohoPBRT('samples', 'integer', [4, 4], False),
        'dimensions' : SohoPBRT('dimensions', 'integer', [4], False),
    }
    parms = obj.evaluate(parm_selection, now)

    sampler_name = parms['sampler'].Value[0]
    paramset = ParamSet()

    if sampler_name == 'stratified':
        xsamples = parms['samples'].Value[0]
        ysamples = parms['samples'].Value[1]
        paramset.add(PBRTParam('integer', 'xsamples', xsamples))
        paramset.add(PBRTParam('integer', 'ysamples', ysamples))
        paramset.add(parms['jitter'].to_pbrt())
        paramset.add(parms['dimensions'].to_pbrt())
    else:
        paramset.add(parms['pixelsamples'].to_pbrt())

    return (sampler_name, paramset)

def wrangle_integrator(obj, wrangler, now):

    plug_nfo = wrangle_plugin_parm(obj, 'integrator_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    parm_selection = {
        'integrator' : SohoPBRT('integrator', 'string', ['path'], False),
        'maxdepth' : SohoPBRT('maxdepth', 'integer', [5], False),
        'rrthreshold' : SohoPBRT('rrthreshold', 'float', [1], True),
        'lightsamplestrategy' :
            SohoPBRT('lightsamplestrategy', 'string', ['spatial'], True),
        'visualizestrategies' :
            SohoPBRT('visualizestrategies', 'toggle', [False], True),
        'visualizeweights' :
            SohoPBRT('visualizeweights', 'toggle', [False], True),
        'iterations' :
            SohoPBRT('iterations', 'integer', [64], True),
        'photonsperiterations' :
            SohoPBRT('photonsperiterations', 'integer', [-1], True),
        'imagewritefrequency' :
            SohoPBRT('imagewritefrequency', 'integer', [2.14748e+09], True),
        'radius' :
            SohoPBRT('radius', 'float', [1], True),
        'bootstrapsamples' :
            SohoPBRT('bootstrapsamples', 'integer', [100000], True),
        'chains' :
            SohoPBRT('chains', 'integer', [1000], True),
        'mutationsperpixel' :
            SohoPBRT('mutataionsperpixel', 'integer', [100], True),
        'largestepprobability' :
            SohoPBRT('largestepprobability', 'float', [0.3], True),
        'sigma' :
            SohoPBRT('sigma', 'float', [0.01], True),
        'strategy' :
            SohoPBRT('strategy', 'string', ['all'], True),
        'nsamples' :
            SohoPBRT('nsamples', 'integer', ['64'], True),
        'cossample' :
            SohoPBRT('cossample', 'toggle', [True], True),
    }

    integrator_parms = {
            'ao' : ['nsamples','cossample'],
            'path' : ['maxdepth','rrthreshold','lightsamplestrategy'],
            'bdpt' : ['maxdepth','rrthreshold','lightsamplestrategy',
                      'visualizestrategies','visualizeweights'],
            'mlt' : ['maxdepth','bootstrapsamples','chains','mutationsperpixel',
                     'largestepprobability','sigma'],
            'sppm' : ['maxdepth','iterations','photonsperiteration',
                      'imagewritefrequency','radius'],
            'whitted' : ['maxdepth'],
            'volpath' : ['maxdepth','rrthreshold','lightsamplestrategy'],
            'directlighting' : ['maxdepth','strategy'],
            }
    parms = obj.evaluate(parm_selection, now)

    integrator_name = parms['integrator'].Value[0]
    paramset = ParamSet()
    for parm_name in integrator_parms[integrator_name]:
        if parm_name not in parms:
            continue
        paramset.add(parms[parm_name].to_pbrt())

    return (integrator_name, paramset)

def wrangle_accelerator(obj, wrangler, now):

    plug_nfo = wrangle_plugin_parm(obj, 'accelerator_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    parm_selection = {
        'accelerator' : SohoPBRT('accelerator', 'string', ['bvh'], False),
    }
    parms = obj.evaluate(parm_selection, now)
    accelerator_name = parms['accelerator'].Value[0]

    if accelerator_name == 'bvh':
        parm_selection = {
            'maxnodeprims' : SohoPBRT('maxnodeprims', 'integer', [4], True),
            'splitmethod' : SohoPBRT('splitmethod', 'string', ['sah'], True),
        }
    else:
        parm_selection = {
            'intersectcost' :
                SohoPBRT('intersectcost', 'integer', [80], True),
            'traversalcostcost' :
                SohoPBRT('traversalcost', 'integer', [1], True),
            'emptybonus' :
                SohoPBRT('emptybonus', 'float', [0.2], True),
            'maxprims' :
                SohoPBRT('maxprims', 'integer', [1], True),
            'kdtree_maxdepth' :
                SohoPBRT('kdtree_maxdepth', 'integer', [1], True,
                          key='maxdepth')
        }
    parms = obj.evaluate(parm_selection, now)

    paramset = ParamSet()

    for parm in parms:
        paramset.add(parms[parm].to_pbrt())

    return (accelerator_name, paramset)

def output_cam_xform(obj, projection, now):
    if projection in ('perspective','orthographic','realistic'):
        xform = get_transform(obj, now, invert=True, flipz=True)
        api.Transform(xform)
    elif projection in ('environment',):
        xform = get_transform(obj, now, invert=True, flipz=False)
        api.Transform(xform)
        api.Rotate(180,0,1,0)
    return

def output_xform(obj, now):
    xform = get_transform(obj, now, invert=False, flipz=False)
    api.Transform(xform)
    return

def wrangle_camera(obj, wrangler, now):

    plug_nfo = wrangle_plugin_parm(obj, 'camera_plugin', now)
    if plug_nfo is not None:
        output_cam_xform(obj, plug_nfo[0], now)
        return plug_nfo

    paramset = ParamSet()

    window = obj.getCameraScreenWindow(wrangler, now)
    parm_selection = {
        'projection' : SohoPBRT('projection', 'string', ['perspective'], False),
        'focal' : SohoPBRT('focal', 'float', [50], False),
        'aperture' : SohoPBRT('aperture', 'float', [41.4214], False),
        'orthowidth' : SohoPBRT('orthowidth', 'float', [2], False),
        'res' : SohoPBRT('res', 'integer', [1280, 720], False),
        'aspect' : SohoPBRT('aspect', 'float', [1], False),
        #'fstop' : SohoPBRT('fstop', 'float', [5.6], True),
        #'focus' : SohoPBRT('focus', 'float', [5], True),
    }

    parms = obj.evaluate(parm_selection, now)
    aspect = parms['aspect'].Value[0]
    aspectfix = aspect * float(parms['res'].Value[0]) / float(parms['res'].Value[1])

    projection = parms['projection'].Value[0]

    if projection == 'perspective':
        projection_name = 'perspective'

        focal = parms['focal'].Value[0]
        aperture = parms['aperture'].Value[0]
        fov = 2.0 * focal / aperture
        fov = 2.0 * math.degrees(math.atan2(1.0, fov))
        paramset.add(PBRTParam('float', 'fov', [fov]))

        screen = [ (window[0] - .5) * 2.0,
                   (window[1] - .5) * 2.0,
                   (window[2] - .5) * 2.0 / aspectfix,
                   (window[3] - .5) * 2.0 / aspectfix ]
        paramset.add(PBRTParam('float', 'screenwindow', screen))

    elif projection == 'ortho':
        projection_name = 'orthographic'

        width = parms['orthowidth'].Value[0]
        screen = [ (window[0] - .5) * width,
                   (window[1] - .5) * width,
                   (window[2] - .5) * width / aspectfix,
                   (window[3] - .5) * width / aspectfix ]
        paramset.add(PBRTParam('float', 'screenwindow', screen))

    elif projection == 'sphere':
        projection_name = 'environment'
    else:
        soho.error('Camera projection setting of %s not supported by PBRT' %
                    projection)

    output_cam_xform(obj, projection_name, now)

    return (projection_name, paramset)

def _to_light_scale(parms):
    # TODO
    # There is a potential issue with using "rgb" types for
    # both L and scale as noted here -
    # https://groups.google.com/d/msg/pbrt/EyT6F-zfBkE/M23oQwGNCAAJ
    # To summarize, when using SpectralSamples instead of RGBSamples, 
    # using an "rgb" type for both L and scale can result in a double application of the D65
    # illuminate.
    #
    # Since Houdini's scale (intensity) parameter is a float this issue should
    # be avoidable.
    #
    # Proper tests are required however.

    intensity = parms['light_intensity'].Value[0]
    exposure = parms['light_exposure'].Value[0]
    scale = intensity*(2.0**exposure)
    return PBRTParam('rgb', 'scale', [scale,]*3)

def wrangle_light(light, wrangler, now):

    plug_nfo = wrangle_plugin_parm(light, 'light_plugin', now)
    if plug_nfo is not None:
        output_xform(light, now)
        return plug_nfo

    parm_selection = {
        'light_wrangler' : SohoPBRT('light_wrangler', 'string', [''], False),
        'light_color' : SohoPBRT('light_color', 'float', [1,1,1], False),
        'light_intensity' : SohoPBRT('light_intensity', 'float', [1], False),
        'light_exposure' : SohoPBRT('light_exposure', 'float', [0], False),
    }
    parms = light.evaluate(parm_selection, now)
    light_wrangler = parms['light_wrangler'].Value[0]

    xform = get_transform(light, now)

    paramset = ParamSet()
    paramset.add(_to_light_scale(parms))

    if light_wrangler == 'HoudiniEnvLight':
        env_map = []
        paramset.add(PBRTParam('rgb','L',parms['light_color'].Value))
        if light.evalString('env_map', now, env_map):
            paramset.add(PBRTParam('string','mapname', env_map))
        api.Transform(xform)
        api.Scale(1,1,-1)
        api.Rotate(90, 0, 0, 1)
        api.Rotate(90, 0, 1, 0)
        api.LightSource('infinite', paramset)
        return
    elif light_wrangler != 'HoudiniLight':
        api.Comment('This light type, %s, is unsupported' % light_wrangler)
        return

    # We are dealing with a standard HoudiniLight type.

    xform = get_transform(light, now)

    light_type = light.wrangleString(wrangler, 'light_type', now, ['point'])[0]

    if light_type in ('sphere','disk','grid','tube','geometry'):
        light_name = 'diffuse'

        single_sided = light.wrangleInt(wrangler, 'singlesided', now, [0])[0]
        visible = light.wrangleInt(wrangler,'light_contribprimary',now,[0])[0]
        size = light.wrangleFloat(wrangler, 'areasize', now, [1,1])
        paramset.add(PBRTParam('rgb', 'L', parms['light_color'].Value))
        paramset.add(PBRTParam('bool', 'twosided', [not single_sided]))

        # This is a mess and needs to be recitified
        # * the Transform crashes despite not having a scale

        xform_to_api_srt(xform, scale=False)

        api.AreaLightSource(light_name, paramset)

        api.AttributeBegin()

        # PBRT only supports uniform scales for non-mesh area lights
        # this is in part due to explicit light's area scaling factor.
        if light_type in ('sphere', 'tube', 'disk'):
            api.Scale(size[0], size[0], size[0])
        else:
            api.Scale(size[0], size[1], size[0])

        # The visibility only applies to hits on the non-emissive side of the light.
        # the emissive side will still be rendered
        if not visible:
            api.Material('none')

        if light_type == 'sphere':
            api.Shape('sphere', [PBRTParam('float','radius',0.5)])
        elif light_type == 'tube':
            api.Rotate(90,0,1,0)
            api.Shape('cylinder',[PBRTParam('float','radius',0.075),
                                  PBRTParam('float','zmin',-0.5),
                                  PBRTParam('float','zmax',0.5)])
        elif light_type == 'disk':
            # A bug was introduced with Issue #154 which requires a -z scale
            # on disk area lights
            # See issue #183
            # api.Scale(1,1,-1)
            api.Shape('disk', [PBRTParam('float', 'radius', [0.5])])
        elif light_type == 'grid':
            api.Shape('trianglemesh', [PBRTParam('integer','indices', [0,3,1,
                                                                        0,2,3]),
                                       PBRTParam('point', 'P', [-0.5, -0.5, 0,
                                                                0.5, -0.5, 0,
                                                                -0.5, 0.5, 0,
                                                                0.5, 0.5, 0])])
        elif light_type == 'geometry':
            api.Comment('TODO')

        api.AttributeEnd()

        return

    cone_enable = light.wrangleInt(wrangler, 'coneenable', now, [0])[0]
    projmap = light.wrangleString(wrangler, 'projmap', now, [''])[0]
    areamap = light.wrangleString(wrangler, 'areamap', now, [''])[0]

    api_calls = []
    api_calls.append(_apiclosure(api.Transform, xform))
    api_calls.append(_apiclosure(api.Scale, 1,1,-1))
    api_calls.append(_apiclosure(api.Scale, 1,-1,1))

    if light_type == 'point':
        paramset.add(PBRTParam('rgb', 'I', parms['light_color'].Value))
        if areamap:
            light_name = 'goniometric'
            paramset.add(PBRTParam('string','mapname',[areamap]))
            api_calls = []
            api_calls.append(_apiclosure(api.Transform, xform))
            api_calls.append(_apiclosure(api.Scale, 1,-1,1))
            api_calls.append(_apiclosure(api.Rotate, 90, 0,1,0))
        elif not cone_enable:
            light_name = 'point'
        else:
            conedelta = light.wrangleFloat(wrangler,'conedelta',now,[10])[0]
            coneangle = light.wrangleFloat(wrangler,'coneangle',now,[45])[0]
            if projmap:
                light_name = 'projection'
                paramset.add(PBRTParam('float','fov',[coneangle]))
                paramset.add(PBRTParam('string','mapname',[projmap]))
            else:
                light_name = 'spot'
                coneangle *= 0.5
                coneangle += conedelta
                paramset.add(PBRTParam('float','coneangle',[coneangle]))
                paramset.add(PBRTParam('float','conedeltaangle',[conedelta]))
    elif light_type == 'distant':
        light_name = light_type
        paramset.add(PBRTParam('rgb','L',parms['light_color'].Value))
    else:
        api.Comment('Light Type, %s, not supported' % light_type)
        return

    for api_call in api_calls:
        api_call()
    api.LightSource(light_name, paramset)

    return

def wrangle_geo(obj, wrangler, now):
    output_xform(obj, now)

    soppath = []
    if not obj.evalString('object:soppath', now, soppath):
        print 'wut'
        return

    Geo.save_geo(soppath[0], now)

