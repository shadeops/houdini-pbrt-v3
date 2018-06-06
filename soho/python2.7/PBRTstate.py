from __future__ import print_function, division, absolute_import

import hou
import soho

class PBRTState(object):
    """Holds the global state of the render session.

    This class can also act as a context, which will create helper networks
    and destory them on exit.
    """

    # TODO replace the cachedUserData workflow with a hou.Geometry parm
    _tesslate_py = """
node = hou.pwd()
geo = node.geometry()
geo.clear()
gdp = hou.node('..').cachedUserData('gdp')
if gdp is not None:
    geo.merge(gdp)
"""

    def __init__(self):
        self.shading_nodes = set()
        self.medium_nodes = set()
        self.instanced_geo = set()
        # We do not interior/exterior these directly but are handy as
        # a quick way of seeing if they are set at the camera/rop
        # level
        self.interior = None
        self.exterior = None
        self.tesselator = None

        self.rop = None
        self.hip = None
        self.hipname = None
        self.fps = None
        self.ver = None
        self.now = None

        self.inv_fps = None
        return

    def init_state(self):
        """Queries Soho to initialize the attributes of the class"""
        state_parms = {
            'rop' : soho.SohoParm('object:name', 'string', key='rop'),
            'hip' : soho.SohoParm('$HIP', 'string', key='hip'),
            'hipname' : soho.SohoParm('$HIPNAME', 'string', key='hipname'),
            'ver' : soho.SohoParm('state:houdiniversion', 'string', ["9.0"], False, key='ver'),
            'now' : soho.SohoParm('state:time', 'real', [0], False, key='now'),
            'fps' : soho.SohoParm('state:fps', 'real', [24], False, key='fps'),
        }
        rop = soho.getOutputDriver()
        parms = soho.evaluate(state_parms, None, rop)
        for parm in parms:
            setattr(self, parm, parms[parm].Value[0])
        if not self.fps:
            self.fps = 24.0
        self.inv_fps = 1.0/self.fps
        return

    def __enter__(self):
        self.reset()
        self.init_state()
        self.tesselator = self.create_tesselator()
        return

    def __exit__(self, *args):
        self.reset()
        return

    def reset(self):
        """Resets the class attributes back to their default state"""
        self.rop = None
        self.hip = None
        self.hipname = None
        self.fps = None
        self.ver = None
        self.now = None
        self.inv_fps = None
        self.shading_nodes.clear()
        self.medium_nodes.clear()
        self.instanced_geo.clear()
        self.interior = None
        self.exterior = None
        self.remove_tesselator()
        return

    def tesselate_geo(self, geo):
        """Takes an hou.Geometry and returns a tesselated version"""

        if self.tesselator is None:
            raise TypeError('Tesselator is None')
        self.tesselator.setCachedUserData('gdp', geo)
        self.tesselator.node('python').cook(force=True)
        gdp = self.tesselator.node('OUT').geometry().freeze()
        return gdp

    def create_tesselator(self):
        """Builds a SOP network for the tesselating geometry"""
        # A network is created instead of a chain of Verbs because currently
        # the Convert SOP doesn't exist in Verb form.
        sopnet = hou.node('/out').createNode('sopnet')

        py_node = sopnet.createNode('python', node_name='python', run_init_scripts=False)
        convert_node = sopnet.createNode('convert', node_name='to_polys', run_init_scripts=False)
        divide_node = sopnet.createNode('divide', node_name='triangulate', run_init_scripts=False)
        wrangler_node = sopnet.createNode('attribwrangle', node_name='cull_open',
                                          run_init_scripts=False)
        out_node = sopnet.createNode('output', node_name='OUT', run_init_scripts=False)

        py_node.setUnloadFlag(True)
        convert_node.setUnloadFlag(True)
        out_node.setDisplayFlag(True)
        out_node.setRenderFlag(True)

        py_node.parm('python').set(self._tesslate_py)

        convert_node.parm('lodu').set(1)
        convert_node.parm('lodv').set(1)

        # Remove any primitives that are not closed as pbrt can not handle them
        wrangler_node.parm('class').set('primitive')
        wrangler_node.parm('snippet').set('if (!primintrinsic(geoself(), "closed", @primnum)) '
                                          'removeprim(geoself(), @primnum, 1);')

        convert_node.setFirstInput(py_node)
        divide_node.setFirstInput(convert_node)
        wrangler_node.setFirstInput(divide_node)
        out_node.setFirstInput(wrangler_node)

        return sopnet

    def remove_tesselator(self):
        """Tear down the previously created tesselator network"""
        if self.tesselator is None:
            return
        self.tesselator.destroyCachedUserData('gdp')
        self.tesselator.destroy()
        self.tesselator = None
        return

# Module global to hold the overall state of the export
scene_state = PBRTState()
