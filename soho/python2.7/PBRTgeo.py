import array
import itertools
import collections

import hou

import PBRTapi as api
from PBRTplugins import BaseNode, PBRTParam, ParamSet, pbrt_param_from_ref

from PBRTstate import scene_state

def override_to_paramset(material, override_str):
    paramset = ParamSet()
    override = eval(override_str)
    if not override or not material:
        return paramset
    node = hou.node(material)
    if not node:
        return paramset
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

def prim_transform(prim):
    rot_mat = hou.Matrix3(prim.intrinsicValue('transform'))
    vtx = prim.vertex(0)
    pt = vtx.point()
    pos = pt.position()
    xlate = hou.hmath.buildTranslate(pos)
    return (hou.Matrix4(rot_mat) * xlate).asTuple()

def sphere_wrangler(gdp, paramset=None, properties=None):
    # TODO: Invert to match Houdini UVs
    for prim in gdp.prims():
        with api.TransformBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            api.Scale(1,1,-1)
            api.Shape('sphere', paramset)

def disk_wrangler(gdp, paramset=None, properties=None):
    # NOTE: PBRT's and Houdini's parameteric UVs are different
    # so when using textures this will need to be fixed on the
    # texture/material side as its not resolvable within Soho.
    for prim in gdp.prims():
        with api.TransformBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            api.Shape('disk', paramset)

def tube_wrangler(gdp, paramset=None, properties=None):

    for prim in gdp.prims():

        shape_paramset = ParamSet(paramset)

        with api.TransformBlock():
            xform = prim_transform(prim)
            taper = prim.intrinsicValue('tubetaper')

            # workaround, see TODO below
            if not (taper == 0 or taper == 1):
                api.Comment('Skipping tube, prim # %i, with non-conforming taper of %f' %
                                (prim.number(),taper))
                continue

            closed = prim.intrinsicValue('closed')
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
    """ Per prim, per vertex fetching vertex/point values
    """
    for prim in gdp.prims():
        for vtx in prim.vertices():
        # TODO Don't test each time through the inner loop
        # TODO reverse order?
        # for vtx in xrange(num_vtx-1,-1,-1):
            if attrib == None:
                yield vtx.point().number()
            elif attrib.type() == hou.attribType.Vertex:
                yield vtx.attribValue(attrib)
            elif attrib.type() == hou.attribType.Point:
                yield vtx.point().attribValue(attrib)

def prim_pt2vtx_attrib_gen(prim, attrib='P'):
    """ per vertex fetching point values
    """
    for vtx in prim.vertices():
        pt = vtx.point()
        yield pt.attribValue(attrib)

# NOTE: If this is only used for trianglemeshes we could just do
#       xrange(len(prims)*3 +1)
def linear_vtx_gen(gdp):
    """ generate the linearvertex

    A linear vertex is a unique value for every vertex in the mesh
    where as a vertex number is the vertex offset on a prim

    We need a linear vertex for generating inidices when we have uniqe points
    http://www.sidefx.com/docs/houdini/vex/functions/vertexindex.html
    """
    i = 0
    for prim in gdp.prims():
        for vtx in prim.vertices():
            yield i
            i+=1

def pt_attrib_gen(gdp, attrib):
    """ Per prim/point fetching their values
    """
    for pt in gdp.points():
        yield pt.attribValue(attrib)

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

    mesh_gdp = scene_state.tesselate_geo(gdp)
    gdp.clear()

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

    #num_pts = mesh_gdp.globalValue('geo:pointcount')[0]
    #num_prims = mesh_gdp.globalValue('geo:primcount')[0]

    # Required
    P_attrib = mesh_gdp.findPointAttrib('P')

    # Optional
    N_attrib = mesh_gdp.findVertexAttrib('N')
    if N_attrib is None:
        N_attrib = mesh_gdp.findPointAttrib('N')

    # If there are no vertex or point normals and we need to compute
    # them use a SopVerb
    if N_attrib is None and computeN:
        normal_verb = hou.sopNodeTypeCategory().nodeVerb('normal')
        normal_verb.setParms({'type':0})
        normals_gdp = hou.Geometry()
        normal_verb.execute(normals_gdp, [mesh_gdp,])
        mesh_gdp.clear()
        del mesh_gdp
        mesh_gdp = normals_gdp
        N_attrib = mesh_gdp.findPointAttrib('N')

    uv_attrib = mesh_gdp.findVertexAttrib('uv')
    if uv_attrib is None:
        uv_attrib = mesh_gdp.findPointAttrib('uv')

    S_attrib = mesh_gdp.findVertexAttrib('S')
    if S_attrib is None:
        S_attrib = mesh_gdp.findPointAttrib('S')

    faceIndices_attrib = mesh_gdp.findPrimAttrib('faceIndices')

    # TODO: If uv's don't exist, check for 'st', we'll assume uvs are a float[3]
    #       in Houdini and st are a float[2], or we could just auto-convert as
    #       needed.

    # We need to unique the points if any of the handles
    # to vtx attributes exists.
    for attrib in (N_attrib, uv_attrib, S_attrib):
        if attrib is None:
            continue
        if attrib.type()==hou.attribType.Vertex:
            unique_points = True
            break

    S = None
    uv = None
    N = None
    faceIndices = None

    if faceIndices_attrib is not None:
        faceIndices = array.array("i")
        faceIndices.fromstring(mesh_gdp.primIntAttribValuesAsString('faceIndices'))

    # We will unique points (verts in PBRT) if any of the attributes are
    # per vertex instead of per point.
    if unique_points:
        P = vtx_attrib_gen(mesh_gdp, P_attrib)
        indices = linear_vtx_gen(mesh_gdp)

        # N is slightly special as we might compute normals automatically.
        if N_attrib is not None:
            N = vtx_attrib_gen(mesh_gdp, N_attrib)
        if uv_attrib is not None:
            uv = vtx_attrib_gen(mesh_gdp, uv_attrib)
        if S_attrib is not None:
            S = vtx_attrib_gen(mesh_gdp, S_attrib)
    else:
        P = array.array('f')
        P.fromstring(mesh_gdp.pointFloatAttribValuesAsString('P'))
        indices = vtx_attrib_gen(mesh_gdp, None)
        if N_attrib is not None:
            N = array.array('f')
            N.fromstring(mesh_gdp.pointFloatAttribValuesAsString('N'))
        if S_attrib is not None:
            S = array.array('f')
            S.fromstring(mesh_gdp.pointFloatAttribValuesAsString('S'))
        if uv_attrib is not None:
            uv = pt_attrib_gen(mesh_gdp, uv_attrib)

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

    P = array.array('f')
    P.fromstring(mesh_gdp.pointFloatAttribValuesAsString('P'))

    indices = vtx_attrib_gen(mesh_gdp, None)

    mesh_paramset.add(PBRTParam('integer', 'indices', indices))
    mesh_paramset.add(PBRTParam('point', 'P', P))

    return mesh_paramset

def volume_wrangler(gdp, paramset=None, properties=None):

    # TODO: There is a bit of an inefficiency here, we don't really
    #       need to split the gdps, we can just pass the heightfield/smoke
    #       wranglers a list of prims instead of creating new gdps.

    # Heightfield masks are not supported currently

    heightfield_prims = []
    density_prims = []
    density_name = None
    name_attrib = gdp.findPrimAttrib('name')
    if name_attrib:
        if 'density' in name_attrib.strings():
            density_name = 'density'
        else:
            density_name = ''
    for prim in gdp.prims():
        if prim.isSDF():
            continue
        if prim.isHeightField():
            heightfield_prims.append(prim)
            continue
        if ( name_attrib is not None and
             prim.attribValue('name') != density_name ):
            continue
        density_prims.append(prim)

    if heightfield_prims:
        heightfield_prim_wrangler(heightfield_prims, paramset, properties)

        # Houdini geometry objects don't allow more than one "volume" set
        # meaning, an object will only ever render one combined volume. That
        # volume could be multiple cloud prims, or multiple heightfields
        # but it can't be a mix of heightfields and clouds. So while not a
        # limitation of pbrt, we'll duplication that logic here.
        return None

    if density_prims:
        smoke_prim_wrangler(density_prims, paramset, properties)

    return None

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

def medium_prim_paramset(prim, paramset=None):

    medium_paramset = ParamSet(paramset)

    # NOTE:
    # Testing for prim attribs on each prim is a bit redudant but
    # in general its not an issue as you won't have huge numbers of
    # volumes. If this does become an issue, attribs can be stored in
    # a dict and searched from there. (This includes evaluating the
    # pbrt_interior node.

    # Initialize with the interior shader on the prim, if it exists.
    try:
        interior = prim.stringAttribValue('pbrt_interior')
        interior = BaseNode.from_node(interior)
    except hou.OperationFailed:
        interior = None

    if interior and interior.directive == 'medium':
        medium_paramset |= interior.paramset

    try:
        preset_value = prim.stringAttribValue('preset')
        if preset_value:
            medium_paramset.update(PBRTParam('string','preset',preset_value))
    except hou.OperationFailed:
        pass

    try:
        g_value = prim.floatAttribValue('g')
        medium_paramset.update(PBRTParam('float','g',g_value))
    except hou.OperationFailed:
        pass

    try:
        scale_value = prim.floatAttribValue('scale')
        medium_paramset.update(PBRTParam('float','scale',g_value))
    except hou.OperationFailed:
        pass

    try:
        sigma_a_value = prim.floatListAttribValue('sigma_a')
        if len(sigma_a) == 3:
            medium_paramset.update(PBRTParam('rgb', 'sigma_a', sigma_a_value))
    except hou.OperationFailed:
        pass

    try:
        sigma_s_value = prim.floatListAttribValue('sigma_s')
        if len(sigma_s) == 3:
            medium_paramset.update(PBRTParam('rgb', 'sigma_s', sigma_s_value))
    except hou.OperationFailed:
        pass

    return medium_paramset

def smoke_prim_wrangler(prims, paramset=None, properties=None):
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

    medium_paramset = ParamSet()
    if 'pbrt_interior' in properties:
        interior = BaseNode.from_node(properties['pbrt_interior'])
        if interior is not None and interior.directive == 'medium':
            medium_paramset |= interior.paramset

    exterior = None
    if 'pbrt_exterior' in properties:
        exterior = properties['pbrt_exterior'].Value[0]
    exterior = '' if exterior is None else exterior

    for prim in prims:
        smoke_paramset = ParamSet(paramset)

        name = '%s[%i]' % (properties.get('soppath',''), prim.number())
        resolution = prim.resolution()
        # TODO: Benchmark this vs other methods like fetching volumeSlices
        voxeldata = array.array('f')
        voxeldata.fromstring(prim.allVoxelsAsString())
        smoke_paramset.add(PBRTParam('integer','nx', resolution[0]))
        smoke_paramset.add(PBRTParam('integer','ny', resolution[1]))
        smoke_paramset.add(PBRTParam('integer','nz', resolution[2]))
        smoke_paramset.add(PBRTParam('point','p0', [-1,-1,-1]))
        smoke_paramset.add(PBRTParam('point','p1', [1,1,1]))
        smoke_paramset.add(PBRTParam('float','density', voxeldata))
        # By default we'll set a sigma_a and sigma_s
        # however the object's pbrt_interior, or prim's pbrt_interior
        # or prim attribs will override these.
        smoke_paramset.add(PBRTParam('color','sigma_a',[1, 1, 1]))
        smoke_paramset.add(PBRTParam('color','sigma_s',[1, 1, 1]))
        medium_prim_overrides = medium_prim_paramset(prim, medium_paramset)
        smoke_paramset.update(medium_prim_overrides)
        with api.AttributeBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            api.MakeNamedMedium(name, 'heterogeneous', smoke_paramset)
            api.Material('none')
            api.MediumInterface(name, exterior)
            # Pad this slightly?
            bounds_to_api_box([-1,1,-1,1,-1,1])

def heightfield_prim_wrangler(prims, paramset=None, properties=None):

    for prim in prims:
        resolution = prim.resolution()
        # If the z resolution is not 1 then this really isn't a heightfield
        if resolution[2] != 1:
            continue

        hf_paramset = ParamSet(paramset)

        voxeldata = array.array('f')
        voxeldata.fromstring(prim.allVoxelsAsString())

        with api.TransformBlock():

            xform = prim_transform(prim)
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

    # TODO: - Figure out how the Pw attribute works in Houdini
    #       - Figure out how to query [uv]_extent in hou
    # has_Pw = False if gdp.findPointAttrib('Pw') is None else True
    has_Pw = False

    #u_extent_h = gdp.attribute('geo:prim', 'geo:ubasisextent')
    #v_extent_h = gdp.attribute('geo:prim', 'geo:vbasisextent')

    for prim in gdp.prims():

        nurbs_paramset = ParamSet(paramset)

        row = prim.intrinsicValue('nv')
        col = prim.intrinsicValue('nu')
        u_order = prim.intrinsicValue('uorder')
        v_order = prim.intrinsicValue('vorder')
        u_knots = prim.intrinsicValue('uknots')
        v_knots = prim.intrinsicValue('vknots')
        #u_extent = prim.intrinsicValue('u_extent')
        #v_extent = prim.intrinsicValue('v_extent')
        nurbs_paramset.add(PBRTParam('integer', 'nu', row))
        nurbs_paramset.add(PBRTParam('integer', 'nv', col))
        nurbs_paramset.add(PBRTParam('integer', 'uorder', u_order))
        nurbs_paramset.add(PBRTParam('integer', 'vorder', v_order))
        nurbs_paramset.add(PBRTParam('float', 'uknots', u_knots))
        nurbs_paramset.add(PBRTParam('float', 'vknots', v_knots))
        # NOTE: Currently not sure how these are set within Houdini
        #       but they are queryable
        #       The Platonic SOP, Teapot -> Convert to NURBS can make these.
        #nurbs_paramset.add(PBRTParam('float', 'u0', u_extent[0]))
        #nurbs_paramset.add(PBRTParam('float', 'v0', v_extent[0]))
        #nurbs_paramset.add(PBRTParam('float', 'u1', u_extent[1]))
        #nurbs_paramset.add(PBRTParam('float', 'v1', v_extent[1]))

        P = prim_pt2vtx_attrib_gen(prim)
        if not has_Pw:
            nurbs_paramset.add(PBRTParam('point', 'P', P))
        else:
            # TODO: While the pbrt scene file looks right, the render
            #       is a bit odd. Scaled up geo? Not what I was expecting.
            #       Perhaps compare to RMan.
            w = prim_pt2vtx_attrib_gen(prim, 'Pw')
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

    has_vtx_width = False if gdp.findVertexAttrib('width') is None else True
    has_pt_width = False if gdp.findPointAttrib('width') is None else True
    has_prim_width = False if gdp.findPrimAttrib('width') is None else True

    has_curvetype = False if gdp.findPrimAttrib('curvetype') is None else True

    has_vtx_N = False if gdp.findVertexAttrib('N') is None else True
    has_pt_N = False if gdp.findPointAttrib('N') is None else True

    for prim in gdp.prims():
        curve_paramset = ParamSet()
        prim_curve_type = curve_type

        order = prim.intrinsicValue('order')
        degree = order - 1
        # PBRT only supports degree 2 or 3 curves
        # TODO: We could possibly convert the curves to a format that
        #       pbrt supports but for now we'll expect the user to have
        #       a curve basis which is supported
        # https://www.codeproject.com/Articles/996281/NURBS-crve-made-easy
        if degree not in ( 2,3 ):
            continue
        curve_paramset.add(PBRTParam('integer', 'degree', degree))

        if prim.intrinsicValue('typename') == 'BezierCurve':
            basis = 'bezier'
        else:
            basis = 'bspline'
        curve_paramset.add(PBRTParam('string', 'basis', [basis]))

        P = prim_pt2vtx_attrib_gen(prim)
        curve_paramset.add(PBRTParam('point', 'P', P))

        if has_curvetype:
            prim_curve_type = prim.attribValue('curvetype')

        if prim_curve_type is not None:
            curve_paramset.add(PBRTParam('string', 'type', [prim_curve_type]))

        if prim_curve_type == 'ribbon':
            if has_vtx_N:
                N_01 = (prim.vertex(0).attribValue('N'),
                        prim.vertex(-1).attribValue('N'))
            elif has_pt_N:
                N_01 = ( prim.vertex(0).point().attribValue('N'),
                         prim.vertex(-1).point().attribValue('N') )
            else:
                N_01 = None
            if N_01 is not None:
                curve_paramset.add(PBRTParam('normal', 'N', N_01))

        if has_vtx_width:
            curve_paramset.add(PBRTParam('float',
                                         'width0',
                                         prim.vertex(0).attribValue('width')))
            curve_paramset.add(PBRTParam('float',
                                         'width1',
                                         prim.vertex(-1).attribValue('width')))
        elif has_pt_width:
            curve_paramset.add(PBRTParam('float',
                                         'width0',
                                         prim.vertex(0).point().attribValue('width')))
            curve_paramset.add(PBRTParam('float',
                                         'width1',
                                         prim.vertex(-1).point().attribValue('width')))
        elif has_prim_width:
            curve_paramset.add(PBRTParam('float',
                                         'width',
                                         prim.attribValue('width')))
        else:
            curve_paramset.add(PBRTParam('float',
                                         'width',
                                         0.1))

        curve_paramset |= paramset
        api.Shape('curve', curve_paramset)


def tesselated_wrangler(gdp, paramset=None, properties=None):
    prim_name = gdp.iterPrims()[0].intrinsicValue('typename')
    api.Comment('%s prims is are not directly supported, they will be tesselated' %
                    prim_name)
    mesh_wrangler(gdp, paramset, properties)

def not_supported(gdp, paramset=None, properties=None):
    num_prims = len(gdp.prims())
    prim_name = gdp.iterPrims()[0].intrinsicValue('typename')
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

def partition_by_attrib(input_gdp, attrib, intrinsic=False):
    # Not sure about a set operation on prims
    prim_values = collections.defaultdict(set)
    prims = input_gdp.prims()
    if intrinsic:
        for prim in prims:
            prim_values[prim.intrinsicValue(attrib)].add(prim.number())
    else:
        for prim in prims:
            prim_values[prim.attribValue(attrib)].add(prim.number())

    split_gdps = {}
    all_prims = set(range(len(prims)))
    for prim_value in prim_values:
        gdp = hou.Geometry()
        gdp.merge(input_gdp)
        keep_prims = prim_values[prim_value]
        remove_prims = all_prims - keep_prims
        cull_list = [ gdp.iterPrims()[p] for p in remove_prims ]
        gdp.deletePrims(cull_list)
        split_gdps[prim_value] = gdp
    return split_gdps

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

    # We need the soppath to come along and since we are creating new
    # hou.Geometry() we'll lose the original sop connection so we need
    # to stash it here.

    properties.update( {'soppath' : soppath} )

    node = hou.node(soppath)
    if node is None:
        return

    input_gdp = node.geometry().freeze()
    gdp = hou.Geometry()
    gdp.merge(input_gdp)

    # Partition based on materials
    try:
        global_material = gdp.stringAttribValue('shop_materialpath')
    except hou.OperationFailed:
        global_material = None

    attrib_h = gdp.findPrimAttrib('shop_materialpath')
    if attrib_h is not None:
        material_gdps = partition_by_attrib(gdp, attrib_h)
    else:
        material_gdps = {global_material : gdp}

    try:
        global_override = gdp.stringAttribValue('material_override')
    except hou.OperationFailed:
        global_override = None

    # Further partition based on material overrides
    has_prim_overrides = False if gdp.findPrimAttrib('material_override') is None else True
    for material in material_gdps:

        if material:
            api.AttributeBegin()
            api.NamedMaterial(material)

        material_gdp = material_gdps[material]
        #api.Comment('%s %i' % (material_gdp,len(material_gdp.prims())))

        if has_prim_overrides:
            attrib_h = material_gdp.findPrimAttrib('material_override')
            override_gdps = partition_by_attrib(material_gdp, attrib_h)
            # Clean up post partition
            material_gdp.clear()
        else:
            override_gdps = {global_override: material_gdp}

        for override in override_gdps:
            override_gdp = override_gdps[override]
            #api.Comment(' %s %i' % (override_gdp, len(override_gdp.prims())))

            shape_gdps = partition_by_attrib(override_gdp, 'typename', intrinsic=True)
            override_gdp.clear()

            for shape in shape_gdps:
                material_paramset = ParamSet()

                if override and material:
                    material_paramset.update(override_to_paramset(material, override))

                shape_gdp = shape_gdps[shape]
                #api.Comment('  %s %i' % (shape_gdp, len(shape_gdp.prims())))

                shape_wrangler = shape_wranglers.get(shape, not_supported)
                if shape_wrangler:
                    shape_wrangler(shape_gdp, material_paramset, properties)
                shape_gdp.clear()

        if material:
            api.AttributeEnd()

