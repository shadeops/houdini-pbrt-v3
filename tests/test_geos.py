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
    env.parm('light_intensity').set(0.1)
    return env

def build_spherelight():
    light = hou.node('/obj').createNode('hlight')
    light.parm('light_type').set('sphere')
    light.parmTuple('areasize').set([1, 1])
    light.parmTuple('t').set([3, 3, 3])
    light.parm('light_intensity').set(50)

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

def build_ground():
    ground = hou.node('/obj').createNode('geo')
    for child in geo.children():
        child.destroy()
    ground.createNode('grid')
    return ground

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
        build_spherelight()

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

class TestShapes(TestGeo):

    def setUp(self):
        self.geo = build_geo()
        self.mat = build_checker_material()

        exr = '%s.exr' % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

        self.geo.parm('shop_materialpath').set(self.mat.path())
        self.extras = []

    def tearDown(self):
        self.geo.destroy()
        self.rop.destroy()
        clear_mat()
        for extra in self.extras:
            extra.destroy()
        self.extras[:] = []
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile,
                                    self.basefile))

    def test_sphere(self):
        sphere = self.geo.createNode('sphere')
        self.compare_scene()

    def test_sphere_xformed(self):
        sphere = self.geo.createNode('sphere')
        sphere.parmTuple('rad').set([0.5, 0.25, 0.75])
        xform =  self.geo.createNode('xform')
        xform.setFirstInput(sphere)
        xform.parmTuple('t').set([0.1, 0.2, 0.3])
        xform.parmTuple('r').set([30, 45, 60])
        xform.setRenderFlag(True)
        self.compare_scene()

    def test_circle(self):
        circle = self.geo.createNode('circle')
        self.compare_scene()

    def test_cylinder(self):
        tube = self.geo.createNode('tube')
        self.compare_scene()

    def test_cone(self):
        tube = self.geo.createNode('tube')
        tube.parm('rad1').set(0)
        self.compare_scene()

    def test_cone_caps(self):
        tube = self.geo.createNode('tube')
        tube.parm('rad1').set(0)
        tube.parm('cap').set(True)
        self.compare_scene()

    def test_unsupported_tube(self):
        tube = self.geo.createNode('tube')
        tube.parm('rad1').set(0.5)
        self.compare_scene()

    def test_cylinder_caps(self):
        tube = self.geo.createNode('tube')
        tube.parm('cap').set(True)
        self.compare_scene()

    def test_trianglemesh(self):
        box = self.geo.createNode('box')
        self.compare_scene()

    def test_trianglemesh_vtxN(self):
        box = self.geo.createNode('box')
        box.parm('vertexnormals').set(True)
        self.compare_scene()

    def test_trianglemesh_ptN(self):
        box = self.geo.createNode('box')
        normal = self.geo.createNode('normal')
        normal.parm('type').set(0)
        normal.setRenderFlag(True)
        normal.setFirstInput(box)
        self.compare_scene()

    def test_trianglemesh_noauto_ptN(self):
        box = self.geo.createNode('box')
        ptg = self.geo.parmTemplateGroup()
        parm = hou.properties.parmTemplate('pbrt-v3','pbrt_computeN')
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm('pbrt_computeN').set(False)
        self.compare_scene()

    def test_trianglemesh_vtxN_vtxUV(self):
        box = self.geo.createNode('box')
        box.parm('vertexnormals').set(True)
        uvtex = self.geo.createNode('texture')
        uvtex.parm('type').set('polar')
        uvtex.setRenderFlag(True)
        uvtex.setFirstInput(box)
        self.compare_scene()

    def test_trianglemesh_vtxN_ptUV(self):
        box = self.geo.createNode('box')
        box.parm('vertexnormals').set(True)
        uvtex = self.geo.createNode('texture')
        uvtex.parm('type').set('polar')
        uvtex.parm('coord').set('point')
        uvtex.setRenderFlag(True)
        uvtex.setFirstInput(box)
        self.compare_scene()

    def test_loopsubdiv(self):
        box = self.geo.createNode('box')
        ptg = self.geo.parmTemplateGroup()
        parm = hou.properties.parmTemplate('pbrt-v3','pbrt_rendersubd')
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm('pbrt_rendersubd').set(True)
        self.compare_scene()

    def test_loopsubdiv_level_1(self):
        box = self.geo.createNode('box')
        ptg = self.geo.parmTemplateGroup()
        subd_parm = hou.properties.parmTemplate('pbrt-v3','pbrt_rendersubd')
        level_parm = hou.properties.parmTemplate('pbrt-v3','pbrt_subdlevels')
        ptg.append(subd_parm)
        ptg.append(level_parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm('pbrt_rendersubd').set(True)
        self.geo.parm('pbrt_subdlevels').set(1)
        self.compare_scene()

    def test_nurbs(self):
        box = self.geo.createNode('box')
        box.parm('type').set('nurbs')
        self.compare_scene()

    def test_nurbs_wrap(self):
        torus = self.geo.createNode('torus')
        torus.parm('type').set('nurbs')
        torus.parm('orderu').set(3)
        torus.parm('orderv').set(3)
        self.compare_scene()

    def test_curves(self):
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        convert = self.geo.createNode('convert')
        convert.setFirstInput(fur)
        convert.parm('totype').set('bezCurve')
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_vtxwidth(self):
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        wrangler = self.geo.createNode('attribwrangle')
        wrangler.parm('class').set('vertex')
        wrangler.parm('snippet').set('@width = fit(@ptnum%5,0,4,0.1,0.01);')
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode('convert')
        convert.setFirstInput(wrangler)
        convert.parm('totype').set('bezCurve')
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_ptwidth(self):
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        wrangler = self.geo.createNode('attribwrangle')
        wrangler.parm('class').set('point')
        wrangler.parm('snippet').set('@width = fit(@ptnum%5,0,4,0.1,0.01);')
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode('convert')
        convert.setFirstInput(wrangler)
        convert.parm('totype').set('bezCurve')
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_bspline(self):
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        fur.setRenderFlag(True)
        self.compare_scene()

    def test_curves_primwidth(self):
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        wrangler = self.geo.createNode('attribwrangle')
        wrangler.parm('class').set('primitive')
        wrangler.parm('snippet').set('@width = fit01(@primnum/10.0, 0.05, 0.1);')
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode('convert')
        convert.setFirstInput(wrangler)
        convert.parm('totype').set('bezCurve')
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_primcurvetype(self):
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        wrangler = self.geo.createNode('attribwrangle')
        wrangler.parm('class').set('primitive')
        wrangler.parm('snippet').set('if (@primnum%3 == 0) s@curvetype = "ribbon";\n'
                                     'if (@primnum%3 == 1) s@curvetype = "cylinder";\n'
                                     'if (@primnum%3 == 2) s@curvetype = "flat";')
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode('convert')
        convert.setFirstInput(wrangler)
        convert.parm('totype').set('bezCurve')
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_curvetype(self):
        parm = hou.properties.parmTemplate('pbrt-v3','pbrt_curvetype')
        ptg = self.geo.parmTemplateGroup()
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm('pbrt_curvetype').set('ribbon')
        grid = self.geo.createNode('grid')
        grid.parmTuple('size').set([2, 2])
        fur = self.geo.createNode('fur')
        fur.setFirstInput(grid)
        fur.parm('density').set(10)
        fur.parm('length').set(1)
        convert = self.geo.createNode('convert')
        convert.setFirstInput(fur)
        convert.parm('totype').set('bezCurve')
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_heightfield(self):
        hf = self.geo.createNode('heightfield')
        hf.parm('gridspacing').set(0.05)
        hf.parmTuple('size').set([3, 3])
        hf_n = self.geo.createNode('heightfield_noise')
        hf_n.setFirstInput(hf)
        hf_n.parm('amp').set(1)
        hf_n.parm('elementsize').set(0.5)
        hf_n.setRenderFlag(True)
        self.compare_scene()

if __name__ == '__main__':
    unittest.main()

