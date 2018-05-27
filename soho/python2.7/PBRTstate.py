from __future__ import print_function, division, absolute_import

import hou
import soho

class PBRTState(object):

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

    def init_state(self):
        state_parms = {
            'rop'     : soho.SohoParm('object:name',  'string', key='rop'),
            'hip'     : soho.SohoParm('$HIP',         'string', key='hip'),
            'hipname' : soho.SohoParm('$HIPNAME',     'string', key='hipname'),
            'ver'     : soho.SohoParm('state:houdiniversion', 'string', ["9.0"], False, key='ver'),
            'now'     : soho.SohoParm('state:time',  'real', [0], False,  key='now'),
            'fps'     : soho.SohoParm('state:fps',   'real', [24], False, key='fps'),
        }
        rop = soho.getOutputDriver()
        parms = soho.evaluate(state_parms, None, rop)
        for parm in parms:
            setattr(self, parm, parms[parm].Value[0])
        if not self.fps:
            self.fps = 24.0
        self.inv_fps = 1.0/self.fps

    def __enter__(self):
        self.reset()
        self.init_state()
        self.create_tesselator()

    def __exit__(self, *args):
        self.reset()

    def reset(self):
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

    def tesselate_geo(self, geo, compute_N=False):
        if self.tesselator is None:
            raise TypeError('Tesselator is None')
        self.tesselator.setCachedUserData('gdp', geo)
        self.tesselator.node('python').cook(force=True)
        gdp = self.tesselator.node('triangulate').geometry().freeze()
        return gdp

    def create_tesselator(self):
        sopnet = hou.node('/out').createNode('sopnet')

        py_node = sopnet.createNode('python', node_name='python', run_init_scripts=False)
        convert_node = sopnet.createNode('convert', node_name='to_polys', run_init_scripts=False)
        divide_node = sopnet.createNode('divide', node_name='triangulate', run_init_scripts=False)

        py_node.setUnloadFlag(True)
        convert_node.setUnloadFlag(True)
        divide_node.setDisplayFlag(True)

        py_node.parm('python').set(self._tesslate_py)

        convert_node.parm('lodu').set(1)
        convert_node.parm('lodv').set(1)

        convert_node.setFirstInput(py_node)
        divide_node.setFirstInput(convert_node)

        self.tesselator = sopnet

    def remove_tesselator(self):
        if self.tesselator is None:
            return
        self.tesselator.destroyCachedUserData('gdp')
        self.tesselator.destroy()
        self.tesselator = None

scene_state = PBRTState()
