from __future__ import print_function, division, absolute_import

import hou
from sohog import SohoGeometry

import PBRTapi as api

def list_instances(obj):
    """Find and list any instances in a Soho Object"""

    # We will be using a hou.Node instead of a Soho Object for this
    # so we can just query the strings directly instead of having to
    # iterate over all the points.

    obj_node = hou.node(obj.getName())
    if not obj_node:
        return None

    sop_node = obj_node.renderNode()
    if sop_node is None:
        return None

    geo = sop_node.geometry()
    if geo is None:
        return None

    instance_geos = set()

    # Get the full path to any point instance geos
    instance_attrib = geo.findPointAttrib('instance')
    if (instance_attrib is not None and
            instance_attrib.dataType() == hou.attribData.String):
        for instance_str in instance_attrib.strings():
            instance_obj = sop_node.node(instance_str)
            if instance_obj:
                instance_geos.add(instance_obj.path())

    # Get the object's instancepath as well
    instancepath_parm = obj_node.parm('instancepath')
    if instancepath_parm:
        instance_obj = instancepath_parm.evalAsNode()
        if instance_obj:
            instance_geos.add(instance_obj.path())

    return list(instance_geos)


def wrangle_instances(obj, now):
    """Output any instanced geoemtry referenced by the Soho Object"""

    # We need hou.Node handles so we can resolve relative paths
    # since soho does not do this.
    # NOTE: the above isn't true, some cleverness from RIBsettings shows
                # if len(shop_path) > 0:
                #   if not posixpath.isabs(shop_path):
                #     # make the shop_path absolute
                #     obj_path = obj.getDefaultedString("object:name", now, [''])[0]
                #     shop_path = posixpath.normpath(posixpath.join(obj_path, shop_path))
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

    # NOTE: Homogenous volumes work when applied to a ObjectBegin/End however
    #       Heterogenous volumes do not. The p0 p1 params aren't being
    #       transformed properly by the instance's CTM.

    pt_attrib_map = {}
    for attrib in pt_attribs:
        attrib_h = geo.attribute('geo:point', attrib)
        if attrib_h >= 0:
            pt_attrib_map[attrib] = attrib_h

    if 'geo:pointxform' not in pt_attrib_map:
        api.Comment('Can not find instance xform attribs, skipping')
        return

    instancepath = []
    obj.evalString('instancepath', now, instancepath)
    instance_node = obj_node.node(instancepath[0])
    if instance_node is not None:
        default_instance_geo = instance_node.path()
    else:
        default_instance_geo = ''


    for pt in xrange(num_pts):
        instance_geo = default_instance_geo
        if 'instance' in pt_attrib_map:
            pt_instance_geo = geo.value(pt_attrib_map['instance'], pt)[0]
            pt_instance_node = sop_node.node(pt_instance_geo)
            if pt_instance_node is not None:
                instance_geo = pt_instance_node.path()

        if not instance_geo:
            continue

        with api.AttributeBlock():
            api.Comment('%s:[%i]' % (sop, pt))
            xform = geo.value(pt_attrib_map['geo:pointxform'], pt)
            api.ConcatTransform(xform)
            api.ObjectInstance(instance_geo)
    return
