import copy

import hou
import soho
import sohog

from sohog import SohoGeometry

import PBRTapi as api
from PBRTplugins import PBRTParam, ParamSet, BasePlugin, pbrt_param_from_ref

def override_to_paramset(material, override_str):
    override = eval(override_str)
    if not override or not material:
        return
    node = hou.node(material)
    if not node:
        return
    paramset = ParamSet()
    processed_parms = set()
    for parm_name in override:
        parm = node.parm(parm_name)
        if parm is None:
            continue
        parm_tuple = parm.tuple()
        if parm_tuple.name() in processed_parms:
            continue
        value = [ override[x.name()] for x in parm_tuple ]
        pbrt_param = pbrt_param_from_ref(parm_tuple, value)
        paramset.add(pbrt_param)
    return paramset

def sphere_wrangler(gdp, paramset=None):
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    for prim_num in xrange(num_prims):
        with api.TransformBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            api.ConcatTransform(xform)
            api.Shape('sphere', paramset)
    return

def disk_wrangler(gdp, paramset=None):
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    for prim_num in xrange(num_prims):
        with api.TransformBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            api.ConcatTransform(xform)
            api.Shape('disk', paramset)
    return

def tube_wrangler(gdp, paramset=None):
    if paramset is None:
        paramset = ParamSet()
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    # This always returns 1, so use 'intrinsic:tubetaper' instead
    # taper_h = gdp.attribute('geo:prim', 'geo:tubetaper')
    taper_h = gdp.attribute('geo:prim', 'intrinsic:tubetaper')
    closed_h = gdp.attribute('geo:prim', 'geo:primclose')

    for prim_num in xrange(num_prims):
        shape_paramset = copy.copy(paramset)
        with api.TransformBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            taper = gdp.value(taper_h, prim_num)[0]
            closed = gdp.value(closed_h, prim_num)[0]
            api.ConcatTransform(xform)
            api.Rotate(-90, 1, 0, 0)
            if taper == 0:
                shape = 'cone'
                api.Translate(0, 0, -0.5)
            else:
                shape = 'cylinder'
                shape_paramset.add(PBRTParam('float', 'zmin', -0.5))
                shape_paramset.add(PBRTParam('float', 'zmax', 0.5))
            api.Shape(shape, shape_paramset)

            if closed:
                disk_paramset = copy.copy(paramset)
                if shape == 'cylinder':
                    disk_paramset.add(PBRTParam('float', 'height', 0.5))
                    api.Shape('disk', disk_paramset)
                    disk_paramset.add(PBRTParam('float', 'height', -0.5))
                    api.Shape('disk', disk_paramset)
                else:
                    disk_paramset.add(PBRTParam('float', 'height', 0))
                    api.Shape('disk', disk_paramset)
    return


shape_wranglers = { 'Sphere': sphere_wrangler,
                    'Circle' : disk_wrangler,
                    'Tube' : tube_wrangler,
                  }

def shape_splits(gdp):
    # intrinsic:primitivecount returns the FULL gdp's count,
    # not the current partition's primcount
    num_prims = gdp.globalValue('geo:primcount')[0]

    prim_name_h = gdp.attribute('geo:prim','intrinsic:typename')
    for prim_num in xrange(num_prims):
        prim_name = gdp.value(prim_name_h, prim_num)[0]
        yield prim_name
    return

def save_geo(soppath, now):
    # split by material
        # split by material override #
            # split by geo type

    gdp = SohoGeometry(soppath, now)

    # Partition based on materials
    global_material = gdp.globalValue('shop_materialpath')
    if global_material is not None:
        global_material = global_material[0]

    attrib_h = gdp.attribute('geo:prim', 'shop_materialpath')
    if attrib_h >= 0:
        material_gdps = gdp.partition('geo:partattrib',
                                      'shop_materialpath')
    else:
        material_gdps = {global_material : gdp}

    global_override = gdp.globalValue('material_override')
    if global_override is not None:
        global_override = global_override[0]

    # Further partition based on material overrides
    attrib_h = gdp.attribute('geo:prim', 'material_override')
    for material in material_gdps:

        if material:
            api.AttributeBegin()
            api.NamedMaterial(material)

        material_gdp = material_gdps[material]

        if attrib_h >= 0:
            override_gdps = material_gdp.partition('geo:partattrib',
                                                   'material_override')
        else:
            override_gdps = {global_override: material_gdp}

        for override in override_gdps:
            override_gdp = override_gdps[override]
            shape_gdps = override_gdp.partition('geo:partlist',
                                                shape_splits(override_gdp))
            for shape in shape_gdps:
                if override and material:
                    paramset = override_to_paramset(material, override)
                else:
                    paramset = None
                shape_gdp = shape_gdps[shape]
                shape_wrangler = shape_wranglers.get(shape)
                if shape_wrangler:
                    shape_wrangler(shape_gdp, paramset)

        if material:
            api.AttributeEnd()


