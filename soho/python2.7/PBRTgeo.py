import itertools

import hou
import soho
import sohog

from sohog import SohoGeometry

import PBRTapi as api
from PBRTplugins import PBRTParam, ParamSet, pbrt_param_from_ref

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

def sphere_wrangler(gdp, paramset=None, properties=None):

    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    for prim_num in xrange(num_prims):
        with api.TransformBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            api.ConcatTransform(xform)
            api.Shape('sphere', paramset)

def disk_wrangler(gdp, paramset=None, properties=None):

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

def tube_wrangler(gdp, paramset=None, properties=None):

    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    # SOHO BUG
    # This always returns 1, so use 'intrinsic:tubetaper' instead
    # taper_h = gdp.attribute('geo:prim', 'geo:tubetaper')
    taper_h = gdp.attribute('geo:prim', 'intrinsic:tubetaper')
    closed_h = gdp.attribute('geo:prim', 'geo:primclose')
    prim_h = gdp.attribute('geo:prim', 'geo:number')

    for prim_num in xrange(num_prims):
        shape_paramset = ParamSet(paramset)

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
                disk_paramset = ParamSet(paramset)
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

def prim_pt2vtx_attrib_gen(gdp, attrib, prim):
    """ per vertex fetching point values
    """
    vtx_count_h = gdp.attribute('geo:prim', 'geo:vertexcount')
    p_ref_attrib = gdp.attribute('geo:vertex', 'geo:pointref')
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


def mesh_wrangler(gdp, paramset=None, properties=None):
    if properties is None:
        properties = {}

    mesh_paramset = ParamSet(paramset)

    # Triangle Meshes in PBRT uses "vertices" to denote positions.
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

    # If subdivs are turned on, instead of running the
    # trianglemesh wrangler, use the loop subdiv one instead
    shape = 'trianglemesh'
    if 'pbrt_rendersubd' in properties:
        if properties['pbrt_rendersubd'].Value[0]:
            shape = 'loopsubdiv'

    if shape == 'loopsubdiv':
        wrangler_paramset = loopsubdiv_params(mesh_gdp)
        if 'levels' in properties:
            mesh_paramset.replace(properties['levels'].to_pbrt())
    else:
        computeN = True
        if 'pbrt_computeN' in properties:
            computeN = properties['pbrt_computeN'].Value[0]
        wrangler_paramset = trianglemesh_params(mesh_gdp, computeN)

    mesh_paramset.update(wrangler_paramset)

    api.Shape(shape, mesh_paramset)

    return None

def trianglemesh_params(mesh_gdp, computeN=True):

    mesh_paramset = ParamSet()
    unique_points = False

    num_pts = mesh_gdp.globalValue('geo:pointcount')[0]
    num_prims = mesh_gdp.globalValue('geo:primcount')[0]

    # Required
    P_attrib = mesh_gdp.attribute('geo:point', 'P')
    pointref_attrib = mesh_gdp.attribute('geo:vertex', 'geo:pointref')

    # Optional
    N_attrib = mesh_gdp.attribute('geo:vertex', 'N')
    uv_attrib = mesh_gdp.attribute('geo:vertex', 'uv')
    S_attrib = mesh_gdp.attribute('geo:vertex', 'S')
    faceIndices_attrib = mesh_gdp.attribute('geo:prim', 'faceIndices')

    # TODO: If uv's don't exist, check for 'st', we'll assume uvs are a float[3]
    #       in Houdini and st are a float[2], or we could just auto-convert as
    #       needed.

    # We need to unique the points if any of the handles
    # to vtx attributes exists.
    if N_attrib >= 0 or uv_attrib >= 0 or S_attrib >= 0:
        unique_points = True

    S = None
    uv = None
    N = None
    faceIndices = None

    # TODO: Reevaluate this. If the mesh is tesselated and new polys are
    #       created then the new polys will inherit the existing faceIndices
    #       This may or may not be what we want, for now leave it and work
    #       through use cases later.  Also look at obj2pbrt as a reference
    if faceIndices_attrib >= 0:
        faceIndices = geo_attrib_gen(mesh_gdp, faceIndices_attrib, num_prims)

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
        N_attrib = mesh_gdp.attribute('geo:point', 'N')
        if N_attrib < 0 and computeN:
            N_attrib = mesh_gdp.attribute('geo:point', 'geo:computeN')
        else:
            N_attrib = None
        if N_attrib is not None:
            N = geo_attrib_gen(mesh_gdp, N_attrib, num_pts)
        else:
            N = None
        S_attrib = mesh_gdp.attribute('geo:point', 'S')
        if S_attrib >= 0:
            S = geo_attrib_gen(mesh_gdp, S_attrib, num_pts)
        uv_attrib = mesh_gdp.attribute('geo:point', 'uv')
        if uv_attrib >= 0:
            uv = geo_attrib_gen(mesh_gdp, uv_attrib, num_pts)

    mesh_paramset.add(PBRTParam('integer', 'indices', indices))
    mesh_paramset.add(PBRTParam('point', 'P', P))
    if N is not None:
        mesh_paramset.add(PBRTParam('normal', 'N', N))
    if S is not None:
        mesh_paramset.add(PBRTParam('vector', 'S', S))
    if faceIndices is not None:
        mesh_paramset.add(PBRTParam('integer', 'faceIndices', faceIndices))
    if uv is not None:
        # Houdini's uvs are stored as 3 floats, but pbrt only needs two
        # We'll use a generator comprehension to strip off the extra
        # float.
        uv2 = ( x[0:2] for x in uv )
        mesh_paramset.add(PBRTParam('float', 'uv', uv2))

    return mesh_paramset

def loopsubdiv_params(mesh_gdp):

    mesh_paramset = ParamSet()
    num_pts = mesh_gdp.globalValue('geo:pointcount')[0]

    P_attrib = mesh_gdp.attribute('geo:point', 'P')
    pointref_attrib = mesh_gdp.attribute('geo:vertex', 'geo:pointref')

    P = geo_attrib_gen(mesh_gdp, P_attrib, num_pts)
    indices = vtx_attrib_gen(mesh_gdp, pointref_attrib)

    mesh_paramset.add(PBRTParam('integer', 'indices', indices))
    mesh_paramset.add(PBRTParam('point', 'P', P))

    return mesh_paramset

def volumemode_splits(gdp):
    num_prims = gdp.globalValue('geo:primcount')[0]

    vismode_h = gdp.attribute('geo:prim', 'intrinsic:volumevisualmode')
    for prim_num in xrange(num_prims):
        vismode = gdp.value(vismode_h, prim_num)[0]
        yield vismode

def volume_wrangler(gdp, paramset=None, properties=None):

    # We are going to further partition the volumes based on whether
    # they are a smoke of heightfield.
    volumemode_gdps = gdp.partition('geo:partlist', volumemode_splits(gdp))

    # Heightfield masks are not supported currently
    heightfield_gdps = volumemode_gdps.get('heightfield')
    if heightfield_gdps is not None:
        heightfield_wrangler(heightfield_gdps, paramset, properties)

        # Houdini geometry objects don't allow more than one "volume" set
        # meaning, an object will only ever render one combined volume. That
        # volume could be multiple cloud prims, or multiple heightfields
        # but it can't be a mix of heightfields and clouds. So while not a
        # limitation of pbrt, we'll duplication that logic here.
        return None

    smoke_gdps = volumemode_gdps.get('smoke')
    volumenames_gdps = smoke_gdps.partition('geo:partattrib','name')

    # First we try to find any smoke volumes named density
    density_gdps = volumenames_gdps.get('density')
    if density_gdps is None:
        # If that fails, look for no named ones as they'll be considered
        # density by Houdini
        density_gdps = volumenames_gdps.get('')

    if density_gdps is not None:
        smoke_wrangler(density_gdps, paramset, properties)

def bounds_to_api_box(b):
    paramset = ParamSet()
    paramset.add(PBRTParam('point', 'P', [ b[1], b[2], b[5],
                                           b[0], b[2], b[5],
                                           b[1], b[3], b[5],
                                           b[0], b[3], b[5],
                                           b[0], b[2], b[4],
                                           b[1], b[2], b[4],
                                           b[0], b[3], b[4],
                                           b[1], b[3], b[4] ]))
    paramset.add(PBRTParam('integer', 'indices', [0,3,1,
                                                  0,2,3,
                                                  4,7,5,
                                                  4,6,7,
                                                  6,2,7,
                                                  6,3,2,
                                                  5,1,4,
                                                  5,0,1,
                                                  5,2,0,
                                                  5,7,2,
                                                  1,6,4,
                                                  1,3,6]))
    api.Shape('trianglemesh', paramset)


# NOTE: Handling Medium Parameters
# Approach: shop_materialpath
#           Treat the medium as a material, so if the volume prim
#           has a medium shader as a shop_materialpath (and its overrides)
#           Fetch the params from it (and its possible overrides) and add
#           them to the MakeNamedMedium paramset.
#           Pros: - Much of the functionality is already there
#           Cons: - Conflicts with the concept of a material
#                 - Reqiures excepting when a pbrt_medium is encountered.
#
# Approach: Add a scene iterator to define MakeNamedMediums similar to 
#           MakeNamedMaterials. Then the wranglers can refer to these.
#           Pros: - Cleaner scene file
#           Cons: - Attaching to actual geometry?
#
# Approach: Similar to above, but point to the sop volume in the
#           pbrt_medium. The wrangler would skip volumes when outputing
#           geometry, but then mediums could be applied to shapes.
#           Pros: - Works well with PBRT's design
#           Cons: - Could only reliably attach to objects not prims.
#
#   How to apply heterogeneous mediums to shapes?
#

# NOTE: In pbrt the medium interface and shading parameters
#       are strongly coupled unlike in Houdini/Mantra where
#       the volume shaders define the volume properties and
#       and the volume primitives only define grids.
#
def smoke_wrangler(gdp, paramset=None, properties=None):
    # TODO: Overlapping heterogeneous volumes don't currently
    #       appear to be supported, although this may be an issue
    #       with the Medium interface order? Visually it appears one
    #       object is blocking the other.

    # TODO: Not all samplers support heterogeneous volumes. Determine which
    #       ones do, (and verify this is accurate).
    if properties is None:
        properties = {}

    if ( 'pbrt_ignorevolumes' in properties and 
            properties['pbrt_ignorevolumes'].Value[0]):
        api.Comment('Ignoring volumes because pbrt_ignorevolumes is enabled')
        return

    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    prim_bounds_h = gdp.attribute('geo:prim', 'intrinsic:bounds')
    voxeldata_h = gdp.attribute('geo:prim', 'intrinsic:voxeldata')
    resolution_h = gdp.attribute('geo:prim', 'intrinsic:voxelresolution')
    for prim_num in xrange(num_prims):
        smoke_paramset = ParamSet(paramset)

        # FIXME: Get real prim_num, not partitioned one
        name = '%s[%i]' % (gdp.globalValue('geo:soppath')[0], prim_num)
        resolution = gdp.value(resolution_h, prim_num)
        # TODO: Benchmark this vs other methods like fetching the volume prim
        #       using hou.
        voxels = gdp.value(voxeldata_h, prim_num)
        smoke_paramset.add(PBRTParam('integer','nx', resolution[0]))
        smoke_paramset.add(PBRTParam('integer','ny', resolution[1]))
        smoke_paramset.add(PBRTParam('integer','nz', resolution[2]))
        smoke_paramset.add(PBRTParam('point','p0', [-1,-1,-1]))
        smoke_paramset.add(PBRTParam('point','p1', [1,1,1]))
        smoke_paramset.add(PBRTParam('float','density', voxels))
        # These must be uniform
        smoke_paramset.add(PBRTParam('color','sigma_a',[1, 1, 1]))
        smoke_paramset.add(PBRTParam('color','sigma_s',[1, 1, 1]))
        with api.AttributeBlock():
            xform = gdp.value(prim_xform_h, prim_num)
            api.ConcatTransform(xform)
            api.MakeNamedMedium(name, 'heterogeneous', smoke_paramset)
            api.Material('')
            api.MediumInterface(name, '')
            # Pad this slightly?
            bounds_to_api_box([-1,1,-1,1,-1,1])

def heightfield_wrangler(gdp, paramset=None, properties=None):
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_xform_h = gdp.attribute('geo:prim', 'geo:primtransform')
    resolution_h = gdp.attribute('geo:prim', 'intrinsic:voxelresolution')
    voxeldata_h = gdp.attribute('geo:prim', 'intrinsic:voxeldata')
    for prim_num in xrange(num_prims):
        resolution = gdp.value(resolution_h, prim_num)
        # If the z resolution is not 1 then this really isn't a heightfield
        if resolution[2] != 1:
            continue
        hf_paramset = ParamSet(paramset)
        voxeldata = gdp.value(voxeldata_h, prim_num)
        with api.TransformBlock():

            xform = gdp.value(prim_xform_h, prim_num)
            xform = hou.Matrix4(xform)
            srt = xform.explode()
            # Here we need to split up the xform mainly so we can manipulate
            # the scale. In particular Houdini's prim xforms maintain a
            # rotation matrix but the z scale is ignored. So here we are
            # setting it directly to 1 as the "Pz" (or voxeldata) will always
            # be the exact height, no scales are applied to the prim xform.
            # We also need to scale up heightfield since in Houdini by default
            # the size is -1,-1,-1 to 1,1,1 where in pbrt its 0,0,0 to 1,1,1
            api.Translate(*srt['translate'])
            rot = srt['rotate']
            if rot.z():
                api.Rotate(rot[2],0,0,1)
            if rot.y():
                api.Rotate(rot[1],0,1,0)
            if rot.x():
                api.Rotate(rot[0],1,0,0)
            api.Scale(srt['scale'][0]*2.0, srt['scale'][1]*2.0, 1.0)
            api.Translate(-0.5, -0.5, 0)
            hf_paramset.add(PBRTParam('integer','nu',resolution[0]))
            hf_paramset.add(PBRTParam('integer','nv',resolution[1]))
            hf_paramset.add(PBRTParam('float','Pz',voxeldata))

            api.Shape('heightfield', hf_paramset)

# TODO: While over all this works, there is an issue where pbrt will crash
#       with prims 12,29-32 of a NURBS teapot. (Plantoic solids)
def nurbs_wrangler(gdp, paramset=None, properties=None):
    num_prims = gdp.globalValue('geo:primcount')[0]

    P_attrib_h = gdp.attribute('geo:point', 'P')
    Pw_attrib_h = gdp.attribute('geo:point', 'Pw')
    u_order_h = gdp.attribute('geo:prim', 'geo:primuorder')
    v_order_h = gdp.attribute('geo:prim', 'geo:primvorder')
    u_knots_h = gdp.attribute('geo:prim', 'geo:ubasisknots')
    v_knots_h = gdp.attribute('geo:prim', 'geo:vbasisknots')
    u_extent_h = gdp.attribute('geo:prim', 'geo:ubasisextent')
    v_extent_h = gdp.attribute('geo:prim', 'geo:vbasisextent')
    rowcol_h = gdp.attribute('geo:prim', 'geo:primrowcol')

    for prim_num in xrange(num_prims):
        nurbs_paramset = ParamSet(paramset)

        rowcol = gdp.value(rowcol_h, prim_num)
        u_order = gdp.value(u_order_h, prim_num)
        v_order = gdp.value(v_order_h, prim_num)
        u_knots = gdp.value(u_knots_h, prim_num)
        v_knots = gdp.value(v_knots_h, prim_num)
        u_extent = gdp.value(u_extent_h, prim_num)
        v_extent = gdp.value(v_extent_h, prim_num)
        nurbs_paramset.add(PBRTParam('integer', 'nu', rowcol[1]))
        nurbs_paramset.add(PBRTParam('integer', 'nv', rowcol[0]))
        nurbs_paramset.add(PBRTParam('integer', 'uorder', u_order))
        nurbs_paramset.add(PBRTParam('integer', 'vorder', v_order))
        nurbs_paramset.add(PBRTParam('float', 'uknots', u_knots))
        nurbs_paramset.add(PBRTParam('float', 'vknots', v_knots))
        # NOTE: Currently not sure how these are set within Houdini
        #       but they are queryable
        #       The Platonic SOP, Teapot -> Convert to NURBS can make these.
        nurbs_paramset.add(PBRTParam('float', 'u0', u_extent[0]))
        nurbs_paramset.add(PBRTParam('float', 'v0', v_extent[0]))
        nurbs_paramset.add(PBRTParam('float', 'u1', u_extent[1]))
        nurbs_paramset.add(PBRTParam('float', 'v1', v_extent[1]))

        P = prim_pt2vtx_attrib_gen(gdp, P_attrib_h, prim_num)
        if Pw_attrib_h < 0:
            nurbs_paramset.add(PBRTParam('point', 'P', P))
        else:
            # TODO: While the pbrt scene file looks right, the render
            #       is a bit odd. Scaled up geo? Not what I was expecting.
            #       Perhaps compare to RMan.
            w = prim_pt2vtx_attrib_gen(gdp, Pw_attrib_h, prim_num)
            Pw = itertools.izip(P,w)
            nurbs_paramset.add(PBRTParam('float', 'Pw', Pw))

        api.Shape('nurbs', nurbs_paramset)

def curve_wrangler(gdp, paramset=None, properties=None):
    if paramset is None:
        paramset = ParamSet()

    if properties is None:
        properties = {}

    curve_type = None
    if 'pbrt_curvetype' in properties:
        curve_type = properties['pbrt_curvetype'].Value[0]
        paramset.add(PBRTParam('string', 'type', curve_type))
    if 'splitdepth' in properties:
        paramset.add(properties['splitdepth'].to_pbrt())

    num_prims = gdp.globalValue('geo:primcount')[0]
    vtx_count_h = gdp.attribute('geo:prim', 'geo:vertexcount')

    P_attrib_h = gdp.attribute('geo:point', 'P')
    type_attrib_h = gdp.attribute('geo:prim', 'curvetype')
    order_h = gdp.attribute('geo:prim', 'geo:primorder')
    prim_name_h = gdp.attribute('geo:prim','intrinsic:typename')
    pointref_attrib_h = gdp.attribute('geo:vertex', 'geo:pointref')

    width_vtx_h = gdp.attribute('geo:vertex', 'width')
    width_pt_h = gdp.attribute('geo:point', 'width')
    width_prim_h = gdp.attribute('geo:prim', 'width')

    curvetype_h = gdp.attribute('geo:prim', 'curvetype')

    N_vtx_attrib_h = gdp.attribute('geo:vertex', 'N')
    N_pt_attrib_h = gdp.attribute('geo:point', 'N')

    for prim_num in xrange(num_prims):
        curve_paramset = ParamSet()
        prim_curve_type = curve_type

        order = gdp.value(order_h, prim_num)[0]
        degree = order - 1
        # PBRT only supports degree 2 or 3 curves
        # TODO: We could possibly convert the curves to a format that
        #       pbrt supports but for now we'll expect the user to have
        #       a curve basis which is supported
        # https://www.codeproject.com/Articles/996281/NURBS-crve-made-easy
        if degree not in ( 2,3 ):
            continue
        curve_paramset.add(PBRTParam('integer', 'degree', degree))

        if gdp.value(prim_name_h, prim_num)[0] == 'BezierCurve':
            basis = 'bezier'
        else:
            basis = 'bspline'
        curve_paramset.add(PBRTParam('string', 'basis', [basis]))

        num_vtx = gdp.value(vtx_count_h, prim_num)[0]
        P = []
        for vtx in xrange(num_vtx):
            pointref = gdp.vertex(pointref_attrib_h, prim_num, vtx)[0]
            P.append(gdp.value(P_attrib_h, pointref))
        curve_paramset.add(PBRTParam('point', 'P', P))
        if curvetype_h >= 0:
            prim_curve_type = gdp.value(curvetype_h, prim_num)[0]
        if prim_curve_type is not None:
            curve_paramset.add(PBRTParam('string', 'type', [prim_curve_type]))

        if prim_curve_type == 'ribbon':
            if N_vtx_attrib_h >= 0:
                N_01 = ( gdp.vertex(N_vtx_attrib_h, prim_num, 0),
                         gdp.vertex(N_vtx_attrib_h, prim_num, num_vtx-1) )
            elif N_pt_attrib_h >= 0:
                pointref_0 = gdp.vertex(pointref_attrib_h, prim_num, 0)
                pointref_1 = gdp.vertex(pointref_attrib_h, prim_num, num_vtx-1)
                N_01 = ( gdp.value(N_pt_attrib_h, pointref_0),
                         gdp.value(N_pt_attrib_h, pointref_1) )
            else:
                N_01 = None
            if N_01 is not None:
                curve_paramset.add(PBRTParam('normal', 'N', N_01))

        if width_vtx_h >= 0:
            curve_paramset.add(PBRTParam('float',
                                         'width0',
                                         gdp.vertex(width_vtx_h, prim_num, 0)))
            curve_paramset.add(PBRTParam('float',
                                         'width1',
                                         gdp.vertex(width_vtx_h, prim_num, num-vtx-1)))
        elif width_pt_h >= 0:
            pointref_0 = gdp.vertex(pointref_attrib_h, prim_num, 0)
            curve_paramset.add(PBRTParam('float',
                                         'width0',
                                         gdp.value(width_pt_h, pointref_0)))
            pointref_1 = gdp.vertex(pointref_attrib_h, prim_num, num_vtx-1)
            curve_paramset.add(PBRTParam('float',
                                         'width1',
                                         gdp.value(width_pt_h, pointref_1)))
        elif width_prim_h >= 0:
            curve_paramset.add(PBRTParam('float',
                                         'width',
                                         gdp.value(width_prim_h, prim_num)))
        else:
            curve_paramset.add(PBRTParam('float',
                                         'width',
                                         0.1))

        curve_paramset |= paramset
        api.Shape('curve', curve_paramset)


def tesselated_wrangler(gdp, paramset=None, properties=None):
    prim_name_h = gdp.attribute('geo:prim','intrinsic:typename')
    prim_name = gdp.value(prim_name_h, 0)[0]
    api.Comment('%s prims is are not directly supported, they will be tesselated' %
                    prim_name)
    mesh_wrangler(gdp, paramset, properties)

def not_supported(gdp, paramset=None, properties=None):
    num_prims = gdp.globalValue('geo:primcount')[0]
    prim_name_h = gdp.attribute('geo:prim','intrinsic:typename')
    prim_name = gdp.value(prim_name_h, 0)[0]
    api.Comment('Ignoring %i prims, %s is not supported' % (
                    num_prims, prim_name))

shape_wranglers = { 'Sphere': sphere_wrangler,
                    'Circle' : disk_wrangler,
                    'Tube' : tube_wrangler,
                    'Poly' : mesh_wrangler,
                    'Mesh' : mesh_wrangler,
                    'PolySoup' : mesh_wrangler,
                    'NURBMesh' : nurbs_wrangler,
                    'BezierCurve' : curve_wrangler,
                    'NURBCurve' : curve_wrangler,
                    'Volume' : volume_wrangler,
                    'TriFan' : tesselated_wrangler,
                    'TriStrip' : tesselated_wrangler,
                    'TriBezier' : tesselated_wrangler,
                    'BezierMesh' : tesselated_wrangler,
                    'PasteSurf' : tesselated_wrangler,
                    'MetaBall' : tesselated_wrangler,
                    'MetaSQuad' : tesselated_wrangler,
                    'Tetrahedron' : tesselated_wrangler,
                  }

def shape_splits(gdp):
    # intrinsic:primitivecount returns the FULL gdp's count,
    # not the current partition's primcount
    num_prims = gdp.globalValue('geo:primcount')[0]

    prim_name_h = gdp.attribute('geo:prim','intrinsic:typename')
    for prim_num in xrange(num_prims):
        prim_name = gdp.value(prim_name_h, prim_num)[0]
        yield prim_name

def save_geo(soppath, now, properties=None):
    # split by material
        # split by material override #
            # split by geo type
    # NOTE: We won't be splitting based on medium interior/exterior
    #       those will be left as a object level assignment only.
    #       Note, that in the case of Houdini Volumes they will look
    #       for the appropriate medium parameters as prim vars

    if properties is None:
        properties = {}

    # PBRT allows setting Material parameters on the Shapes in order to
    #       override a material's settings.  (Shapes get checked first)
    #       This paramset will be for holding those overrides and passing
    #       them down to the actual shape api calls.
    material_paramset = ParamSet()

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
                material_paramset = ParamSet()

                if override and material:
                    material_paramset.update(override_to_paramset(material, override))

                shape_gdp = shape_gdps[shape]

                shape_wrangler = shape_wranglers.get(shape, not_supported)
                if shape_wrangler:
                    shape_wrangler(shape_gdp, material_paramset, properties)

        if material:
            api.AttributeEnd()


