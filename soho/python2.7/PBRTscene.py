from __future__ import print_function, division, absolute_import

import time

import hou
import soho

from sohog import SohoGeometry

import PBRTapi as api
from PBRTwranglers import *
from PBRTplugins import BaseNode
from PBRTinstancing import list_instances

from PBRTstate import scene_state


def output_materials(obj, wrangler, now):
    parms = [ soho.SohoParm('shop_materialpath', 'shaderhandle', skipdefault=False)]
    eval_parms = obj.evaluate(parms, now)
    if eval_parms:
        shop = eval_parms[0].Value[0]

    if shop:
        wrangle_shading_network(shop)

    soppath = []
    if not obj.evalString('object:soppath', now, soppath):
        return
    soppath = soppath[0]

    gdp = SohoGeometry(soppath, now)
    global_material = gdp.globalValue('shop_materialpath')
    if global_material is not None:
        wrangle_shading_network(global_material[0])

    attrib_h = gdp.attribute('geo:prim', 'shop_materialpath')
    if attrib_h >= 0:
        shop_materialpaths = gdp.attribProperty(attrib_h, 'geo:allstrings')
        for shop in shop_materialpaths:
            wrangle_shading_network(shop)
    return

def output_medium(medium):
    if not medium:
        return None
    if medium in scene_state.medium_nodes:
        return None
    scene_state.medium_nodes.add(medium)

    medium_vop = BaseNode.from_node(medium)
    if medium_vop is None:
        return None
    if medium_vop.directive_type != 'pbrt_medium':
        return None

    api.MakeNamedMedium(medium_vop.name, 'homogeneous', medium_vop.paramset)
    return medium_vop.name


def output_mediums(obj, wrangler, now):
    exterior = obj.wrangleString(wrangler, 'pbrt_exterior', now, [None])[0]
    interior = obj.wrangleString(wrangler, 'pbrt_interior', now, [None])[0]

    exterior = output_medium(exterior)
    interior = output_medium(interior)

    return interior, exterior


def output_instances(obj, wrangler, now):
    instances = list_instances(obj)
    if not instances:
        return

    for instance in instances:
        if instance in scene_state.instanced_geo:
            continue
        scene_state.instanced_geo.add(instance)

        # Since a referenced geo might not be displayed, output its
        # mediums if any.
        # TODO this works but is a bit magic, rethink this and see if there
        # is a better approach.
        instance_obj = soho.getObject(instance)
        output_materials(instance_obj, wrangler, now)
        output_mediums(instance_obj, wrangler, now)

        with api.ObjectBlock(instance), api.AttributeBlock():
            soho_obj = soho.getObject(instance)
            wrangle_geo(soho_obj, wrangler, now)
        print()

def header():
    if scene_state.ver is not None:
        api.Comment('Houdini Version %s' % scene_state.ver)
    api.Comment('Generation Time: %s' % time.strftime("%b %d, %Y at %H:%M:%S"))
    if scene_state.hip and scene_state.hipname:
        api.Comment('Hip File: %s.%s' % (scene_state.hip, scene_state.hipname))
    if scene_state.rop is not None:
        api.Comment('Output Driver: %s' % scene_state.rop)
    if scene_state.now is not None:
        api.Comment('Output Time: %s' % scene_state.now)
    if scene_state.fps:
        api.Comment('Output FPS: %s' % scene_state.fps)

def render(cam, now):

    # For now we will not be using wranglers
    wrangler = None

    header()
    print()

    api.Film(*wrangle_film(cam, wrangler, now))
    api.Filter(*wrangle_filter(cam, wrangler, now))
    api.Sampler(*wrangle_sampler(cam, wrangler, now))
    api.Integrator(*wrangle_integrator(cam, wrangler, now))
    api.Accelerator(*wrangle_accelerator(cam, wrangler, now))

    print()

    # wrangle_camera will output api.Transforms
    api.Comment(cam.getName())
    api.Camera(*wrangle_camera(cam, wrangler, now))

    print()

    interior,exterior = output_mediums(cam, wrangler, now)
    scene_state.exterior = exterior
    scene_state.interior = interior
    if exterior:
        api.MediumInterface('', exterior)
        print()

    api.WorldBegin()

    print()

    api.Comment('='*50)
    api.Comment('Light Definitions')
    print()
    for light in soho.objectList('objlist:light'):
        api.Comment(light.getName())
        with api.AttributeBlock():
            wrangle_light(light, wrangler, now)
        print()

    print()

    # Output Materials
    api.Comment('='*50)
    api.Comment('NamedMaterial Definitions')
    for obj in soho.objectList('objlist:instance'):
        output_materials(obj, wrangler, now)

    print()

    # Output NamedMediums
    api.Comment('='*50)
    api.Comment('NamedMedium Definitions')
    for obj in soho.objectList('objlist:instance'):
        output_mediums(obj, wrangler, now)

    print()

    # Output Object Instances
    api.Comment('='*50)
    api.Comment('Object Instance Definitions')
    for obj in soho.objectList('objlist:instance'):
        output_instances(obj, wrangler, now)

    print()

    # Output Geometry
    api.Comment('='*50)
    api.Comment('Geometry Definitions')
    for obj in soho.objectList('objlist:instance'):
        api.Comment('-'*50)
        api.Comment(obj.getName())
        with api.AttributeBlock():
            wrangle_obj(obj, wrangler, now)
        print()

    print()

    api.WorldEnd()

    return
