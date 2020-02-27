from __future__ import print_function, division, absolute_import

import os
import array
import itertools
import collections

import hou

import PBRTapi as api
from PBRTnodes import BaseNode, MaterialNode, PBRTParam, ParamSet
from PBRTstate import scene_state


def mesh_alpha_texs(properties):
    if not properties:
        return
    paramset = ParamSet()
    for prop in ("alpha", "shadowalpha"):
        if prop not in properties:
            continue
        tex = properties[prop].Value[0]
        if not tex:
            continue
        paramset.add(PBRTParam("texture", prop, tex))
    return paramset


# The following generators could be simplified if we
# assume that each gdp will always have 3 verts thus
# removing the need to constantly fetch the
# geo:vertexcount. (Could be passed as a parm, and if the
# default is None, then compute)


def vtx_attrib_gen(gdp, attrib):
    """Per prim, per vertex fetching vertex/point values

    Args:
        gdp (hou.Geometry): Input geometry
        attrib (hou.Attrib): Attribute to evaluate

    Yields:
        Values of attrib for each vertex
    """
    for prim in gdp.prims():
        for vtx in prim.vertices():
            # TODO Don't test each time through the inner loop
            # TODO reverse order?
            # for vtx in xrange(num_vtx-1,-1,-1):
            if attrib is None:
                yield vtx.point().number()
            elif attrib.type() == hou.attribType.Vertex:
                yield vtx.attribValue(attrib)
            elif attrib.type() == hou.attribType.Point:
                yield vtx.point().attribValue(attrib)


def prim_pt2vtx_attrib_gen(prim, attrib="P"):
    """Output point attrib values for a prim

    Args:
        prim (hou.Prim): Input primitive
        attrib (hou.Attrib, str): Attribute to evaluate (defaults to 'P')

    Yields:
        Values of attrib for each point on the prim
    """
    for vtx in prim.vertices():
        pt = vtx.point()
        yield pt.attribValue(attrib)


def linear_vtx_gen(gdp):
    """Generate the linearvertex for input geometry

    A linear vertex is a unique value for every vertex in the mesh
    where as a vertex number is the vertex offset on a prim

    We need a linear vertex for generating inidices when we have uniqe points
    http://www.sidefx.com/docs/houdini/vex/functions/vertexindex.html

    Args:
        gdp (hou.Geometry): Input geometry

    Yields:
        Linear vertex number for every vertex
    """
    # NOTE: If this is only used for trianglemeshes we could just do
    #       xrange(len(prims)*3 +1)
    i = 0
    for prim in gdp.prims():
        for vtx in prim.vertices():
            yield i
            i += 1


def pt_attrib_gen(gdp, attrib):
    """Fetch point values for input geometry

    Args:
        gdp (hou.Geometry): Input geometry
        attrib (hou.Attrib): Attribute to evaluate

    Yields:
        Values of attrib for each point in geo
    """
    for pt in gdp.points():
        yield pt.attribValue(attrib)


def prim_transform(prim):
    """Return a tuple representing the Matrix4 of the transform intrinsic"""
    rot_mat = hou.Matrix3(prim.intrinsicValue("transform"))
    vtx = prim.vertex(0)
    pt = vtx.point()
    pos = pt.position()
    xlate = hou.hmath.buildTranslate(pos)
    return (hou.Matrix4(rot_mat) * xlate).asTuple()


def sphere_wrangler(gdp, paramset=None, properties=None):
    """Outputs a "sphere" Shapes for the input geometry

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """
    for prim in gdp.prims():
        with api.TransformBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            # Scale required to match Houdini's uvs
            api.Scale(1, 1, -1)
            api.Shape("sphere", paramset)
    return


def disk_wrangler(gdp, paramset=None, properties=None):
    """Outputs "disk" Shapes for the input geometry

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """
    # NOTE: PBRT's and Houdini's parameteric UVs are different
    # so when using textures this will need to be fixed on the
    # texture/material side as its not resolvable within Soho.
    for prim in gdp.prims():
        with api.TransformBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            api.Shape("disk", paramset)
    return


def packeddisk_wrangler(gdp, paramset=None, properties=None):
    """Outputs "ply" Shapes for the input geometry

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """
    alpha_paramset = mesh_alpha_texs(properties)
    for prim in gdp.prims():
        shape_paramset = ParamSet(paramset)
        filename = prim.intrinsicValue("filename")
        if not filename:
            continue
        if os.path.splitext(filename)[1].lower() != ".ply":
            continue
        shape_paramset.replace(PBRTParam("string", "filename", filename))
        shape_paramset.update(alpha_paramset)
        with api.TransformBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            api.Shape("plymesh", shape_paramset)
    return


def tube_wrangler(gdp, paramset=None, properties=None):
    """Outputs "cone" or "cylinder" Shapes for the input geometry

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """

    for prim in gdp.prims():

        shape_paramset = ParamSet(paramset)

        with api.TransformBlock():
            xform = prim_transform(prim)
            taper = prim.intrinsicValue("tubetaper")

            # workaround, see TODO below in the else: pass
            if not (taper == 0 or taper == 1):
                api.Comment(
                    "Skipping tube, prim # %i, with non-conforming taper of %f"
                    % (prim.number(), taper)
                )
                continue

            closed = prim.intrinsicValue("closed")
            api.ConcatTransform(xform)
            api.Rotate(-90, 1, 0, 0)
            if taper == 0:
                shape = "cone"
                api.Translate(0, 0, -0.5)
            elif taper == 1:
                shape = "cylinder"
                shape_paramset.add(PBRTParam("float", "zmin", -0.5))
                shape_paramset.add(PBRTParam("float", "zmax", 0.5))
            else:
                # TODO support hyperboloid, however pbrt currently
                # has no ends of trouble with this shape type
                # crashes or hangs
                pass
            with api.TransformBlock():
                # Flip in Y so parameteric UV's match Houdini's
                api.Scale(1, -1, 1)
                api.Shape(shape, shape_paramset)

            if closed:
                disk_paramset = ParamSet(paramset)
                if shape == "cylinder":
                    disk_paramset.add(PBRTParam("float", "height", 0.5))
                    api.Shape("disk", disk_paramset)
                    disk_paramset.add(PBRTParam("float", "height", -0.5))
                    api.Shape("disk", disk_paramset)
                else:
                    disk_paramset.add(PBRTParam("float", "height", 0))
                    api.Shape("disk", disk_paramset)
    return


def mesh_wrangler(gdp, paramset=None, properties=None):
    """Outputs meshes (trianglemesh or loopsubdiv) depending on properties

    If the pbrt_rendersubd property is set and true, a loopsubdiv shape will
    be generated, otherwise a trianglemesh

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """

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
    shape = "trianglemesh"
    if "pbrt_rendersubd" in properties:
        if properties["pbrt_rendersubd"].Value[0]:
            shape = "loopsubdiv"

    if shape == "loopsubdiv":
        wrangler_paramset = loopsubdiv_params(mesh_gdp)
        if "levels" in properties:
            wrangler_paramset.replace(properties["levels"].to_pbrt())
    else:
        computeN = True
        if "pbrt_computeN" in properties:
            computeN = properties["pbrt_computeN"].Value[0]
        wrangler_paramset = trianglemesh_params(mesh_gdp, computeN)
        alpha_paramset = mesh_alpha_texs(properties)
        wrangler_paramset.update(alpha_paramset)

    mesh_paramset.update(wrangler_paramset)

    api.Shape(shape, mesh_paramset)

    return None


def trianglemesh_params(mesh_gdp, computeN=True):
    """Generates a ParamSet for a trianglemesh

    The following attributes are checked for -
    P (point), built-in attribute
    N (vertex/point), float[3]
    uv (vertex/point), float[3]
    S (vertex/point), float[3]
    faceIndices (prim), integer, used for ptex

    Args:
        mesh_gdp (hou.Geometry): Input geo
        computeN (bool): Whether to auto-compute normals if they don't exist
                         Defaults to True
    Returns: ParamSet of the attributes on the geometry
    """

    mesh_paramset = ParamSet()
    unique_points = False

    # Required
    P_attrib = mesh_gdp.findPointAttrib("P")

    # Optional
    N_attrib = mesh_gdp.findVertexAttrib("N")
    if N_attrib is None:
        N_attrib = mesh_gdp.findPointAttrib("N")

    # If there are no vertex or point normals and we need to compute
    # them with a SopVerb
    if N_attrib is None and computeN:
        normal_verb = hou.sopNodeTypeCategory().nodeVerb("normal")
        normal_verb.setParms({"type": 0})
        normals_gdp = hou.Geometry()
        normal_verb.execute(normals_gdp, [mesh_gdp])
        mesh_gdp.clear()
        del mesh_gdp
        mesh_gdp = normals_gdp
        N_attrib = mesh_gdp.findPointAttrib("N")

    uv_attrib = mesh_gdp.findVertexAttrib("uv")
    if uv_attrib is None:
        uv_attrib = mesh_gdp.findPointAttrib("uv")

    S_attrib = mesh_gdp.findVertexAttrib("S")
    if S_attrib is None:
        S_attrib = mesh_gdp.findPointAttrib("S")

    faceIndices_attrib = mesh_gdp.findPrimAttrib("faceIndices")

    # TODO: If uv's don't exist, check for 'st', we'll assume uvs are a float[3]
    #       in Houdini and st are a float[2], or we could just auto-convert as
    #       needed.

    # We need to unique the points if any of the handles
    # to vtx attributes exists.
    for attrib in (N_attrib, uv_attrib, S_attrib):
        if attrib is None:
            continue
        if attrib.type() == hou.attribType.Vertex:
            unique_points = True
            break

    S = None
    uv = None
    N = None
    faceIndices = None

    if faceIndices_attrib is not None:
        faceIndices = array.array("i")
        faceIndices.fromstring(mesh_gdp.primIntAttribValuesAsString("faceIndices"))

    # We will unique points (verts in PBRT) if any of the attributes are
    # per vertex instead of per point.
    if unique_points:
        P = vtx_attrib_gen(mesh_gdp, P_attrib)
        indices = linear_vtx_gen(mesh_gdp)

        if N_attrib is not None:
            N = vtx_attrib_gen(mesh_gdp, N_attrib)
        if uv_attrib is not None:
            uv = vtx_attrib_gen(mesh_gdp, uv_attrib)
        if S_attrib is not None:
            S = vtx_attrib_gen(mesh_gdp, S_attrib)
    else:
        # NOTE: We are using arrays here for very fast access since we can
        #       fetch all the values at once compactly, while faster, this
        #       will take more RAM than a generator approach. If this becomes
        #       and issue we can change it.
        P = array.array("f")
        P.fromstring(mesh_gdp.pointFloatAttribValuesAsString("P"))
        indices = vtx_attrib_gen(mesh_gdp, None)
        if N_attrib is not None:
            N = array.array("f")
            N.fromstring(mesh_gdp.pointFloatAttribValuesAsString("N"))
        if S_attrib is not None:
            S = array.array("f")
            S.fromstring(mesh_gdp.pointFloatAttribValuesAsString("S"))
        if uv_attrib is not None:
            uv = pt_attrib_gen(mesh_gdp, uv_attrib)

    mesh_paramset.add(PBRTParam("integer", "indices", indices))
    mesh_paramset.add(PBRTParam("point", "P", P))
    if N is not None:
        mesh_paramset.add(PBRTParam("normal", "N", N))
    if S is not None:
        mesh_paramset.add(PBRTParam("vector", "S", S))
    if faceIndices is not None:
        mesh_paramset.add(PBRTParam("integer", "faceIndices", faceIndices))
    if uv is not None:
        # Houdini's uvs are stored as 3 floats, but pbrt only needs two
        # We'll use a generator comprehension to strip off the extra
        # float.
        uv2 = (x[0:2] for x in uv)
        mesh_paramset.add(PBRTParam("float", "uv", uv2))

    return mesh_paramset


def loopsubdiv_params(mesh_gdp):
    """Generates a ParamSet for a loopsubdiv

    The following attributes are checked for -
    P (point), built-in attribute

    Args:
        mesh_gdp (hou.Geometry): Input geo
    Returns: ParamSet of the attributes on the geometry
    """

    mesh_paramset = ParamSet()

    P = array.array("f")
    P.fromstring(mesh_gdp.pointFloatAttribValuesAsString("P"))

    indices = vtx_attrib_gen(mesh_gdp, None)

    mesh_paramset.add(PBRTParam("integer", "indices", indices))
    mesh_paramset.add(PBRTParam("point", "P", P))

    return mesh_paramset


def volume_wrangler(gdp, paramset=None, properties=None):
    """Call either the smoke_prim_wrangler or heightfield_wrangler"""

    # TODO: There is a bit of an inefficiency here, we don't really
    #       need to split the gdps, we can just pass the heightfield/smoke
    #       wranglers a list of prims instead of creating new gdps.

    # Heightfield masks are not supported currently

    heightfield_prims = []
    density_prims = []
    density_name = None
    name_attrib = gdp.findPrimAttrib("name")
    if name_attrib:
        if "density" in name_attrib.strings():
            density_name = "density"
        else:
            density_name = ""
    for prim in gdp.prims():
        if prim.isSDF():
            continue
        if prim.isHeightField():
            heightfield_prims.append(prim)
            continue
        if name_attrib is not None and prim.attribValue("name") != density_name:
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
    """Output a trianglemesh Shape of box based on the input bounds"""

    paramset = ParamSet()
    paramset.add(
        PBRTParam(
            "point",
            "P",
            [
                b[1],
                b[2],
                b[5],
                b[0],
                b[2],
                b[5],
                b[1],
                b[3],
                b[5],
                b[0],
                b[3],
                b[5],
                b[0],
                b[2],
                b[4],
                b[1],
                b[2],
                b[4],
                b[0],
                b[3],
                b[4],
                b[1],
                b[3],
                b[4],
            ],
        )
    )
    paramset.add(
        PBRTParam(
            "integer",
            "indices",
            [
                0,
                3,
                1,
                0,
                2,
                3,
                4,
                7,
                5,
                4,
                6,
                7,
                6,
                2,
                7,
                6,
                3,
                2,
                5,
                1,
                4,
                5,
                0,
                1,
                5,
                2,
                0,
                5,
                7,
                2,
                1,
                6,
                4,
                1,
                3,
                6,
            ],
        )
    )
    api.Shape("trianglemesh", paramset)


# NOTE: In pbrt the medium interface and shading parameters
#       are strongly coupled unlike in Houdini/Mantra where
#       the volume shaders define the volume properties and
#       and the volume primitives only define grids.
#


def medium_prim_paramset(prim, paramset=None):
    """Build a ParamSet of medium values based off of hou.Prim attribs"""
    medium_paramset = ParamSet(paramset)

    # NOTE:
    # Testing for prim attribs on each prim is a bit redundat but
    # in general its not an issue as you won't have huge numbers of
    # volumes. If this does become an issue, attribs can be stored in
    # a dict and searched from there. (This includes evaluating the
    # pbrt_interior node.

    # Initialize with the interior shader on the prim, if it exists.
    try:
        interior = prim.stringAttribValue("pbrt_interior")
        interior = BaseNode.from_node(interior)
    except hou.OperationFailed:
        interior = None

    if interior and interior.directive_type == "pbrt_medium":
        medium_paramset |= interior.paramset

    try:
        preset_value = prim.stringAttribValue("preset")
        if preset_value:
            medium_paramset.replace(PBRTParam("string", "preset", preset_value))
    except hou.OperationFailed:
        pass

    try:
        g_value = prim.floatAttribValue("g")
        medium_paramset.replace(PBRTParam("float", "g", g_value))
    except hou.OperationFailed:
        pass

    try:
        scale_value = prim.floatAttribValue("scale")
        medium_paramset.replace(PBRTParam("float", "scale", scale_value))
    except hou.OperationFailed:
        pass

    try:
        sigma_a_value = prim.floatListAttribValue("sigma_a")
        if len(sigma_a_value) == 3:
            medium_paramset.replace(PBRTParam("rgb", "sigma_a", sigma_a_value))
    except hou.OperationFailed:
        pass

    try:
        sigma_s_value = prim.floatListAttribValue("sigma_s")
        if len(sigma_s_value) == 3:
            medium_paramset.replace(PBRTParam("rgb", "sigma_s", sigma_s_value))
    except hou.OperationFailed:
        pass

    return medium_paramset


def smoke_prim_wrangler(prims, paramset=None, properties=None):
    """Outputs a "heterogeneous" Medium and bounding Shape for the input geometry

    The following attributes are checked for via medium_prim_paramset() -
    (See pbrt_medium node for what each parm does)
    pbrt_interior (prim), string
    preset (prim), string
    g (prim), float
    scale (prim), float[3]
    sigma_a (prim), float[3]
    sigma_s (prim), float[3]

    Args:
        prims (list of hou.Prims): Input prims
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """
    # NOTE: Overlapping heterogeneous volumes don't currently
    #       appear to be supported, although this may be an issue
    #       with the Medium interface order? Visually it appears one
    #       object is blocking the other.

    # NOTE: Not all samplers support heterogeneous volumes. Determine which
    #       ones do, (and verify this is accurate).
    if properties is None:
        properties = {}

    if "pbrt_ignorevolumes" in properties and properties["pbrt_ignorevolumes"].Value[0]:
        api.Comment("Ignoring volumes because pbrt_ignorevolumes is enabled")
        return

    medium_paramset = ParamSet()
    if "pbrt_interior" in properties:
        interior = BaseNode.from_node(properties["pbrt_interior"].Value[0])
        if interior is not None and interior.directive_type == "pbrt_medium":
            medium_paramset |= interior.paramset
        # These are special overrides that come from full point instancing.
        # It allows "per point" medium values to be "stamped" out to volume prims.
        interior_paramset = properties.get(".interior_overrides")
        if interior_paramset is not None:
            medium_paramset.update(interior_paramset)

    medium_suffix = ""
    instance_info = properties.get(".instance_info")
    if instance_info is not None:
        medium_suffix = ":%s[%i]" % (instance_info.source, instance_info.number)

    exterior = None
    if "pbrt_exterior" in properties:
        exterior = properties["pbrt_exterior"].Value[0]
    exterior = "" if exterior is None else exterior

    for prim in prims:
        smoke_paramset = ParamSet()

        medium_name = "%s[%i]%s" % (
            properties["object:soppath"].Value[0],
            prim.number(),
            medium_suffix,
        )
        resolution = prim.resolution()
        # TODO: Benchmark this vs other methods like fetching volumeSlices
        voxeldata = array.array("f")
        voxeldata.fromstring(prim.allVoxelsAsString())
        smoke_paramset.add(PBRTParam("integer", "nx", resolution[0]))
        smoke_paramset.add(PBRTParam("integer", "ny", resolution[1]))
        smoke_paramset.add(PBRTParam("integer", "nz", resolution[2]))
        smoke_paramset.add(PBRTParam("point", "p0", [-1, -1, -1]))
        smoke_paramset.add(PBRTParam("point", "p1", [1, 1, 1]))
        smoke_paramset.add(PBRTParam("float", "density", voxeldata))

        medium_prim_overrides = medium_prim_paramset(prim, medium_paramset)
        smoke_paramset.update(medium_prim_overrides)
        smoke_paramset |= paramset

        # By default we'll set a sigma_a and sigma_s to be more Houdini-like
        # however the object's pbrt_interior, or prim's pbrt_interior
        # or prim attribs will override these.
        if (
            PBRTParam("color", "sigma_a") not in smoke_paramset
            and PBRTParam("color", "sigma_s") not in smoke_paramset
        ) and PBRTParam("string", "preset") not in smoke_paramset:
            smoke_paramset.add(PBRTParam("color", "sigma_a", [1, 1, 1]))
            smoke_paramset.add(PBRTParam("color", "sigma_s", [1, 1, 1]))

        with api.AttributeBlock():
            xform = prim_transform(prim)
            api.ConcatTransform(xform)
            api.MakeNamedMedium(medium_name, "heterogeneous", smoke_paramset)
            api.Material("none")
            api.MediumInterface(medium_name, exterior)
            # Pad this slightly?
            bounds_to_api_box([-1, 1, -1, 1, -1, 1])
    return


def heightfield_prim_wrangler(prims, paramset=None, properties=None):
    """Outputs a "heightfield" Shapes for the input geometry

    Args:
        prims (list of hou.Prims): Input prims
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """

    for prim in prims:
        resolution = prim.resolution()
        # If the z resolution is not 1 then this really isn't a heightfield
        if resolution[2] != 1:
            continue

        hf_paramset = ParamSet()

        # Similar to trianglemesh, this is more compact fast, however it might
        # be a memory issue and a generator per voxel or per slice might be a
        # better approach.
        voxeldata = array.array("f")
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
            api.Translate(*srt["translate"])
            rot = srt["rotate"]
            if rot.z():
                api.Rotate(rot[2], 0, 0, 1)
            if rot.y():
                api.Rotate(rot[1], 0, 1, 0)
            if rot.x():
                api.Rotate(rot[0], 1, 0, 0)
            api.Scale(srt["scale"][0] * 2.0, srt["scale"][1] * 2.0, 1.0)
            api.Translate(-0.5, -0.5, 0)
            hf_paramset.add(PBRTParam("integer", "nu", resolution[0]))
            hf_paramset.add(PBRTParam("integer", "nv", resolution[1]))
            hf_paramset.add(PBRTParam("float", "Pz", voxeldata))
            hf_paramset |= paramset

            api.Shape("heightfield", hf_paramset)
    return


# TODO: While over all this works, there is an issue where pbrt will crash
#       with prims 12,29-32 of a NURBS teapot. (Plantoic solids)
def nurbs_wrangler(gdp, paramset=None, properties=None):
    """Outputs a "nurbs" Shape for input geometry

    The following attributes are checked for -
    P (point), built-in attribute

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """

    # TODO: - Figure out how the Pw attribute works in Houdini
    # has_Pw = False if gdp.findPointAttrib('Pw') is None else True
    has_Pw = False

    # TODO   - Figure out how to query [uv]_extent in hou
    # u_extent_h = gdp.attribute('geo:prim', 'geo:ubasisextent')
    # v_extent_h = gdp.attribute('geo:prim', 'geo:vbasisextent')

    for prim in gdp.prims():

        nurbs_paramset = ParamSet()

        row = prim.intrinsicValue("nu")
        col = prim.intrinsicValue("nv")
        u_order = prim.intrinsicValue("uorder")
        v_order = prim.intrinsicValue("vorder")
        u_wrap = prim.intrinsicValue("uwrap")
        v_wrap = prim.intrinsicValue("vwrap")
        u_knots = prim.intrinsicValue("uknots")
        v_knots = prim.intrinsicValue("vknots")

        if u_wrap:
            row += u_order - 1
        if v_wrap:
            col += v_order - 1
        nurbs_paramset.add(PBRTParam("integer", "nu", row))
        nurbs_paramset.add(PBRTParam("integer", "nv", col))
        nurbs_paramset.add(PBRTParam("integer", "uorder", u_order))
        nurbs_paramset.add(PBRTParam("integer", "vorder", v_order))
        nurbs_paramset.add(PBRTParam("float", "uknots", u_knots))
        nurbs_paramset.add(PBRTParam("float", "vknots", v_knots))
        # NOTE: Currently not sure how these are set within Houdini
        #       but they are queryable
        #       The Platonic SOP, Teapot -> Convert to NURBS can make these.
        # nurbs_paramset.add(PBRTParam('float', 'u0', u_extent[0]))
        # nurbs_paramset.add(PBRTParam('float', 'v0', v_extent[0]))
        # nurbs_paramset.add(PBRTParam('float', 'u1', u_extent[1]))
        # nurbs_paramset.add(PBRTParam('float', 'v1', v_extent[1]))

        # if row + u_order != len(u_knots):
        #    api.Comment('Invalid U')
        # if col + v_order != len(v_knots):
        #    api.Comment('Invalid V')

        P = []
        for v in xrange(col):
            for u in xrange(row):
                vtx = prim.vertex(u % prim.numCols(), v % prim.numRows())
                pt = vtx.point()
                P.append(pt.attribValue("P"))
        if not has_Pw:
            nurbs_paramset.add(PBRTParam("point", "P", P))
        else:
            # TODO: While the pbrt scene file looks right, the render
            #       is a bit odd. Scaled up geo? Not what I was expecting.
            #       Perhaps compare to RMan.
            w = prim_pt2vtx_attrib_gen(prim, "Pw")
            Pw = itertools.izip(P, w)
            nurbs_paramset.add(PBRTParam("float", "Pw", Pw))

        nurbs_paramset |= paramset
        api.Shape("nurbs", nurbs_paramset)


def _convert_nurbs_to_bezier(gdp):
    """Convert any NURBS Curves to Beziers

    Due to how knots are interrupted between Houdini and PBRT we won't be able to
    map NURBS to B-Splines. To work around this we just convert to Bezier degree 4
    curves, which is what PBRT is doing internally as well. "yolo"

    Args:
        gdp (hou.Geometry): Input geo
    Returns: hou.Geometry: Replaces input gdp
    """
    convert_verb = hou.sopNodeTypeCategory().nodeVerb("convert")
    # fromtype: "nurbCurve", totype: "bezCurve"
    convert_verb.setParms({"fromtype": 9, "totype": 2})
    convert_verb.execute(gdp, [gdp])
    return gdp


def curve_wrangler(gdp, paramset=None, properties=None):
    """Outputs a "curve" Shape for input geometry

    The following attributes are checked for -

    P (point), built-in attribute
    width (vertex/point/prim), float
    N (vertex/point), float[3]
    curvetype (prim), string (overrides the property pbrt_curvetype)

    Args:
        gdp (hou.Geometry): Input geo
        paramset (ParamSet): Any base params to add to the shape. (Optional)
        properties (dict): Dictionary of SohoParms (Optional)
    Returns: None
    """
    if paramset is None:
        paramset = ParamSet()

    if properties is None:
        properties = {}

    curve_type = None
    if "pbrt_curvetype" in properties:
        curve_type = properties["pbrt_curvetype"].Value[0]
        paramset.add(PBRTParam("string", "type", curve_type))
    if "splitdepth" in properties:
        paramset.add(properties["splitdepth"].to_pbrt())

    gdp = _convert_nurbs_to_bezier(gdp)

    has_vtx_width = False if gdp.findVertexAttrib("width") is None else True
    has_pt_width = False if gdp.findPointAttrib("width") is None else True
    has_prim_width = False if gdp.findPrimAttrib("width") is None else True

    has_curvetype = False if gdp.findPrimAttrib("curvetype") is None else True

    has_vtx_N = False if gdp.findVertexAttrib("N") is None else True
    has_pt_N = False if gdp.findPointAttrib("N") is None else True

    material_node = None
    overrides_h = None

    if '.prim_overrides' in properties:
        overrides_h = gdp.findPrimAttrib("material_override")
        material_node = properties[".material_node"]
    api.Comment('OVERRIDES')

    for prim in gdp.prims():

        if overrides_h is not None:
            override = prim.attribValue(overrides_h)
            if override:
                paramset.update(material_node.override_paramset(override))

        curve_paramset = ParamSet()
        prim_curve_type = curve_type

        # Closed curve surfaces are not supported
        if prim.intrinsicValue("closed"):
            continue

        order = prim.intrinsicValue("order")
        degree = order - 1
        # PBRT only supports degree 2 or 3 curves
        # TODO: We could possibly convert the curves to a format that
        #       pbrt supports but for now we'll expect the user to have
        #       a curve basis which is supported
        # https://www.codeproject.com/Articles/996281/NURBS-crve-made-easy
        if degree not in (2, 3):
            continue
        curve_paramset.add(PBRTParam("integer", "degree", degree))

        if prim.intrinsicValue("typename") == "BezierCurve":
            basis = "bezier"
        else:
            # We should not see these as they are being converted to BezierCurves
            basis = "bspline"
        curve_paramset.add(PBRTParam("string", "basis", [basis]))

        P = prim_pt2vtx_attrib_gen(prim)
        curve_paramset.add(PBRTParam("point", "P", P))

        if has_curvetype:
            prim_val = prim.attribValue("curvetype")
            prim_curve_type = prim_val if prim_val else curve_type

        if prim_curve_type is not None:
            curve_paramset.add(PBRTParam("string", "type", [prim_curve_type]))

        if prim_curve_type == "ribbon":

            if has_vtx_N or has_pt_N:
                N = (prim.attribValueAt("N", u) for u in prim.intrinsicValue("knots"))
            else:
                # If ribbon, normals must exist
                # TODO: Let pbrt error? Or put default values?
                N = [(0, 0, 1)] * len(prim.intrinsicValue("knots"))

            if N is not None:
                curve_paramset.add(PBRTParam("normal", "N", N))

        if has_vtx_width:
            curve_paramset.add(
                PBRTParam("float", "width0", prim.vertex(0).attribValue("width"))
            )
            curve_paramset.add(
                PBRTParam("float", "width1", prim.vertex(-1).attribValue("width"))
            )
        elif has_pt_width:
            curve_paramset.add(
                PBRTParam(
                    "float", "width0", prim.vertex(0).point().attribValue("width")
                )
            )
            curve_paramset.add(
                PBRTParam(
                    "float", "width1", prim.vertex(-1).point().attribValue("width")
                )
            )
        elif has_prim_width:
            curve_paramset.add(PBRTParam("float", "width", prim.attribValue("width")))
        else:
            # Houdini's default matches a width of 0.05
            curve_paramset.add(PBRTParam("float", "width", 0.05))

        curve_paramset |= paramset
        api.Shape("curve", curve_paramset)
    return


def tesselated_wrangler(gdp, paramset=None, properties=None):
    """Wrangler for any geo that needs to be tesselated"""
    prim_name = gdp.iterPrims()[0].intrinsicValue("typename")
    api.Comment(
        "%s prims is are not directly supported, they will be tesselated" % prim_name
    )
    mesh_wrangler(gdp, paramset, properties)
    return


def not_supported(gdp, paramset=None, properties=None):
    """Wrangler for unsupported prim types"""
    num_prims = len(gdp.prims())
    prim_name = gdp.iterPrims()[0].intrinsicValue("typename")
    api.Comment("Ignoring %i prims, %s is not supported" % (num_prims, prim_name))
    return


shape_wranglers = {
    "Sphere": sphere_wrangler,
    "Circle": disk_wrangler,
    "Tube": tube_wrangler,
    "Poly": mesh_wrangler,
    "Mesh": mesh_wrangler,
    "PolySoup": mesh_wrangler,
    "NURBMesh": nurbs_wrangler,
    "BezierCurve": curve_wrangler,
    "NURBCurve": curve_wrangler,
    "Volume": volume_wrangler,
    "PackedDisk": packeddisk_wrangler,
    "TriFan": tesselated_wrangler,
    "TriStrip": tesselated_wrangler,
    "TriBezier": tesselated_wrangler,
    "BezierMesh": tesselated_wrangler,
    "PasteSurf": tesselated_wrangler,
    "MetaBall": tesselated_wrangler,
    "MetaSQuad": tesselated_wrangler,
    "Tetrahedron": tesselated_wrangler,
}

# These are the types that the primtives form an aggregate.
# For example you can have a single polygon or combine multiple into
# a poly mesh. We'll want to combine the same overrides into a single
# mesh to save on creating a mesh per poly face.
requires_override_partition = set([ "Poly", ])


def partition_by_attrib(input_gdp, attrib, intrinsic=False):
    """Partition the input geo based on a attribute

    Args:
        input_gdp (hou.Geometry): Incoming geometry, not modified
        attrib (str, hou.Attrib): Attribute to partition by
        intrinsic (bool): Whether to an attribute or intrinsic attrib
                          (Optional, defaults to False)
    Returns:
        Dictionary of hou.Geometry with keys of the attrib value.
    """
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
        cull_list = [gdp.iterPrims()[p] for p in remove_prims]
        gdp.deletePrims(cull_list)
        split_gdps[prim_value] = gdp
    return split_gdps


def output_geo(soppath, now, properties=None):
    """Output the geometry by calling the appropriate wrangler

    Geometry is partitioned into subparts based on the shop_materialpath
    and material_override prim attributes.

    Args:
        soppath (str): oppath to SOP
        properties (dict, None): Dictionary of SohoParms
                                 (Optional, defaults to None)
    Returns:
        None
    """
    # split by material
    # split by material override #
    # split by geo type
    # NOTE: We won't be splitting based on medium interior/exterior
    #       those will be left as a object level assignment only.
    #       Note, that in the case of Houdini Volumes they will look
    #       for the appropriate medium parameters as prim vars

    if properties is None:
        properties = {}

    ignore_materials = False
    if "pbrt_ignorematerials" in properties:
        ignore_materials = properties["pbrt_ignorematerials"].Value[0]

    # PBRT allows setting Material parameters on the Shapes in order to
    #       override a material's settings.  (Shapes get checked first)
    #       This paramset will be for holding those overrides and passing
    #       them down to the actual shape api calls.
    material_paramset = ParamSet()

    # We need the soppath to come along and since we are creating new
    # hou.Geometry() we'll lose the original sop connection so we need
    # to stash it here.

    node = hou.node(soppath)
    if node is None or node.type().category() != hou.sopNodeTypeCategory():
        return

    input_gdp = node.geometry()
    if input_gdp is None:
        return
    gdp = hou.Geometry()
    gdp.merge(input_gdp.freeze())

    # Partition based on materials
    global_material = None
    if not ignore_materials:
        try:
            global_material = gdp.stringAttribValue("shop_materialpath")
        except hou.OperationFailed:
            pass

    attrib_h = gdp.findPrimAttrib("shop_materialpath")
    if attrib_h is not None and not ignore_materials:
        material_gdps = partition_by_attrib(gdp, attrib_h)
    else:
        material_gdps = {global_material: gdp}

    global_override = None
    if not ignore_materials:
        try:
            global_override = gdp.stringAttribValue("material_override")
        except hou.OperationFailed:
            pass

    # Further partition based on material overrides
    has_prim_overrides = bool(
        not ignore_materials and gdp.findPrimAttrib("material_override") is not None
    )

    for material,material_gdp in material_gdps.iteritems():

        if material and material not in scene_state.shading_nodes:
            material = ""

        material_node = None
        if material:
            api.AttributeBegin()
            api.NamedMaterial(material)
            material_node = MaterialNode(material)

        # api.Comment('%s %i' % (material_gdp,len(material_gdp.prims())))

# START
        shape_gdps = partition_by_attrib(material_gdp, "typename", intrinsic=True)
        material_gdp.clear()

        for shape,shape_gdp in shape_gdps.iteritems():


            if has_prim_overrides and shape in requires_override_partition:
                override_attrib_h = material_gdp.findPrimAttrib("material_override")
                override_gdps = partition_by_attrib(shape_gdp, override_attrib_h)
                # Clean up post partition
                shape_gdp.clear()
            else:
                override_gdps = {global_override: shape_gdp}

            for override, override_gdp in override_gdps.iteritems():
                override_paramset = ParamSet()
                if override and material_node is not None:
                    # material parm overrides are only valid for MaterialNodes
                    override_paramset |= material_node.override_paramset(override)

                if has_prim_overrides:
                    api.Comment("PRIM OVERRIDES")
                    properties[".prim_overrides"] = True
                    properties[".material_node"] = material_node

                shape_wrangler = shape_wranglers.get(shape, not_supported)
                if shape_wrangler:
                    shape_wrangler(override_gdp, override_paramset, properties)
                override_gdp.clear()

# END

#        if has_prim_overrides:
#            attrib_h = material_gdp.findPrimAttrib("material_override")
#            override_gdps = partition_by_attrib(material_gdp, attrib_h)
#            # Clean up post partition
#            material_gdp.clear()
#        else:
#            override_gdps = {global_override: material_gdp}
#
#        for override in override_gdps:
#            override_gdp = override_gdps[override]
#            # api.Comment(' %s %i' % (override_gdp, len(override_gdp.prims())))
#
#            shape_gdps = partition_by_attrib(override_gdp, "typename", intrinsic=True)
#            override_gdp.clear()
#
#            for shape in shape_gdps:
#                material_paramset = ParamSet()
#
#                if override and material:
#                    # material parm overrides are only valid for MaterialNodes
#                    material_node = MaterialNode(material)
#                    material_paramset.update(material_node.override_paramset(override))
#
#                shape_gdp = shape_gdps[shape]
#                # api.Comment('  %s %i' % (shape_gdp, len(shape_gdp.prims())))
#
#                shape_wrangler = shape_wranglers.get(shape, not_supported)
#                if shape_wrangler:
#                    shape_wrangler(shape_gdp, material_paramset, properties)
#                shape_gdp.clear()

        if material:
            api.AttributeEnd()
    return
