import os
import sys
import shutil
import filecmp
import unittest

import hou

CLEANUP_FILES = False

# Disable headers in pbrt scene files as they have time info
os.environ['SOHO_PBRT_NO_HEADER'] = '1'

def build_checker_material():
    matte = hou.node('/mat').createNode('pbrt_material_matte',
                                        run_init_scripts=False)
    checks = hou.node('/mat').createNode('pbrt_texture_checkerboard',
                                         run_init_scripts=False)
    checks.parm('signature').set('s')
    checks.parmTuple('tex1_s').set([0.1, 0.1, 0.1])
    checks.parmTuple('tex2_s').set([0.375, 0.5, 0.5])
    checks.parm('uscale').set(10)
    checks.parm('vscale').set(10)
    matte.setNamedInput('Kd', checks, 'output')
    return matte

def clear_mat():
    for child in hou.node('/mat').children():
        child.destroy()

def build_envlight():
    env = hou.node('/obj').createNode('envlight')
    env.parm('light_intensity').set(0.5)
    return env

def build_cam():
    cam = hou.node('/obj').createNode('cam')
    cam.parmTuple('t').set([0,1,5])
    cam.parmTuple('r').set([-12,0,0])
    cam.parmTuple('res').set([320,240])
    return cam

def build_geo():
    geo = hou.node('/obj').createNode('geo')
    for child in geo.children():
        child.destroy()
    return geo

def build_rop(filename=None, diskfile=None):
    rop = hou.node('/out').createNode('pbrt')
    rop.parm('soho_outputmode').set(1)
    if diskfile:
        rop.parm('soho_diskfile').set(diskfile)
    if filename:
        rop.parm('filename').set(filename)
    return rop

def build_scene():
    cam = build_cam()
    env = build_envlight()
    matte = build_checker_material()

    geo = hou.node('/obj').createNode('geo')
    geo.parm('shop_materialpath').set(matte.path())

class TestGeo(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        build_cam()
        build_envlight()

    @classmethod
    def tearDownClass(cls):
        hou.hipFile.clear(suppress_save_prompt=True)
        if CLEANUP_FILES:
            shutil.rmtree('tests/tmp')

    @property
    def testfile(self):
        return 'tests/tmp/%s.pbrt' % '/'.join(self.id().split('.')[1:])

    @property
    def basefile(self):
        return 'tests/scenes/%s.pbrt' % '/'.join(self.id().split('.')[1:])

    @property
    def name(self):
        return self.id().split('.')[-1]

class TestSphere(TestGeo):

    def setUp(self):
        self.geo = build_geo()
        self.mat = build_checker_material()

        exr = '%s.exr' % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

        self.geo.parm('shop_materialpath').set(self.mat.path())

    def tearDown(self):
        self.geo.destroy()
        self.rop.destroy()
        clear_mat()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def test_sphere(self):
        sphere = self.geo.createNode('sphere')
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))
    def test_sphere_xformed(self):
        sphere = self.geo.createNode('sphere')
        sphere.parmTuple('rad').set([0.5, 0.25, 0.75])
        xform =  self.geo.createNode('xform')
        xform.setFirstInput(sphere)
        xform.parmTuple('t').set([0.1, 0.2, 0.3])
        xform.parmTuple('r').set([30, 45, 60])
        xform.setRenderFlag(True)
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))

    def test_circle(self):
        circle = self.geo.createNode('circle')
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))

    def test_cylinder(self):
        tube = self.geo.createNode('tube')
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))

    def test_cone(self):
        tube = self.geo.createNode('tube')
        tube.parm('rad1').set(0)
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))

    def test_cylinder_caps(self):
        tube = self.geo.createNode('tube')
        tube.parm('cap').set(True)
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))

if __name__ == '__main__':
    unittest.main()

