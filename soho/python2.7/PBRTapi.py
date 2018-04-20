from __future__ import print_function

import soho

PBRT_COMMENT = '#'

# Identity
def _api_call(api_call):
    soho.indent()
    print(api_call)

# Translate x y z
def _api_call_with_args(api_call, *args):
    soho.indent()
    print(api_call, end='')
    soho.printArray(' ', args, '\n')

# Transform [ 0 1 2 3 4 5 ... 13 14 15 ]
def _api_call_with_iter(api_call, args):
    soho.indent()
    print(api_call, end='')
    soho.printArray(' [ ', args, ' ]\n')

# Film "image" "string filename" [ "pbrt.exr" ]
def _api_plugin_call(api_call, plugin, paramset):
    soho.indent()
    print(api_call, ' "', plugin, '"', sep='', end='')
    for param in paramset:
        print(' ', param.as_str(), sep='', end='')
    print()

# MakeNamedMaterial "myplastic" "string type" "plastic" "float roughness"
def _api_named_plugin_call(api_call, name, plugin, paramset):
    soho.indent()
    print(api_call, '"{name}" "{plugin}"'.format(name=name,
                                                 plugin=plugin),
                    end='')
    for param in paramset:
        print(' ', param.as_str(), sep='', end='')

# Texture "name" "texture|spectrum" "plugin" parmlist
def _api_named_output_plugin_call(api_call, name, output, plugin, paramset):
    soho.indent()
    print(api_call, '"{name}" "{output}" "{plugin}"'.format(name=name,
                                                            output=output,
                                                            plugin=plugin),
                    end='')
    for param in paramset:
        print(' ', param.as_str(), sep='', end='')
    print()

def _api_geo_handler(plugin, paramset):
    # Quadratics
    if plugin in ('cone', 'cylinder', 'disk', 'hyperboloid',
                  'paraboloid', 'sphere'):
        _api_plugin_call('Shape', plugin, paramset)
        return

    if plugin == 'plymesh':
        _api_plugin_call('Shape', plugin, paramset)
        return

    _api_plugin_call('Shape', plugin, paramset)

    return

def Include(path):
    _api_call_with_args('Include', path)

def Comment(msg):
    soho.indent()
    print('# ', msg)

def Film(plugin, paramset=()):
    _api_plugin_call('Film', plugin, paramset)

def Filter(plugin, paramset=()):
    _api_plugin_call('PixelFilter', plugin, paramset)

def Sampler(plugin, paramset=()):
    _api_plugin_call('Sampler', plugin, paramset)

def Integrator(plugin, paramset=()):
    _api_plugin_call('Integrator', plugin, paramset)

def Accelerator(plugin, paramset=()):
    _api_plugin_call('Accelerator', plugin, paramset)

def Camera(plugin, paramset=()):
    _api_plugin_call('Camera', plugin, paramset)

def Identity():
    _api_call('Identity')

def Translate(tx, ty, tz):
    _api_call_with_args('Translate', tx, ty, tz)

def Scale(tx, ty, tz):
    _api_call_with_args('Scale', tx, ty, tz)

def Rotate(angle, x, y, z):
    _api_call_with_args('Rotate', angle, x, y, z)

def LookAt(eye_x, eye_y, eye_z,
           look_x, look_y, look_z,
           up_x, up_y, up_z):
    _api_call_with_args('LookAt', eye_x, eye_y, eye_z,
                                  look_x, look_y, look_z,
                                  up_x, up_y, up_z)

def CoordinateSystem(name):
    _api_call_with_args('CoordinateSystem', name)

def CoordSysTransform(name):
    _api_call_with_args('CoordSysTransform', name)

def Transform(matrix):
    _api_call_with_iter('Transform', matrix)

def ConcatTransform(matrix):
    _api_call_with_iter('ConcatTransform', matrix)

def TransformTimes(start, end):
    _api_call_with_args('TransfomTimes', start, end)

def ActiveTransform(time):
    _api_call_with_args('ActiveTransform', time)

def TransformBegin():
    soho.indent(1, 'TransformBegin', PBRT_COMMENT)

def TransformEnd():
    soho.indent(-1, 'TransformEnd', PBRT_COMMENT)

def AttributeBegin():
    soho.indent(1, 'AttributeBegin', PBRT_COMMENT)

def AttributeEnd():
    soho.indent(-1, 'AttributeEnd', PBRT_COMMENT)

def ObjectBegin():
    soho.indent(1, 'ObjectBegin', PBRT_COMMENT)

def ObjectEnd():
    soho.indent(-1, 'ObjectEnd', PBRT_COMMENT)

def ObjectInstance(name):
    _api_call_with_args('ObjectInstance', name)

def ReverseOrientation():
    _api_call('ReverseOrientation')

def WorldBegin():
    soho.indent(1, 'WorldBegin', PBRT_COMMENT)

def WorldEnd():
    soho.indent(-1, 'WorldEnd', PBRT_COMMENT)

def Material(plugin, paramset=()):
    _api_plugin_call('Material', plugin, paramset)

def MakeNamedMaterial(name, plugin, paramset=()):
    _api_named_plugin_call('MakeNamedMaterial', name, plugin, paramset)

def NamedMaterial(name):
    _api_call_with_args('NamedMaterial', name)

def Texture(name, output, plugin, paramset=()):
    _api_named_output_plugin_call('Texture', name, output, plugin, paramset)

def LightSource(plugin, paramset=()):
    _api_plugin_call('LightSource', plugin, paramset)

def AreaLightSource(plugin, paramset=()):
    _api_plugin_call('AreaLightSource', plugin, paramset)

def Shape(plugin, paramset=()):
    _api_geo_handler(plugin, paramset)
