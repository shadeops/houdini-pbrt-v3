import math

import soho

import PBRTapi as api
from PBRTplugins import PBRTParam, BasePlugin

__all__ = ['wrangle_film', 'wrangle_sampler', 'wrangle_accelerator',
           'wrangle_integrator', 'wrangle_filter', 'wrangle_camera']

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

def get_transform(obj, now):
    xform = []
    if not obj.evalFloat('space:world', now, xform):
        return None
    return xform

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
        wrangler = wrangler(obj, now, RIBsettings.theTarget)
    else:
        wrangler = None
    return wrangler

def wrangle_rop_plugin(obj, parm_name, now):

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

    plug_nfo = wrangle_rop_plugin(obj, 'film_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    paramset = []

    parm_selection = {
        'filename' : SohoPBRT('filename', 'string', ['pbrt.exr'], False),
        'maxsampleluminance' : SohoPBRT('maxsampleluminance', 'float', [1e38], True),
        'diagonal' : SohoPBRT('diagonal', 'float', [35], True),
    }
    parms = obj.evaluate(parm_selection, now)
    for parm_name,parm in parms.iteritems():
        paramset.append(parm.to_pbrt())

    parm_selection = {
        'res' : SohoPBRT('res', 'integer', [1280, 720], False),
    }
    parms = obj.evaluate(parm_selection, now)
    paramset.append(PBRTParam('integer','xresolution',parms['res'].Value[0]))
    paramset.append(PBRTParam('integer','yresolution',parms['res'].Value[1]))

    crop_region = obj.getCameraCropWindow(wrangler, now)
    if crop_region != [0.0, 1.0, 0.0, 1.0]:
        paramset.append(PBRTParam('float','cropwindow',crop_region))

    return ('image', paramset)

def wrangle_filter(obj, wrangler, now):

    plug_nfo = wrangle_rop_plugin(obj, 'filter_plugin', now)
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
    paramset = []
    xwidth = parms['filter_width'].Value[0]
    ywidth = parms['filter_width'].Value[1]
    paramset.append(PBRTParam('float','xwidth',xwidth))
    paramset.append(PBRTParam('float','ywidth',ywidth))

    if filter_name == 'gaussian' and 'alpha' in parms:
        paramset.append(parms['alpha'].to_pbrt())
    if filter_name == 'mitchell' and 'mitchell_B' in parms:
        paramset.append(parms['B'].to_pbrt())
    if filter_name == 'mitchell' and 'mitchell_C' in parms:
        paramset.append(parms['C'].to_pbrt())
    if filter_name == 'sinc' and 'tau' in parms:
        paramset.append(parms['tau'].to_pbrt())
    return (filter_name, paramset)

def wrangle_sampler(obj, wrangler, now):

    plug_nfo = wrangle_rop_plugin(obj, 'sampler_plugin', now)
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
    paramset = []

    if sampler_name == 'stratified':
        xsamples = parms['samples'].Value[0]
        ysamples = parms['samples'].Value[1]
        paramset.append(PBRTParam('integer', 'xsamples', xsamples))
        paramset.append(PBRTParam('integer', 'ysamples', ysamples))
        paramset.append(parms['jitter'].to_pbrt())
        paramset.append(parms['dimensions'].to_pbrt())
    else:
        paramset.append(parms['pixelsamples'].to_pbrt())

    return (sampler_name, paramset)

def wrangle_integrator(obj, wrangler, now):

    plug_nfo = wrangle_rop_plugin(obj, 'integrator_plugin', now)
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
    paramset = []
    for parm_name in integrator_parms[integrator_name]:
        if parm_name not in parms:
            continue
        paramset.append(parms[parm_name].to_pbrt())

    return (integrator_name, paramset)

def wrangle_accelerator(obj, wrangler, now):

    plug_nfo = wrangle_rop_plugin(obj, 'accelerator_plugin', now)
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

    paramset = []

    for parm in parms:
        paramset.append(parms[parm].to_pbrt())

    return (accelerator_name, paramset)

def wrangle_camera(obj, wrangler, now):

    xform = get_transform(obj, now)
    api.Transform(xform)

    plug_nfo = wrangle_rop_plugin(obj, 'camera_plugin', now)
    if plug_nfo is not None:
        return plug_nfo

    paramset = []

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
    screen = [ (window[0] - .5) * 2.0,
               (window[1] - .5) * 2.0,
               (window[2] - .5) * 2.0 / aspectfix,
               (window[3] - .5) * 2.0 / aspectfix ]

    projection = parms['projection'].Value[0]

    if projection == 'perspective':
        focal = parms['focal'].Value[0]
        aperture = parms['aperture'].Value[0]
        fov = 2.0 * focal / aperture
        fov = 2.0 * math.degrees(math.atan2(1.0, fov))
        paramset.append(PBRTParam('float', 'fov', [fov]))
        if screen:
            paramset.append(PBRTParam('float', 'screenwindow', screen))

    return (projection, paramset)

