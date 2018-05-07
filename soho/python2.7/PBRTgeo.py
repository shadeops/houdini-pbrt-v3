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

def disk_wrangler(gdp, paramset=None):

    # NOTE: PBRT's and Houdini's parameteric UVs are different
    # so when using textures this will need to be fixed on the
    # texture/material side as its not resolvable within Soho.
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    for prim_num in xrange(num_prims):
        with api.TransformBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            api.ConcatTransform(xform)
            api.Shape('disk', paramset)

def tube_wrangler(gdp, paramset=None):
    if paramset is None:
        paramset = ParamSet()
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    # SOHO BUG
    # This always returns 1, so use 'intrinsic:tubetaper' instead
    # taper_h = gdp.attribute('geo:prim', 'geo:tubetaper')
    taper_h = gdp.attribute('geo:prim', 'intrinsic:tubetaper')
    closed_h = gdp.attribute('geo:prim', 'geo:primclose')
    prim_h = gdp.attribute('geo:prim', 'geo:number')

    for prim_num in xrange(num_prims):
        shape_paramset = copy.copy(paramset)
        with api.TransformBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            taper = gdp.value(taper_h, prim_num)[0]

            # workaround, see TODO below
            if not (taper == 0 or taper == 1):
                geo_num = gdp.value(prim_h, prim_num)[0]
                api.Comment('Skipping tube, prim # %i, with non-conforming taper of %f' %
                                (geo_num,taper))
                continue

            closed = gdp.value(closed_h, prim_num)[0]
            api.ConcatTransform(xform)
            api.Rotate(-90, 1, 0, 0)
            if taper == 0:
                shape = 'cone'
                api.Translate(0, 0, -0.5)
            elif taper == 1:
                shape = 'cylinder'
                shape_paramset.add(PBRTParam('float', 'zmin', -0.5))
                shape_paramset.add(PBRTParam('float', 'zmax', 0.5))
            else:
                # TODO support hyperboloid, however pbrt currently
                # has no ends of trouble with this shape type
                # crashes or hangs
                pass
            with api.TransformBlock():
                # Flip in Y so parameteric UV's match Houdini's
                api.Scale(1,-1,1)
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

# The following generators could be simplified if we
# assume that each gdp will always have 3 verts thus
# removing the need to constantly fetch the
# geo:vertexcount. (Could be passed as a parm, and if the
# default is None, then compute)

def vtx_attrib_gen(gdp, attrib):
    """ Per prim, per vertex fetching vertex values
    """
    num_prims = gdp.globalValue('geo:primcount')[0]
    vtx_count_h = gdp.attribute('geo:prim', 'geo:vertexcount')
    for prim in xrange(num_prims):
        num_vtx = gdp.value(vtx_count_h, prim)[0]
        # TODO reverse order?
        #for vtx in xrange(num_vtx-1,-1,-1):
        for vtx in xrange(num_vtx):
            # could also use gdp.vertex(attrib, prim, vtx)
            yield gdp.value(attrib, (prim,vtx))

def pt2vtx_attrib_gen(gdp, attrib):
    """ Per prim, per vertex fetching point values
    """
    num_prims = gdp.globalValue('geo:primcount')[0]
    vtx_count_h = gdp.attribute('geo:prim', 'geo:vertexcount')
    p_ref_attrib = gdp.attribute('geo:vertex', 'geo:pointref')
    for prim in xrange(num_prims):
        num_vtx = gdp.value(vtx_count_h, prim)[0]
        for vtx in xrange(num_vtx):
            ptnum = gdp.value(p_ref_attrib, (prim,vtx))[0]
            yield gdp.value(attrib, ptnum)

def linear_vtx_gen(gdp):
    """ generate the linearvertex

    A linear vertex is a unique value for every vertex in the mesh
    where as a vertex number is the vertex offset on a prim

    We need a linear vertex for generating inidices when we have uniqe points
    http://www.sidefx.com/docs/houdini/vex/functions/vertexindex.html
    """
    num_prims = gdp.globalValue('geo:primcount')[0]
    vtx_count_h = gdp.attribute('geo:prim', 'geo:vertexcount')
    i = 0
    for prim in xrange(num_prims):
        num_vtx = gdp.value(vtx_count_h, prim)[0]
        for vtx in xrange(num_vtx):
            yield i
            i+=1

def geo_attrib_gen(gdp, attrib, count):
    """ Per prim/point fetching their values
    """
    for i in xrange(count):
        value = gdp.value(attrib, i)
        yield value

# TODO: The below logic could possibly be simplified a bit by having a
#       GeoAttrib class, which wraps up some of the below functionality.
#       Including auto resolution of vtx or pt attrib, handle, attrib size
#       and application of the correct generator function.

def trianglemesh_wrangler(gdp, paramset=None):
    if paramset is None:
        mesh_paramset = ParamSet()
    else:
        mesh_paramset = copy.copy(paramset)

    # Triangle Meshes in PBRT uses "verticies" to denote positions.
    # These are similar to Houdini "points". Since the PBRT verts
    # are shared between primitives if hard edges or "vertex normals"
    # (Houdini-ese) are required then need to unique the points so
    # so each point can have its own normal.
    # To support this, if any of the triangle mesh params (N, uv, S)
    # are vertex attributes, then we'll uniquify the points.

    # We can only deal with triangles, where Houdini is a bit more
    # general, so we'll need to tesselate
    #
    # NOTE: You'll see references to other options like geo:convstyle
    #       and geo:triangulate. These, as far as I can tell, do not
    #       actually exist. Use the soho.doc or run "strings" on
    #       libHoudiniOP2.so
    options = {
               'tess:style' : 'lod',
               'tess:polysides' : 3,
               'tess:metastyle' : 'lod',
               }

    mesh_gdp = gdp.tesselate(options)
    if not mesh_gdp:
        return None

    unique_points = False

    num_pts = mesh_gdp.globalValue('geo:pointcount')[0]

    # Required
    P_attrib = mesh_gdp.attribute('geo:point', 'P')
    pointref_attrib = mesh_gdp.attribute('geo:vertex', 'geo:pointref')

    # Optional
    N_attrib = mesh_gdp.attribute('geo:vertex', 'N')
    uv_attrib = mesh_gdp.attribute('geo:vertex', 'uv')
    S_attrib = mesh_gdp.attribute('geo:vertex', 'S')

    # We need to unique the points if any of the handles
    # to vtx attributes exists.
    if N_attrib >= 0 or uv_attrib >= 0 or S_attrib >= 0:
        unique_points = True

    # TODO: Add option to disable automatic normals?

    S = None
    uv = None
    N = None

    # We will unique points (verts in PBRT) if any of the attributes are
    # per vertex instead of per point.
    if unique_points:
        P = pt2vtx_attrib_gen(mesh_gdp, P_attrib)
        indices = linear_vtx_gen(mesh_gdp)

        # N is slightly special as we might compute normals automatically.
        if N_attrib >= 0:
            N = vtx_attrib_gen(mesh_gdp, N_attrib)
        else:
            N_attrib = mesh_gdp.normal()
            N = pt2vtx_attrib_gen(mesh_gdp, N_attrib)

        if uv_attrib >= 0:
            uv = vtx_attrib_gen(mesh_gdp, uv_attrib)
        else:
            uv_attrib = mesh_gdp.attribute('geo:point', 'uv')
            if uv_attrib >= 0:
                uv = pt2vtx_attrib_gen(mesh_gdp, uv_attrib)

        if S_attrib >= 0:
            S = vtx_attrib_gen(mesh_gdp, S_attrib)
        else:
            S_attrib = mesh_gdp.attribute('geo:point', 'S')
            if S_attrib >= 0:
                S = pt2vtx_attrib_gen(mesh_gdp, S_attrib)
    else:
        P = geo_attrib_gen(mesh_gdp, P_attrib, num_pts)
        indices = vtx_attrib_gen(mesh_gdp, pointref_attrib)
        N_attrib = mesh_gdp.normal()
        N = geo_attrib_gen(mesh_gdp, N_attrib, num_pts)
        S_attrib = mesh_gdp.attribute('geo:point', 'S')
        if S_attrib >= 0:
            S = geo_attrib_gen(mesh_gdp, S_attrib, num_pts)
        uv_attrib = mesh_gdp.attribute('geo:point', 'uv')
        if uv_attrib >= 0:
            uv = geo_attrib_gen(mesh_gdp, uv_attrib, num_pts)

    mesh_paramset.add(PBRTParam('integer', 'indices', indices))
    mesh_paramset.add(PBRTParam('point', 'P', P))
    mesh_paramset.add(PBRTParam('normal', 'N', N))
    if uv is not None:
        # Houdini's uvs are stored as 3 floats, but pbrt only needs two
        # We'll use a generator comprehension to strip off the extra
        # float.
        uv2 = ( x[0:2] for x in uv )
        mesh_paramset.add(PBRTParam('float', 'uv', uv2))
    if S is not None:
        mesh_paramset.add(PBRTParam('vector', 'S', S))

    api.Shape('trianglemesh', mesh_paramset)

    return None

shape_wranglers = { 'Sphere': sphere_wrangler,
                    'Circle' : disk_wrangler,
                    'Tube' : tube_wrangler,
                    'Poly' : trianglemesh_wrangler,
                    'Mesh' : trianglemesh_wrangler,
                    'MetaBall' : trianglemesh_wrangler,
                    'PolySoup' : trianglemesh_wrangler,
                  }

def shape_splits(gdp):
    # intrinsic:primitivecount returns the FULL gdp's count,
    # not the current partition's primcount
    num_prims = gdp.globalValue('geo:primcount')[0]

    prim_name_h = gdp.attribute('geo:prim','intrinsic:typename')
    for prim_num in xrange(num_prims):
        prim_name = gdp.value(prim_name_h, prim_num)[0]
        yield prim_name

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

