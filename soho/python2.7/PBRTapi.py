from __future__ import print_function, division, absolute_import
from contextlib import contextmanager

import soho

PBRT_COMMENT = '#'

# Identity
def _api_call(directive):
    soho.indent()
    print(directive)

# Translate x y z
def _api_call_with_args(directive, *args):
    soho.indent()
    print(directive, end='')
    soho.printArray(' ', args, '\n')

# ActiveTransform StartTime
def _api_call_with_cmds(directive, *args):
    soho.indent()
    print(directive, end='')
    soho.printArray(' ', args, '\n', False)

# Transform [ 0 1 2 3 4 5 ... 13 14 15 ]
def _api_call_with_iter(directive, args):
    soho.indent()
    print(directive, end='')
    soho.printArray(' [ ', args, ' ]\n')

# Film "image" "string filename" [ "pbrt.exr" ]
def _api_dtype_call(directive, dtype, paramset=None):
    soho.indent()
    print(directive, ' "', dtype, '"', sep='', end='')
    if paramset:
        for param in paramset:
            print(' ', sep='', end='')
            param.print_str()
    print()

# MakeNamedMaterial "myplastic" "string type" "plastic" "float roughness"
# Texture "name" "texture|spectrum" "dtype" parmlist
def _api_named_dtype_call(directive, name, output, dtype, paramset=None):
    soho.indent()
    print(directive,
          '"{name}" "{output}" "{dtype}"'.format(name=name,
                                                 output=output,
                                                 dtype=dtype),
          end='')
    if paramset:
        for param in paramset:
            print(' ', param.as_str(), sep='', end='')
    print()

def _api_geo_handler(dtype, paramset=None):
    _api_dtype_call('Shape', dtype, paramset)

def Include(path):
    _api_call_with_args('Include', path)

def Comment(msg):
    soho.indent()
    print('# ', msg)

def Film(dtype, paramset=()):
    _api_dtype_call('Film', dtype, paramset)

def Filter(dtype, paramset=()):
    _api_dtype_call('PixelFilter', dtype, paramset)

def Sampler(dtype, paramset=()):
    _api_dtype_call('Sampler', dtype, paramset)

def Integrator(dtype, paramset=()):
    _api_dtype_call('Integrator', dtype, paramset)

def Accelerator(dtype, paramset=()):
    _api_dtype_call('Accelerator', dtype, paramset)

def Camera(dtype, paramset=()):
    _api_dtype_call('Camera', dtype, paramset)

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

def ActiveTransform(xform_time):
    if xform_time not in ('StartTime', 'EndTime', 'All'):
        raise ValueError('%s is an invalid ActiveTransform time' % xform_time)
    _api_call_with_cmds('ActiveTransform', xform_time)

def TransformBegin():
    soho.indent(1, 'TransformBegin', PBRT_COMMENT)

def TransformEnd():
    soho.indent(-1, 'TransformEnd', PBRT_COMMENT)

def AttributeBegin():
    soho.indent(1, 'AttributeBegin', PBRT_COMMENT)

def AttributeEnd():
    soho.indent(-1, 'AttributeEnd', PBRT_COMMENT)

def ObjectBegin(name):
    soho.indent(1, 'ObjectBegin "%s"' % name, PBRT_COMMENT)

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

def Material(dtype, paramset=()):
    _api_dtype_call('Material', dtype, paramset)

# NOTE: Named materials obey AttributeBegin/End blocks as well
def MakeNamedMaterial(name, output, dtype, paramset=()):
    _api_named_dtype_call('MakeNamedMaterial', name, output, dtype, paramset)

def NamedMaterial(name):
    _api_call_with_args('NamedMaterial', name)

def Texture(name, output, dtype, paramset=()):
    _api_named_dtype_call('Texture', name, output, dtype, paramset)

def MakeNamedMedium(name, dtype, paramset=()):
    _api_named_dtype_call('MakeNamedMedium', name, 'string type', dtype, paramset)

def MediumInterface(interior, exterior):
    _api_call_with_args('MediumInterface', interior, exterior)

def LightSource(dtype, paramset=()):
    _api_dtype_call('LightSource', dtype, paramset)

def AreaLightSource(dtype, paramset=()):
    _api_dtype_call('AreaLightSource', dtype, paramset)

def Shape(dtype, paramset=()):
    _api_geo_handler(dtype, paramset)

@contextmanager
def WorldBlock():
    WorldBegin()
    yield
    WorldEnd()

@contextmanager
def AttributeBlock():
    AttributeBegin()
    yield
    AttributeEnd()

@contextmanager
def TransformBlock():
    TransformBegin()
    yield
    TransformEnd()

@contextmanager
def ObjectBlock(name):
    ObjectBegin(name)
    yield
    ObjectEnd()

# Helper context
@contextmanager
def NullBlock():
    yield

