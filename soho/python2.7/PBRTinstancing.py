from __future__ import print_function, division, absolute_import

import hou
from sohog import SohoGeometry

import PBRTapi as api

def list_instances(obj):

    obj_node = hou.node(obj.getName())
    if not obj_node:
        return

    sop_node = obj_node.renderNode()
    if sop_node is None:
        return

    instance_geos = set()

    # Get the full path to any point instance geos
    geo = sop_node.geometry()
    instance_attrib = geo.findPointAttrib('instance')
    if ( instance_attrib is not None and
         instance_attrib.dataType() == hou.attribData.String ):
        for instance_str in instance_attrib.strings():
            instance_obj = sop_node.node(instance_str)
            if instance_obj:
                instance_geos.add(instance_obj.path())

    # Get the object's instancepath as well
    instance_obj = obj_node.parm('instancepath').evalAsNode()
    if instance_obj:
        instance_geos.add(instance_obj.path())

    return list(instance_geos)


def wrangle_instances(obj, now):

    # We need hou.Node handles so we can resolve relative paths
    # since soho does not do this.
    soppath = []
    if not obj.evalString('object:soppath', now, soppath):
        api.Comment('Can not find soppath for object')
        return
    sop = soppath[0]

    obj_node = hou.node(obj.getName())
    sop_node = hou.node(sop)
    if obj_node is None or sop_node is None:
        api.Comment('Can not resolve obj or geo')
        return

    # Exit out quick if we can't fetch the proper instance attribs.
    geo = SohoGeometry(sop, now)
    if geo.Handle < 0:
        api.Comment('No geometry available, skipping')
        return

    num_pts = geo.globalValue('geo:pointcount')[0]
    if not num_pts:
        api.Comment('No points, skipping')
        return

    pt_attribs = ('geo:pointxform',
                  'instance',
                  # NOTE: Materials can not be applied to ObjectInstances
                  # ( or setting material params (overrides) for that matter
                  # See Excersise B.2 in 'The Book'
                  # same applies for medium interfaces as well.
                  # Applying them to the ObjectInstances does nothing
                  # works on the base instance defintion
                  # 'shop_materialpath',
                  # 'material_override',
                 )

    # TODO: Homogenous volumes work when applied to a ObjectBegin/End however
    #       Heterogenous volumes do not. Currently I'm not sure why this is
    #       the case. Possibly the p0 p1 params aren't being transformed properly
    #       by the instance's CTM.
    #       This is pretty much confirmed by testing, will need to verify in the
    #       pbrt src.

    pt_attrib_map = {}
    for attrib in pt_attribs:
        attrib_h = geo.attribute('geo:point', attrib)
        if attrib_h >= 0:
            pt_attrib_map[attrib] = attrib_h

    if 'geo:pointxform' not in pt_attrib_map:
        api.Comment('Can not find instance xform attribs, skipping')
        return

    instance_geo = []
    obj.evalString('instancepath', now, instance_geo)
    instance_node = obj_node.node(instance_geo[0])
    if instance_node is not None:
        default_instance_geo = instance_node.path()
    else:
        default_instance_geo = ''


    for pt in xrange(num_pts):
        instance_geo = default_instance_geo
        if 'instance' in pt_attrib_map:
            pt_instance_geo = geo.pt_instance_geovalue(pt_attrib_map['instance'], pt)[0]
            pt_instance_node = sop_node.node(pt_instance_geo)
            if pt_instance_node is not None:
                instance_geo = pt_instance_node.path()

        if not instance_geo:
            continue

        with api.AttributeBlock():
            api.Comment('%s:[%i]' % ( sop, pt))
            xform = geo.value(pt_attrib_map['geo:pointxform'], pt)
            api.ConcatTransform(xform)
            api.ObjectInstance(instance_geo)

