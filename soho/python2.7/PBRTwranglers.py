from __future__ import print_function, division, absolute_import

import math
import collections

import hou
import soho
from sohog import SohoGeometry

import PBRTapi as api
import PBRTgeo as Geo
import PBRTinstancing as Instancing

from PBRTstate import scene_state
from PBRTsoho import SohoPBRT
from PBRTnodes import PBRTParam, ParamSet, BaseNode

__all__ = [
    "wrangle_film",
    "wrangle_sampler",
    "wrangle_accelerator",
    "wrangle_integrator",
    "wrangle_filter",
    "wrangle_camera",
    "wrangle_light",
    "wrangle_geo",
    "wrangle_obj",
    "wrangle_shading_network",
]

ShutterRange = collections.namedtuple("ShutterRange", ["open", "close"])


def _apiclosure(api_call, *args, **kwargs):
    def api_func():
        return api_call(*args, **kwargs)

    return api_func


# This function is not being used currently but is a common pattern
# with other SOHO exporters
def get_wrangler(obj, now, style):  # pragma: no coverage
    wrangler = obj.getDefaultedString(style, now, [""])[0]
    wrangler = "%s-PBRT" % wrangler
    if style == "light_wrangler":
        wrangler = soho.LightWranglers.get(wrangler, None)
    elif style == "camera_wrangler":
        wrangler = soho.CameraWranglers.get(wrangler, None)
    elif style == "object_wrangler":
        wrangler = soho.ObjectWranglers.get(wrangler, None)
    else:
        wrangler = None  # Not supported at the current time

    if wrangler:
        wrangler = wrangler(obj, now, "PBRT")
    else:
        wrangler = None
    return wrangler


def get_transform(obj, now, invert=False, flipx=False, flipy=False, flipz=False):
    xform = []
    if not obj.evalFloat("space:world", now, xform):
        return None
    xform = hou.Matrix4(xform)
    if invert:
        xform = xform.inverted()
    x = -1 if flipx else 1
    y = -1 if flipy else 1
    z = -1 if flipz else 1
    xform = xform * hou.hmath.buildScale(x, y, z)
    return list(xform.asTuple())


def xform_to_api_srt(xform, scale=True, rotate=True, trans=True):
    xform = hou.Matrix4(xform)
    srt = xform.explode()
    if trans:
        api.Translate(*srt["translate"])
    if rotate:
        # NOTE, be wary of -180 to 180 flips
        rot = srt["rotate"]
        if rot.z():
            api.Rotate(rot[2], 0, 0, 1)
        if rot.y():
            api.Rotate(rot[1], 0, 1, 0)
        if rot.x():
            api.Rotate(rot[0], 1, 0, 0)
    if scale:
        api.Scale(*srt["scale"])
    return


def output_xform(
    obj, now, no_motionblur=False, invert=False, flipx=False, flipy=False, flipz=False
):
    if no_motionblur:
        shutter_range = None
    else:
        shutter_range = wrangle_motionblur(obj, now)
    if shutter_range is None:
        xform = get_transform(
            obj, now, invert=invert, flipx=flipx, flipy=flipy, flipz=flipz
        )
        api.Transform(xform)
        return
    api.ActiveTransform("StartTime")
    xform = get_transform(
        obj, shutter_range.open, invert=invert, flipx=flipx, flipy=flipy, flipz=flipz
    )
    api.Transform(xform)
    api.ActiveTransform("EndTime")
    xform = get_transform(
        obj, shutter_range.close, invert=invert, flipx=flipx, flipy=flipy, flipz=flipz
    )
    api.Transform(xform)
    api.ActiveTransform("All")
    return


def wrangle_node_parm(obj, parm_name, now):

    parm_selection = {parm_name: SohoPBRT(parm_name, "string", [""], False)}
    parms = obj.evaluate(parm_selection, now)
    if not parms:
        return None
    node_path = parms[parm_name].Value[0]
    if not node_path:
        return None
    return BaseNode(node_path)


def process_full_pt_instance_material(obj, now):

    # The order of evaluation.
    #   1. shaders attached to the actual prims (handled in PBRTgeo.py)
    #   2. per point assignments on the instancer
    #   3. instancer's shop_materialpath
    #   4. object being instanced shop_materialpath
    #   5. nothing
    #   The choice between 3 and 4 is handled automatically by soho

    full_instance_info = Instancing.get_full_instance_info(obj)
    instancer_obj = soho.getObject(full_instance_info.source)
    instancer_sop = []
    if not instancer_obj.evalString("object:soppath", now, instancer_sop):
        return False
    instancer_sop = instancer_sop[0]
    gdp = SohoGeometry(instancer_sop, now)

    override_attrib_h = gdp.attribute("geo:point", "material_override")
    shop_attrib_h = gdp.attribute("geo:point", "shop_materialpath")

    if shop_attrib_h < 0:
        return False

    shop = gdp.value(shop_attrib_h, full_instance_info.number)[0]

    override_str = ""
    if override_attrib_h >= 0:
        override_str = gdp.value(override_attrib_h, full_instance_info.number)[0]

    # We can just reference a NamedMaterial since there are no overrides
    if not override_str:
        if shop in scene_state.shading_nodes:
            api.NamedMaterial(shop)
        else:
            # This shouldn't happen, if it does there is an coding mistake
            raise ValueError("Could not find shop in scene state")
        return True

    # override and shop should exist beyond this point
    # Fully expand shading network since there will be uniqueness
    suffix = ":%s[%i]" % (full_instance_info.source, full_instance_info.number)
    wrangle_shading_network(
        shop,
        use_named=False,
        saved_nodes=set(),
        name_suffix=suffix,
        overrides=override_str,
    )
    return True


def wrangle_shading_network(
    node_path,
    name_prefix="",
    name_suffix="",
    use_named=True,
    saved_nodes=None,
    overrides=None,
    root=True,
):

    # Depth first, as textures/materials need to be
    # defined before they are referenced

    # Use this to track if a node has been output or not.
    # if the saved_nodes is None, we use the global scene_state
    # otherwise we use the one passed in. This is useful for outputing
    # named materials within a nested Attribute Block.
    if saved_nodes is None:
        saved_nodes = scene_state.shading_nodes

    # TODO: Currently (AFAICT) there isn't a case where prefixed and suffixed
    #       names are required. The original intent was to handling instancing
    #       variations, but given that fast instancing doesn't support material
    #       variations it has become moot. The workaround for full instancing is
    #       just to regenerate the shading network each time.
    #       Partitioning based on the different shading overrides might still make
    #       this useful but the current implementation doesn't need this.
    presufed_node_path = name_prefix + node_path + name_suffix
    if presufed_node_path in saved_nodes:
        return

    saved_nodes.add(presufed_node_path)

    hnode = hou.node(node_path)

    # Material or Texture?
    node = BaseNode.from_node(hnode)
    if node is None:
        return

    node.path_suffix = name_suffix
    node.path_prefix = name_prefix

    if node.directive == "material":
        api_call = api.MakeNamedMaterial if use_named else api.Material
    elif node.directive == "texture":
        api_call = api.Texture
    else:
        return

    paramset = node.paramset_with_overrides(overrides)

    for node_input in node.inputs():
        wrangle_shading_network(
            node_input,
            name_prefix=name_prefix,
            name_suffix=name_suffix,
            use_named=use_named,
            saved_nodes=saved_nodes,
            overrides=overrides,
            root=False,
        )

    coord_sys = node.coord_sys
    if coord_sys:
        api.TransformBegin()
        api.Transform(coord_sys)

    if api_call == api.Material:
        api_call(node.directive_type, paramset)
    else:
        api_call(node.full_name, node.output_type, node.directive_type, paramset)
    if coord_sys:
        api.TransformEnd()
    if api_call == api.MakeNamedMaterial:
        print()
    return


def wrangle_motionblur(obj, now):
    mb_parms = [
        soho.SohoParm("allowmotionblur", "int", [0], False),
        soho.SohoParm("shutter", "float", [0.5], False),
        soho.SohoParm("shutteroffset", "float", [None], False),
        soho.SohoParm("motionstyle", "string", ["trailing"], False),
    ]
    eval_mb_parms = obj.evaluate(mb_parms, now)
    if not eval_mb_parms[0].Value[0]:
        return None
    shutter = eval_mb_parms[1].Value[0] * scene_state.inv_fps
    offset = eval_mb_parms[2].Value[0]
    style = eval_mb_parms[3].Value[0]
    # This logic is in part from RIBmisc.py
    # NOTE: For pbrt output we will keep this limited to just shutter and
    #       shutteroffset, if the need arises we can add in the various
    #       scaling options etc.
    if style == "centered":
        delta = shutter * 0.5
    elif style == "leading":
        delta = shutter
    else:  # trailing
        delta = 0.0
    delta -= (offset - 1.0) * 0.5 * shutter
    start_time = now - delta
    end_time = start_time + shutter
    return ShutterRange(start_time, end_time)


def wrangle_film(obj, wrangler, now):

    node = wrangle_node_parm(obj, "film_node", now)
    if node is not None:
        return node.type_and_paramset

    paramset = ParamSet()

    parm_selection = {
        "filename": SohoPBRT("filename", "string", ["pbrt.exr"], False),
        "maxsampleluminance": SohoPBRT("maxsampleluminance", "float", [1e38], True),
        "diagonal": SohoPBRT("diagonal", "float", [35], True),
    }
    parms = obj.evaluate(parm_selection, now)
    for parm_name, parm in parms.iteritems():
        paramset.add(parm.to_pbrt())

    parm_selection = {"res": SohoPBRT("res", "integer", [1280, 720], False)}
    parms = obj.evaluate(parm_selection, now)
    paramset.add(PBRTParam("integer", "xresolution", parms["res"].Value[0]))
    paramset.add(PBRTParam("integer", "yresolution", parms["res"].Value[1]))

    crop_region = obj.getCameraCropWindow(wrangler, now)
    if crop_region != [0.0, 1.0, 0.0, 1.0]:
        paramset.add(PBRTParam("float", "cropwindow", crop_region))

    return ("image", paramset)


def wrangle_filter(obj, wrangler, now):

    node = wrangle_node_parm(obj, "filter_node", now)
    if node is not None:
        return node.type_and_paramset

    parm_selection = {
        "filter": SohoPBRT("filter", "string", ["gaussian"], False),
        "filter_width": SohoPBRT("filter_width", "float", [2.0, 2.0], False),
        "alpha": SohoPBRT("gauss_alpha", "float", [2.0], True, key="alpha"),
        "B": SohoPBRT("mitchell_B", "float", [0.333333], True, key="B"),
        "C": SohoPBRT("mitchell_C", "float", [0.333333], True, key="C"),
        "tau": SohoPBRT("sinc_tau", "float", [3], True, key="tau"),
    }
    parms = obj.evaluate(parm_selection, now)

    filter_name = parms["filter"].Value[0]
    paramset = ParamSet()
    xwidth = parms["filter_width"].Value[0]
    ywidth = parms["filter_width"].Value[1]
    paramset.add(PBRTParam("float", "xwidth", xwidth))
    paramset.add(PBRTParam("float", "ywidth", ywidth))

    if filter_name == "gaussian" and "alpha" in parms:
        paramset.add(parms["alpha"].to_pbrt())
    if filter_name == "mitchell" and "mitchell_B" in parms:
        paramset.add(parms["B"].to_pbrt())
    if filter_name == "mitchell" and "mitchell_C" in parms:
        paramset.add(parms["C"].to_pbrt())
    if filter_name == "sinc" and "tau" in parms:
        paramset.add(parms["tau"].to_pbrt())
    return (filter_name, paramset)


def wrangle_sampler(obj, wrangler, now):

    node = wrangle_node_parm(obj, "sampler_node", now)
    if node is not None:
        return node.type_and_paramset

    parm_selection = {
        "sampler": SohoPBRT("sampler", "string", ["halton"], False),
        "pixelsamples": SohoPBRT("pixelsamples", "integer", [16], False),
        "jitter": SohoPBRT("jitter", "bool", [1], False),
        "samples": SohoPBRT("samples", "integer", [4, 4], False),
        "dimensions": SohoPBRT("dimensions", "integer", [4], False),
    }
    parms = obj.evaluate(parm_selection, now)

    sampler_name = parms["sampler"].Value[0]
    paramset = ParamSet()

    if sampler_name == "stratified":
        xsamples = parms["samples"].Value[0]
        ysamples = parms["samples"].Value[1]
        paramset.add(PBRTParam("integer", "xsamples", xsamples))
        paramset.add(PBRTParam("integer", "ysamples", ysamples))
        paramset.add(parms["jitter"].to_pbrt())
        paramset.add(parms["dimensions"].to_pbrt())
    else:
        paramset.add(parms["pixelsamples"].to_pbrt())

    return (sampler_name, paramset)


def wrangle_integrator(obj, wrangler, now):

    node = wrangle_node_parm(obj, "integrator_node", now)
    if node is not None:
        return node.type_and_paramset

    parm_selection = {
        "integrator": SohoPBRT("integrator", "string", ["path"], False),
        "maxdepth": SohoPBRT("maxdepth", "integer", [5], False),
        "rrthreshold": SohoPBRT("rrthreshold", "float", [1], True),
        "lightsamplestrategy": SohoPBRT(
            "lightsamplestrategy", "string", ["spatial"], True
        ),
        "visualizestrategies": SohoPBRT("visualizestrategies", "toggle", [False], True),
        "visualizeweights": SohoPBRT("visualizeweights", "toggle", [False], True),
        "iterations": SohoPBRT("iterations", "integer", [64], True),
        "photonsperiterations": SohoPBRT("photonsperiterations", "integer", [-1], True),
        "imagewritefrequency": SohoPBRT(
            "imagewritefrequency", "integer", [2.14748e09], True
        ),
        "radius": SohoPBRT("radius", "float", [1], True),
        "bootstrapsamples": SohoPBRT("bootstrapsamples", "integer", [100000], True),
        "chains": SohoPBRT("chains", "integer", [1000], True),
        "mutationsperpixel": SohoPBRT("mutataionsperpixel", "integer", [100], True),
        "largestepprobability": SohoPBRT("largestepprobability", "float", [0.3], True),
        "sigma": SohoPBRT("sigma", "float", [0.01], True),
        "strategy": SohoPBRT("strategy", "string", ["all"], True),
        "nsamples": SohoPBRT("nsamples", "integer", ["64"], True),
        "cossample": SohoPBRT("cossample", "toggle", [True], True),
    }

    integrator_parms = {
        "ao": ["nsamples", "cossample"],
        "path": ["maxdepth", "rrthreshold", "lightsamplestrategy"],
        "bdpt": [
            "maxdepth",
            "rrthreshold",
            "lightsamplestrategy",
            "visualizestrategies",
            "visualizeweights",
        ],
        "mlt": [
            "maxdepth",
            "bootstrapsamples",
            "chains",
            "mutationsperpixel",
            "largestepprobability",
            "sigma",
        ],
        "sppm": [
            "maxdepth",
            "iterations",
            "photonsperiteration",
            "imagewritefrequency",
            "radius",
        ],
        "whitted": ["maxdepth"],
        "volpath": ["maxdepth", "rrthreshold", "lightsamplestrategy"],
        "directlighting": ["maxdepth", "strategy"],
    }
    parms = obj.evaluate(parm_selection, now)

    integrator_name = parms["integrator"].Value[0]
    paramset = ParamSet()
    for parm_name in integrator_parms[integrator_name]:
        if parm_name not in parms:
            continue
        paramset.add(parms[parm_name].to_pbrt())

    return (integrator_name, paramset)


def wrangle_accelerator(obj, wrangler, now):

    node = wrangle_node_parm(obj, "accelerator_node", now)
    if node is not None:
        return node.type_and_paramset

    parm_selection = {"accelerator": SohoPBRT("accelerator", "string", ["bvh"], False)}
    parms = obj.evaluate(parm_selection, now)
    accelerator_name = parms["accelerator"].Value[0]

    if accelerator_name == "bvh":
        parm_selection = {
            "maxnodeprims": SohoPBRT("maxnodeprims", "integer", [4], True),
            "splitmethod": SohoPBRT("splitmethod", "string", ["sah"], True),
        }
    else:
        parm_selection = {
            "intersectcost": SohoPBRT("intersectcost", "integer", [80], True),
            "traversalcostcost": SohoPBRT("traversalcost", "integer", [1], True),
            "emptybonus": SohoPBRT("emptybonus", "float", [0.2], True),
            "maxprims": SohoPBRT("maxprims", "integer", [1], True),
            "kdtree_maxdepth": SohoPBRT(
                "kdtree_maxdepth", "integer", [1], True, key="maxdepth"
            ),
        }
    parms = obj.evaluate(parm_selection, now)

    paramset = ParamSet()

    for parm in parms:
        paramset.add(parms[parm].to_pbrt())

    return (accelerator_name, paramset)


def output_cam_xform(obj, projection, now):
    # NOTE: Initial tests show pbrt has problems when motion blur xforms
    #       are applied to the camera (outside the World block)
    if projection in ("perspective", "orthographic", "realistic"):
        output_xform(obj, now, no_motionblur=True, invert=True, flipz=True)
    elif projection in ("environment",):
        api.Rotate(-180, 0, 1, 0)
        output_xform(obj, now, invert=True, flipx=True, flipz=True)
    return


def wrangle_camera(obj, wrangler, now):

    node = wrangle_node_parm(obj, "camera_node", now)
    if node is not None:
        output_cam_xform(obj, node.directive_type, now)
        return node.type_and_paramset

    paramset = ParamSet()

    window = obj.getCameraScreenWindow(wrangler, now)
    parm_selection = {
        "projection": SohoPBRT("projection", "string", ["perspective"], False),
        "focal": SohoPBRT("focal", "float", [50], False),
        "focalunits": SohoPBRT("focalunits", "string", ["mm"], False),
        "aperture": SohoPBRT("aperture", "float", [41.4214], False),
        "orthowidth": SohoPBRT("orthowidth", "float", [2], False),
        "res": SohoPBRT("res", "integer", [1280, 720], False),
        "aspect": SohoPBRT("aspect", "float", [1], False),
        "fstop": SohoPBRT("fstop", "float", [5.6], False),
        "focaldistance": SohoPBRT("focus", "float", [5], False, key="focaldistance"),
        "pbrt_dof": SohoPBRT("pbrt_dof", "integer", [0], False),
    }

    parms = obj.evaluate(parm_selection, now)
    aspect = parms["aspect"].Value[0]
    aspectfix = aspect * float(parms["res"].Value[0]) / float(parms["res"].Value[1])

    projection = parms["projection"].Value[0]

    if parms["pbrt_dof"].Value[0]:
        paramset.add(parms["focaldistance"].to_pbrt())
        # to convert from f-stop to lens radius
        # FStop = FocalLength / (Radius * 2)
        # Radius = FocalLength/(FStop * 2)
        focal = parms["focal"].Value[0]
        fstop = parms["fstop"].Value[0]
        units = parms["focalunits"].Value[0]
        focal = soho.houdiniUnitLength(focal, units)
        lens_radius = focal / (fstop * 2.0)
        paramset.add(PBRTParam("float", "lensradius", lens_radius))

    if projection == "perspective":
        projection_name = "perspective"

        focal = parms["focal"].Value[0]
        aperture = parms["aperture"].Value[0]
        fov = 2.0 * focal / aperture
        fov = 2.0 * math.degrees(math.atan2(1.0, fov))
        paramset.add(PBRTParam("float", "fov", [fov]))

        screen = [
            (window[0] - 0.5) * 2.0,
            (window[1] - 0.5) * 2.0,
            (window[2] - 0.5) * 2.0 / aspectfix,
            (window[3] - 0.5) * 2.0 / aspectfix,
        ]
        paramset.add(PBRTParam("float", "screenwindow", screen))

    elif projection == "ortho":
        projection_name = "orthographic"

        width = parms["orthowidth"].Value[0]
        screen = [
            (window[0] - 0.5) * width,
            (window[1] - 0.5) * width,
            (window[2] - 0.5) * width / aspectfix,
            (window[3] - 0.5) * width / aspectfix,
        ]
        paramset.add(PBRTParam("float", "screenwindow", screen))

    elif projection == "sphere":
        projection_name = "environment"
    else:
        soho.error("Camera projection setting of %s not supported by PBRT" % projection)

    output_cam_xform(obj, projection_name, now)

    return (projection_name, paramset)


def _to_light_scale(parms):
    """Converts light_intensity, light_exposure to a single scale value"""
    # TODO
    # There is a potential issue with using "rgb" types for
    # both L and scale as noted here -
    # https://groups.google.com/d/msg/pbrt/EyT6F-zfBkE/M23oQwGNCAAJ
    # To summarize, when using SpectralSamples instead of RGBSamples,
    # using an "rgb" type for both L and scale can result in a double
    # application of the D65 illuminate.
    #
    # Since Houdini's scale (intensity) parameter is a float this issue should
    # be avoidable.
    #
    # Proper tests are required however.

    intensity = parms["light_intensity"].Value[0]
    exposure = parms["light_exposure"].Value[0]
    scale = intensity * (2.0 ** exposure)
    return PBRTParam("rgb", "scale", [scale] * 3)


def _light_api_wrapper(wrangler_light_type, wrangler_paramset, node):
    if node is not None:
        ltype = node.directive_type
        paramset = node.paramset
        is_arealight = bool(node.directive == "arealight")
    else:
        ltype = wrangler_light_type
        paramset = wrangler_paramset
        is_arealight = bool(ltype == "diffuse")

    if is_arealight:
        api.AreaLightSource(ltype, paramset)
    else:
        api.LightSource(ltype, paramset)


def wrangle_light(light, wrangler, now):

    # NOTE: Lights do not support motion blur so we disable it when
    #       outputs the xforms

    node = wrangle_node_parm(light, "light_node", now)

    parm_selection = {
        "light_wrangler": SohoPBRT("light_wrangler", "string", [""], False),
        "light_color": SohoPBRT("light_color", "float", [1, 1, 1], False),
        "light_intensity": SohoPBRT("light_intensity", "float", [1], False),
        "light_exposure": SohoPBRT("light_exposure", "float", [0], False),
    }
    parms = light.evaluate(parm_selection, now)
    light_wrangler = parms["light_wrangler"].Value[0]

    paramset = ParamSet()
    paramset.add(_to_light_scale(parms))

    if light_wrangler == "HoudiniEnvLight":
        env_map = []
        paramset.add(PBRTParam("rgb", "L", parms["light_color"].Value))
        if light.evalString("env_map", now, env_map):
            paramset.add(PBRTParam("string", "mapname", env_map))
        output_xform(light, now, no_motionblur=True)
        api.Scale(1, 1, -1)
        api.Rotate(90, 0, 0, 1)
        api.Rotate(90, 0, 1, 0)
        _light_api_wrapper("infinite", paramset, node)
        return
    elif light_wrangler != "HoudiniLight":
        api.Comment("This light type, %s, is unsupported" % light_wrangler)
        return

    # We are dealing with a standard HoudiniLight type.

    light_type = light.wrangleString(wrangler, "light_type", now, ["point"])[0]

    if light_type in ("sphere", "disk", "grid", "tube", "geo"):

        single_sided = light.wrangleInt(wrangler, "singlesided", now, [0])[0]
        visible = light.wrangleInt(wrangler, "light_contribprimary", now, [0])[0]
        size = light.wrangleFloat(wrangler, "areasize", now, [1, 1])
        paramset.add(PBRTParam("rgb", "L", parms["light_color"].Value))
        paramset.add(PBRTParam("bool", "twosided", [not single_sided]))

        # TODO, Possibly get the xform's scale and scale the geo, not the light.
        #       (for example, further multiplying down the radius)
        xform = get_transform(light, now)
        xform_to_api_srt(xform, scale=False)

        _light_api_wrapper("diffuse", paramset, node)

        api.AttributeBegin()

        # PBRT only supports uniform scales for non-mesh area lights
        # this is in part due to explicit light's area scaling factor.
        if light_type in ("grid", "geo"):
            api.Scale(size[0], size[1], size[0])

        # The visibility only applies to hits on the non-emissive side of the light.
        # the emissive side will still be rendered
        if not visible:
            api.Material("none")

        if light_type == "sphere":
            # We apply the scale to the radius instead of using a api.Scale
            api.Shape("sphere", [PBRTParam("float", "radius", 0.5 * size[0])])
        elif light_type == "tube":
            api.Rotate(90, 0, 1, 0)
            api.Shape(
                "cylinder",
                [
                    PBRTParam("float", "radius", 0.075 * size[1]),
                    PBRTParam("float", "zmin", -0.5 * size[0]),
                    PBRTParam("float", "zmax", 0.5 * size[0]),
                ],
            )
        elif light_type == "disk":
            # After pbrt-v3 commit #2f0852ce api.ReverseOrientation() is needed,
            # prior that it was a api.Scale(1,1,-1)
            # (see issue #183 in pbrt-v3)
            api.ReverseOrientation()
            api.Shape("disk", [PBRTParam("float", "radius", 0.5 * size[0])])
        elif light_type == "grid":
            api.Shape(
                "trianglemesh",
                [
                    PBRTParam("integer", "indices", [0, 3, 1, 0, 2, 3]),
                    PBRTParam(
                        "point",
                        "P",
                        [-0.5, -0.5, 0, 0.5, -0.5, 0, -0.5, 0.5, 0, 0.5, 0.5, 0],
                    ),
                ],
            )
        elif light_type == "geo":
            areageo_parm = hou.node(light.getName()).parm("areageometry")
            if not areageo_parm:
                api.Comment('No "areageometry" parm on light')
                return
            area_geo_node = areageo_parm.evalAsNode()
            if not area_geo_node:
                api.Comment("Skipping, no geometry object specified")
                return
            obj = soho.getObject(area_geo_node.path())
            api.Comment("Light geo from %s" % obj.getName())
            # TODO: The area light scale ('areasize') happens *after* the wrangle_obj's
            #       xform when 'intothisobject' is enabled.
            into_this_obj = light.wrangleInt(wrangler, "intothisobject", now, [0])[0]
            ignore_xform = not into_this_obj
            wrangle_obj(obj, None, now, ignore_xform=ignore_xform)

        api.AttributeEnd()

        return

    cone_enable = light.wrangleInt(wrangler, "coneenable", now, [0])[0]
    projmap = light.wrangleString(wrangler, "projmap", now, [""])[0]
    areamap = light.wrangleString(wrangler, "areamap", now, [""])[0]

    api_calls = []
    api_calls.append(_apiclosure(output_xform, light, now, no_motionblur=True))
    api_calls.append(_apiclosure(api.Scale, 1, 1, -1))
    api_calls.append(_apiclosure(api.Scale, 1, -1, 1))

    if light_type == "point":
        paramset.add(PBRTParam("rgb", "I", parms["light_color"].Value))
        if areamap:
            light_name = "goniometric"
            paramset.add(PBRTParam("string", "mapname", [areamap]))
            api_calls = []
            api_calls.append(_apiclosure(output_xform, light, now, no_motionblur=True))
            api_calls.append(_apiclosure(api.Scale, 1, -1, 1))
            api_calls.append(_apiclosure(api.Rotate, 90, 0, 1, 0))
        elif not cone_enable:
            light_name = "point"
        else:
            conedelta = light.wrangleFloat(wrangler, "conedelta", now, [10])[0]
            coneangle = light.wrangleFloat(wrangler, "coneangle", now, [45])[0]
            if projmap:
                light_name = "projection"
                paramset.add(PBRTParam("float", "fov", [coneangle]))
                paramset.add(PBRTParam("string", "mapname", [projmap]))
            else:
                light_name = "spot"
                coneangle *= 0.5
                coneangle += conedelta
                paramset.add(PBRTParam("float", "coneangle", [coneangle]))
                paramset.add(PBRTParam("float", "conedeltaangle", [conedelta]))
    elif light_type == "distant":
        light_name = light_type
        paramset.add(PBRTParam("rgb", "L", parms["light_color"].Value))
    else:
        api.Comment("Light Type, %s, not supported" % light_type)
        return

    for api_call in api_calls:
        api_call()
    _light_api_wrapper(light_name, paramset, node)

    return


def wrangle_obj(obj, wrangler, now, ignore_xform=False):

    ptinstance = []
    has_ptinstance = obj.evalInt("ptinstance", now, ptinstance)

    if not ignore_xform:
        output_xform(obj, now)

    if has_ptinstance and ptinstance[0] == 2:
        # This is "fast instancing", "full instancing" results in Soho outputing
        # actual objects which independently need to be wrangled.
        Instancing.wrangle_fast_instances(obj, now)
        return

    wrangle_geo(obj, wrangler, now)
    return


def wrangle_geo(obj, wrangler, now):
    parm_selection = {
        "object:soppath": SohoPBRT("object:soppath", "string", [""], skipdefault=False),
        "ptinstance": SohoPBRT("ptinstance", "integer", [0], skipdefault=False),
        # NOTE: In order for shop_materialpath to evaluate correctly when using
        #       (full) instancing shop_materialpath needs to be a 'shaderhandle'
        #       and not a 'string'
        # NOTE: However this does not seem to apply to shop_materialpaths on the
        #       instance points and has to be done manually
        "shop_materialpath": SohoPBRT(
            "shop_materialpath", "shaderhandle", skipdefault=False
        ),
        "pbrt_rendersubd": SohoPBRT("pbrt_rendersubd", "bool", [False], False),
        "pbrt_subdlevels": SohoPBRT(
            "pbrt_subdlevels", "integer", [3], False, key="levels"
        ),
        "pbrt_computeN": SohoPBRT("pbrt_computeN", "bool", [True], False),
        # The combination of None as a default as well as ignore defaults being False
        # is important. 'None' implying the parm is missing and not available,
        # and '' meaning a vacuum medium.
        # We can't ignore defaults since a default might be the only way to set a
        # medium back to a vacuum.
        "pbrt_interior": SohoPBRT("pbrt_interior", "string", [None], False),
        "pbrt_exterior": SohoPBRT("pbrt_exterior", "string", [None], False),
        "pbrt_ignorevolumes": SohoPBRT("pbrt_ignorevolumes", "bool", [False], True),
        "pbrt_ignorematerials": SohoPBRT("pbrt_ignorematerials", "bool", [False], True),
        "pbrt_splitdepth": SohoPBRT(
            "pbrt_splitdepth", "integer", [3], True, key="splitdepth"
        ),
        # We don't use the key=type since its a bit too generic of a name
        "pbrt_curvetype": SohoPBRT("pbrt_curvetype", "string", ["flat"], True),
        "pbrt_include": SohoPBRT("pbrt_include", "string", [""], False),
        "pbrt_alpha_texture": SohoPBRT(
            "pbrt_alpha_texture", "string", [""], skipdefault=False, key="alpha"
        ),
        "pbrt_shadowalpha_texture": SohoPBRT(
            "pbrt_shadowalpha_texture",
            "string",
            [""],
            skipdefault=False,
            key="shadowalpha",
        ),
        # TODO, Tesselation options?
    }
    properties = obj.evaluate(parm_selection, now)

    if "shop_materialpath" not in properties:
        shop = ""
    else:
        shop = properties["shop_materialpath"].Value[0]

    # NOTE: Having to track down shop_materialpaths does not seem to be a requirement
    #       with Mantra or RenderMan. Either its because I'm missing some
    #       logic/initialization either in Soho or in the Shading HDAs. Or there is
    #       some hardcoding in the Houdini libs that know how to translate
    #       shop_materialpath point aassignments to shaders directly through a
    #       SohoParm. Until that is figured out, we'll have to do it manually.

    pt_shop_found = False
    if properties["ptinstance"].Value[0] == 1:
        pt_shop_found = process_full_pt_instance_material(obj, now)

    # If we found a point shop, don't output the default one here.
    if shop in scene_state.shading_nodes and not pt_shop_found:
        api.NamedMaterial(shop)

    interior = None
    exterior = None
    if "pbrt_interior" in properties:
        interior = properties["pbrt_interior"].Value[0]
    if "pbrt_exterior" in properties:
        exterior = properties["pbrt_exterior"].Value[0]

    # We only output a MediumInterface if one or both of the parms exist
    if interior is not None or exterior is not None:
        interior = "" if interior is None else interior
        exterior = "" if exterior is None else exterior
        api.MediumInterface(interior, exterior)

    for prop in ("alpha", "shadowalpha"):
        alpha_tex = properties[prop].Value[0]
        alpha_node = BaseNode.from_node(alpha_tex)
        if (
            alpha_node
            and alpha_node.directive == "texture"
            and alpha_node.output_type == "float"
        ):
            if alpha_node.path not in scene_state.shading_nodes:
                wrangle_shading_network(alpha_node.path, saved_nodes=set())
        else:
            # If the passed in alpha_texture wasn't valid, clear it so we don't add
            # it to the geometry
            if alpha_tex:
                api.Comment("%s is an invalid float texture" % alpha_tex)
            properties[prop].Value[0] = ""

    if properties["pbrt_include"].Value[0]:
        # If we have included a file, skip output any geo.
        api.Include(properties["pbrt_include"].Value[0])
        return

    soppath = properties["object:soppath"].Value[0]
    if not soppath:
        api.Comment("Can not find soppath for object")
        return

    Geo.output_geo(soppath, now, properties)
    return
