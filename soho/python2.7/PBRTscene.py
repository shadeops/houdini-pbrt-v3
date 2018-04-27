from __future__ import print_function

import hou
import soho

from sohog import SohoGeometry

import PBRTapi as api
from PBRTwranglers import *
from PBRTplugins import PBRTParam, MaterialPlugin, TexturePlugin

shading_nodes = set()

def output_shading_network(node_path):
    # Depth first, as textures/materials need to be
    # defined before they are referenced

    if node_path in shading_nodes:
        return

    node = hou.node(node_path)
    shading_nodes.add(node_path)

    # Material or Texture?
    if 'struct_PBRTMaterial' in node.outputDataTypes():
        plugin = MaterialPlugin(node)
        api_call = api.MakeNamedMaterial
    else:
        plugin = TexturePlugin(node)
        api_call = api.Texture

    for plugin_input in plugin.inputs():
        output_shading_network(plugin_input)

    coord_sys = plugin.coord_sys
    if coord_sys:
        api.TransformBegin()
        api.Transform(coord_sys)
    api_call(plugin.name,
             plugin.output_type,
             plugin.plugin_class,
             plugin.paramset)
    if coord_sys:
        api.TransformEnd()
    return


def output_materials(obj, wrangler, now):
    shop = obj.wrangleString(wrangler, 'shop_materialpath', now, [''])[0]
    if shop:
        output_shading_network(shop)

    soppath = []
    if not obj.evalString('object:soppath', now, soppath):
        return
    soppath = soppath[0]

    gdp = SohoGeometry(soppath, now)
    global_material = gdp.globalValue('shop_materialpath')
    if global_material is not None:
        output_shading_network(global_material[0])

    attrib_h = gdp.attribute('geo:prim', 'shop_materialpath')
    if attrib_h >= 0:
        shop_materialpaths = gdp.attribProperty(attrib_h, 'geo:allstrings')
        for shop in shop_materialpaths:
            output_shading_network(shop)
    return

def render(cam, now):

    shading_nodes.clear()

    # For now we will not be using wranglers
    wrangler = None

    api.Comment('Rendering %s' % soho.getOutputDriver().getName())
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

    api.WorldBegin()

    print()

    api.Comment('==========================')
    api.Comment('Light Definitions')
    print()
    for light in soho.objectList('objlist:light'):
        api.Comment(light.getName())
        with api.AttributeBlock():
            wrangle_light(light, wrangler, now)
        print()

    # Output Materials
    api.Comment('==========================')
    api.Comment('NamedMaterial Definitions')
    for obj in soho.objectList('objlist:instance'):
        output_materials(obj, wrangler, now)
        print()

    # Output Geometry
    api.Comment('==========================')
    api.Comment('Geometry Definitions')
    for obj in soho.objectList('objlist:instance'):
        api.Comment(obj.getName())
        with api.AttributeBlock():
            wrangle_geo(obj, wrangler, now)
        print()

    print()

    api.WorldEnd()

    return
