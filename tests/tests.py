import os
import shutil
import filecmp
import unittest

import hou

CLEANUP_FILES = False

# Disable headers in pbrt scene files as they have time info
os.environ["SOHO_PBRT_NO_HEADER"] = "1"


def build_checker_material():
    matte = hou.node("/mat").createNode("pbrt_material_matte", run_init_scripts=False)
    checks = hou.node("/mat").createNode(
        "pbrt_texture_checkerboard", run_init_scripts=False
    )
    checks.parm("signature").set("s")
    checks.parmTuple("tex1_s").set([0.1, 0.1, 0.1])
    checks.parmTuple("tex2_s").set([0.375, 0.5, 0.5])
    checks.parm("uscale").set(10)
    checks.parm("vscale").set(10)
    matte.setNamedInput("Kd", checks, "output")
    return matte


def clear_mat():
    for child in hou.node("/mat").children():
        child.destroy()


def build_envlight():
    env = hou.node("/obj").createNode("envlight")
    env.parm("light_intensity").set(0.1)
    return env


def build_spherelight():
    light = hou.node("/obj").createNode("hlight")
    light.parm("light_type").set("sphere")
    light.parmTuple("areasize").set([1, 1])
    light.parmTuple("t").set([3, 3, 3])
    light.parm("light_intensity").set(50)


def build_cam():
    cam = hou.node("/obj").createNode("cam")
    cam.parmTuple("t").set([0, 1, 5])
    cam.parmTuple("r").set([-12, 0, 0])
    cam.parmTuple("res").set([320, 240])
    return cam


def build_zcam():
    cam = hou.node("/obj").createNode("cam")
    cam.parmTuple("t").set([0, 0, 10])
    cam.parmTuple("res").set([320, 240])
    return cam


def build_geo():
    geo = hou.node("/obj").createNode("geo")
    for child in geo.children():
        child.destroy()
    return geo


def build_instance():
    instance = hou.node("/obj").createNode("instance")
    for child in instance.children():
        child.destroy()
    return instance


def build_ground():
    ground = hou.node("/obj").createNode("geo")
    for child in ground.children():
        child.destroy()
    ground.createNode("grid")
    return ground


def build_rop(filename=None, diskfile=None):
    rop = hou.node("/out").createNode("pbrt")
    ptg = rop.parmTemplateGroup()
    precision = hou.properties.parmTemplate("pbrt-v3", "soho_precision")
    almostzero = hou.properties.parmTemplate("pbrt-v3", "soho_almostzero")
    ptg.append(precision)
    ptg.append(almostzero)
    rop.setParmTemplateGroup(ptg)
    rop.parm("soho_precision").set(2)
    rop.parm("soho_almostzero").set(0.001)
    rop.parm("soho_outputmode").set(1)
    if diskfile:
        rop.parm("soho_diskfile").set(diskfile)
    if filename:
        rop.parm("filename").set(filename)
    return rop


def build_archive(diskfile=None):
    rop = hou.node("/out").createNode("pbrtarchive")
    ptg = rop.parmTemplateGroup()
    precision = hou.properties.parmTemplate("pbrt-v3", "soho_precision")
    almostzero = hou.properties.parmTemplate("pbrt-v3", "soho_almostzero")
    ptg.append(precision)
    ptg.append(almostzero)
    rop.setParmTemplateGroup(ptg)
    rop.parm("soho_precision").set(2)
    rop.parm("soho_almostzero").set(0.001)
    if diskfile:
        rop.parm("soho_diskfile").set(diskfile)
    return rop


class TestParamBase(unittest.TestCase):

    # In order to import the Soho related PBRT modules we need to
    # invoke a render first. While hacky this avoids having to setup
    # custom python path.
    @classmethod
    def setUpClass(cls):
        cls.cam = build_cam()
        cls.rop = build_rop()
        cls.rop.parm("filename").set("/dev/null")

    @classmethod
    def tearDownClass(cls):
        hou.hipFile.clear(suppress_save_prompt=True)
        if CLEANUP_FILES:
            shutil.rmtree("tests/tmp")

    def setUp(self):
        self.rop.render()
        from PBRTnodes import PBRTParam

        self.PBRTParam = PBRTParam

    def test_invalid_type(self):
        with self.assertRaises(TypeError):
            self.PBRTParam("cake", "my_name", "foo")

    def test_invalid_equal(self):
        a = self.PBRTParam("float", "my_name", 1)
        with self.assertRaises(TypeError):
            a == "dog"

    def test_invalid_notequal(self):
        a = self.PBRTParam("float", "my_name", 1)
        with self.assertRaises(TypeError):
            a != "dog"

    def test_rgb_is_spectrum(self):
        param = self.PBRTParam("rgb", "my_name", [1, 2, 3])
        self.assertEqual(param.type, "spectrum")

    def test_rgb_string_is_equal(self):
        param = self.PBRTParam("rgb", "my_name", [1, 2, 3])
        self.assertEqual(str(param), "rgb my_name [ 1 2 3 ]")

    def test_rgb_string_is_notequal(self):
        param = self.PBRTParam("rgb", "my_name", [1, 2, 3])
        self.assertNotEqual(str(param), "spectrum my_name [ 0 0 0 ]")

    def test_rgb_is_equal(self):
        a = self.PBRTParam("rgb", "my_name", [1, 2, 3])
        b = self.PBRTParam("xyz", "my_name", [0, 1, 0])
        self.assertEqual(a, b)

    def test_rgb_is_notequal(self):
        a = self.PBRTParam("rgb", "my_name", [1, 2, 3])
        b = self.PBRTParam("float", "my_name", [0])
        self.assertNotEqual(a, b)

    def test_shorten_str(self):
        param = self.PBRTParam("spectrum", "my_name", [400, 1, 500, 1, 600, 1])
        self.assertEqual(str(param), "spectrum my_name [ 400 1 500 ... ]")

    def test_shorten_generator(self):
        gen = (x for x in [400, 1, 500, 1, 600, 1])
        param = self.PBRTParam("spectrum", "my_name", gen)
        self.assertEqual(str(param), "spectrum my_name [ ... ]")


class TestBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build_cam()

    @classmethod
    def tearDownClass(cls):
        hou.hipFile.clear(suppress_save_prompt=True)
        if CLEANUP_FILES:
            shutil.rmtree("tests/tmp")

    @property
    def testfile(self):
        return "tests/tmp/%s.pbrt" % "/".join(self.id().split(".")[1:])

    @property
    def basefile(self):
        return "tests/scenes/%s.pbrt" % "/".join(self.id().split(".")[1:])

    @property
    def name(self):
        return self.id().split(".")[-1]


class TestROP(TestBase):
    def setUp(self):
        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

    def tearDown(self):
        self.rop.destroy()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_filter_gaussian(self):
        self.rop.parm("filter").set("gaussian")
        self.rop.parm("gauss_alpha").set(3)
        self.compare_scene()

    def test_filter_mitchell(self):
        self.rop.parm("filter").set("mitchell")
        self.rop.parm("mitchell_B").set(0.3)
        self.rop.parm("mitchell_C").set(0.3)
        self.compare_scene()

    def test_filter_sinc(self):
        self.rop.parm("filter").set("sinc")
        self.rop.parm("sinc_tau").set(4)
        self.compare_scene()

    def test_sampler_stratified(self):
        self.rop.parm("sampler").set("stratified")
        self.compare_scene()

    def test_accelerator_kdtree(self):
        self.rop.parm("accelerator").set("kdtree")
        self.compare_scene()


class TestArchive(TestBase):
    def setUp(self):
        self.geo = build_ground()
        self.rop = build_archive(diskfile=self.testfile)

    def tearDown(self):
        self.geo.destroy()
        self.rop.destroy()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_singlegeo(self):
        self.rop.parm("vobject").set(self.geo.path())
        self.compare_scene()


class TestLights(TestBase):
    @classmethod
    def setUpClass(cls):
        build_cam()
        build_ground()

    def setUp(self):
        self.light = hou.node("/obj").createNode("hlight")
        self.light.parm("ty").set(1.5)
        self.light.parm("rx").set(-90)
        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

    def tearDown(self):
        self.light.destroy()
        self.rop.destroy()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_pointlight(self):
        self.light.parm("light_type").set("point")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_spotlight(self):
        self.light.parm("light_type").set("point")
        self.light.parm("light_intensity").set(5)
        self.light.parm("coneenable").set(True)
        self.compare_scene()

    def test_projectorlight(self):
        self.light.parm("light_type").set("point")
        self.light.parm("light_intensity").set(5)
        self.light.parm("coneenable").set(True)
        self.light.parm("projmap").set("../../maps/tex.exr")
        self.compare_scene()

    def test_goniometriclight(self):
        self.light.parm("light_type").set("point")
        self.light.parm("light_intensity").set(5)
        self.light.parm("areamap").set("../../maps/tex.exr")
        self.compare_scene()

    def test_distantlight(self):
        self.light.parm("light_type").set("distant")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_spherelight(self):
        self.light.parm("light_type").set("sphere")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_spherelight_rotated(self):
        self.light.parm("light_type").set("sphere")
        self.light.parm("light_intensity").set(5)
        self.light.parmTuple("r").set([15, 30, 45])
        self.compare_scene()

    def test_tubelight(self):
        self.light.parm("light_type").set("tube")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_disklight(self):
        self.light.parm("light_type").set("disk")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_gridlight(self):
        self.light.parm("light_type").set("grid")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_sunlight(self):
        self.light.parm("light_type").set("sun")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()


class TestGeoLight(TestBase):
    @classmethod
    def setUpClass(cls):
        build_cam()
        build_ground()

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def setUp(self):
        self.light = hou.node("/obj").createNode("hlight")
        self.light.parm("ty").set(1.5)
        self.light.parm("rx").set(-90)
        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)
        self.box = hou.node("/obj").createNode("geo")
        self.box.createNode("box")
        self.box.setDisplayFlag(False)

    def tearDown(self):
        self.box.destroy()
        self.light.destroy()
        self.rop.destroy()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def test_geolight(self):
        self.light.parm("light_type").set("geo")
        self.light.parm("areageometry").set(self.box.path())
        self.light.parm("light_intensity").set(5)
        self.compare_scene()

    def test_geolight_no_geo(self):
        self.light.parm("light_type").set("geo")
        self.light.parm("areageometry").set("")
        self.light.parm("light_intensity").set(5)
        self.compare_scene()


class TestGeo(TestBase):
    @classmethod
    def setUpClass(cls):
        build_cam()
        build_envlight()
        build_spherelight()

    @classmethod
    def tearDownClass(cls):
        hou.hipFile.clear(suppress_save_prompt=True)
        if CLEANUP_FILES:
            shutil.rmtree("tests/tmp")


class TestInstance(TestGeo):
    def setUp(self):
        self.geo1 = build_geo()
        self.geo1.createNode("sphere")
        self.geo1.setDisplayFlag(False)
        self.geo2 = build_geo()
        self.geo2.createNode("sphere")
        self.geo2.setDisplayFlag(False)
        self.instance = build_instance()
        self.mat = build_checker_material()

        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

        self.geo1.parm("shop_materialpath").set(self.mat.path())
        self.geo2.parm("shop_materialpath").set(self.mat.path())
        self.extras = []

    def tearDown(self):
        self.geo1.destroy()
        self.geo2.destroy()
        self.instance.destroy()
        self.rop.destroy()
        clear_mat()
        for extra in self.extras:
            extra.destroy()
        self.extras[:] = []
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_instance(self):
        add_sop = self.instance.createNode("add")
        add_sop.parm("usept0").set(True)
        self.instance.parm("instancepath").set(self.geo1.path())
        self.compare_scene()

    def test_full_instance(self):
        add_sop = self.instance.createNode("add")
        add_sop.parm("usept0").set(True)
        self.instance.parm("instancepath").set(self.geo1.path())
        self.instance.parm("ptinstance").set("on")
        self.compare_scene()

    def test_fast_instance(self):
        add_sop = self.instance.createNode("add")
        add_sop.parm("usept0").set(True)
        self.instance.parm("instancepath").set(self.geo1.path())
        self.instance.parm("ptinstance").set("fast")
        self.compare_scene()

    def test_full_pt_instance(self):
        add_sop = self.instance.createNode("add")
        add_sop.parm("points").set(2)
        add_sop.parm("usept0").set(True)
        add_sop.parm("usept1").set(True)
        add_sop.parmTuple("pt1").set([2, 0, 0])
        attrib1_sop = self.instance.createNode("attribcreate")
        attrib1_sop.setFirstInput(add_sop)
        attrib1_sop.parm("group").set("0")
        attrib1_sop.parm("name1").set("instance")
        attrib1_sop.parm("type1").set("index")
        attrib1_sop.parm("string1").set(self.geo1.path())
        attrib2_sop = self.instance.createNode("attribcreate")
        attrib2_sop.setFirstInput(attrib1_sop)
        attrib2_sop.parm("group").set("1")
        attrib2_sop.parm("name1").set("instance")
        attrib2_sop.parm("type1").set("index")
        attrib2_sop.parm("string1").set(self.geo2.path())
        attrib2_sop.setRenderFlag(True)
        self.instance.parm("instancepath").set(self.geo1.path())
        self.instance.parm("ptinstance").set("on")
        self.compare_scene()

    def test_fast_pt_instance(self):
        add_sop = self.instance.createNode("add")
        add_sop.parm("points").set(2)
        add_sop.parm("usept0").set(True)
        add_sop.parm("usept1").set(True)
        add_sop.parmTuple("pt1").set([2, 0, 0])
        attrib1_sop = self.instance.createNode("attribcreate")
        attrib1_sop.setFirstInput(add_sop)
        attrib1_sop.parm("group").set("0")
        attrib1_sop.parm("name1").set("instance")
        attrib1_sop.parm("type1").set("index")
        attrib1_sop.parm("string1").set(self.geo1.path())
        attrib2_sop = self.instance.createNode("attribcreate")
        attrib2_sop.setFirstInput(attrib1_sop)
        attrib2_sop.parm("group").set("1")
        attrib2_sop.parm("name1").set("instance")
        attrib2_sop.parm("type1").set("index")
        attrib2_sop.parm("string1").set(self.geo2.path())
        attrib2_sop.setRenderFlag(True)
        self.instance.parm("instancepath").set(self.geo1.path())
        self.instance.parm("ptinstance").set("fast")
        self.compare_scene()


class TestMediums(TestGeo):
    def setUp(self):
        self.geo = build_geo()
        self.geo.createNode("sphere")
        ptg = self.geo.parmTemplateGroup()
        interior = hou.properties.parmTemplate("pbrt-v3", "pbrt_interior")
        exterior = hou.properties.parmTemplate("pbrt-v3", "pbrt_exterior")
        ptg.append(interior)
        ptg.append(exterior)
        self.geo.setParmTemplateGroup(ptg)
        self.none = hou.node("/mat").createNode("pbrt_material_none")
        self.medium = hou.node("/mat").createNode("pbrt_medium")

        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

    def tearDown(self):
        self.geo.destroy()
        self.rop.destroy()
        clear_mat()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_interior(self):
        self.geo.parm("pbrt_interior").set(self.medium.path())
        self.geo.parm("pbrt_exterior").set("")
        self.geo.parm("shop_materialpath").set(self.none.path())
        self.compare_scene()


class TestProperties(TestGeo):
    def setUp(self):
        self.geo = build_geo()
        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

    def tearDown(self):
        self.geo.destroy()
        self.rop.destroy()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_include(self):
        ptg = self.geo.parmTemplateGroup()
        parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_include")
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm("pbrt_include").set("test.pbrt")
        self.compare_scene()


class TestMaterials(TestGeo):
    def setUp(self):
        self.geo = build_geo()
        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

    def tearDown(self):
        self.geo.destroy()
        self.rop.destroy()
        clear_mat()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_mix_material(self):
        matte1 = hou.node("/mat").createNode("pbrt_material_matte")
        matte2 = hou.node("/mat").createNode("pbrt_material_matte")
        mix = hou.node("/mat").createNode("pbrt_material_mix")
        mix.setNamedInput("namedmaterial1", matte1, "material")
        mix.setNamedInput("namedmaterial2", matte2, "material")
        self.geo.parm("shop_materialpath").set(mix.path())
        self.compare_scene()

    def test_bumpmap_material(self):
        matte = hou.node("/mat").createNode("pbrt_material_matte")
        bump = hou.node("/mat").createNode("pbrt_texture_wrinkled")
        matte.setNamedInput("bumpmap", bump, "output")
        self.geo.parm("shop_materialpath").set(matte.path())
        self.compare_scene()

    def test_checker_material(self):
        space = hou.node("/obj").createNode("null")
        space.parmTuple("t").set([1, 2, 3])
        space.parmTuple("s").set([5, 10, 20])
        matte = hou.node("/mat").createNode("pbrt_material_matte")
        checks = hou.node("/mat").createNode("pbrt_texture_checkerboard")
        checks.parm("signature").set("s")
        checks.parm("dimension").set(3)
        checks.parm("texture_space").set(space.path())
        matte.setNamedInput("Kd", checks, "output")

        self.geo.parm("shop_materialpath").set(matte.path())
        self.compare_scene()


class TestSpectrum(TestGeo):
    def setUp(self):
        self.geo = build_geo()
        material = hou.node("/mat").createNode("pbrt_material_matte")
        spectrum = hou.node("/mat").createNode("pbrt_spectrum")
        material.setNamedInput("Kd", spectrum, "output")
        self.spectrum = spectrum

        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

        self.geo.parm("shop_materialpath").set(material.path())
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
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_rgb(self):
        self.spectrum.parmTuple("rgb").set([0.25, 0.5, 0.75])
        self.spectrum.parm("type").set("rgb")
        self.compare_scene()

    def test_xyz(self):
        self.spectrum.parmTuple("xyz").set([0.25, 0.5, 0.75])
        self.spectrum.parm("type").set("xyz")
        self.compare_scene()

    def test_spd(self):
        self.spectrum.parm("spd").set({"400": "1", "500": "0.5", "600": "0.25"})
        self.spectrum.parm("type").set("spd")
        self.compare_scene()

    def test_file(self):
        self.spectrum.parm("file").set("./file.spd")
        self.spectrum.parm("type").set("file")
        self.compare_scene()

    def test_ramp(self):
        ramp = hou.Ramp([hou.rampBasis.Linear] * 3, (0.0, 0.5, 1.0), (0.25, 1.0, 0.5))
        self.spectrum.parm("ramp").set(ramp)
        self.spectrum.parm("type").set("ramp")
        self.compare_scene()

    def test_blackbody(self):
        self.spectrum.parmTuple("blackbody").set([5000, 0.5])
        self.spectrum.parm("type").set("blackbody")
        self.compare_scene()


class TestMotionBlur(TestBase):
    @classmethod
    def setUpClass(cls):
        build_envlight()

    @classmethod
    def tearDownClass(cls):
        hou.hipFile.clear(suppress_save_prompt=True)
        if CLEANUP_FILES:
            shutil.rmtree("tests/tmp")

    def setUp(self):
        self.cam = build_zcam()
        self.geo = build_geo()
        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

    def tearDown(self):
        self.geo.destroy()
        self.cam.destroy()
        self.rop.destroy()
        if CLEANUP_FILES:
            os.remove(self.testfile)

    def compare_scene(self):
        self.rop.render()
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_obj_mb(self):
        self.geo.parm("tx").setExpression("$FF-1")
        self.rop.parm("allowmotionblur").set(True)
        self.compare_scene()

    def test_cam_mb(self):
        self.cam.parm("tx").setExpression("$FF-1")
        self.rop.parm("allowmotionblur").set(True)
        self.compare_scene()

    def test_motion_window(self):
        self.geo.parm("tx").setExpression("$FF-1")
        self.rop.parm("allowmotionblur").set(True)
        ptg = self.cam.parmTemplateGroup()
        parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_motionwindow")
        ptg.append(parm)
        self.cam.setParmTemplateGroup(ptg)
        self.cam.parmTuple("pbrt_motionwindow").set([0.25, 0.75])
        self.compare_scene()


class TestShapes(TestGeo):
    def setUp(self):
        self.geo = build_geo()
        self.mat = build_checker_material()

        exr = "%s.exr" % self.name
        self.rop = build_rop(filename=exr, diskfile=self.testfile)

        self.geo.parm("shop_materialpath").set(self.mat.path())
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
        self.assertTrue(filecmp.cmp(self.testfile, self.basefile))

    def test_sphere(self):
        self.geo.createNode("sphere")
        self.compare_scene()

    def test_sphere_xformed(self):
        sphere = self.geo.createNode("sphere")
        sphere.parmTuple("rad").set([0.5, 0.25, 0.75])
        xform = self.geo.createNode("xform")
        xform.setFirstInput(sphere)
        xform.parmTuple("t").set([0.1, 0.2, 0.3])
        xform.parmTuple("r").set([30, 45, 60])
        xform.setRenderFlag(True)
        self.compare_scene()

    def test_circle(self):
        self.geo.createNode("circle")
        self.compare_scene()

    def test_cylinder(self):
        self.geo.createNode("tube")
        self.compare_scene()

    def test_cone(self):
        tube = self.geo.createNode("tube")
        tube.parm("rad1").set(0)
        self.compare_scene()

    def test_cone_caps(self):
        tube = self.geo.createNode("tube")
        tube.parm("rad1").set(0)
        tube.parm("cap").set(True)
        self.compare_scene()

    def test_unsupported_tube(self):
        tube = self.geo.createNode("tube")
        tube.parm("rad1").set(0.5)
        self.compare_scene()

    def test_cylinder_caps(self):
        tube = self.geo.createNode("tube")
        tube.parm("cap").set(True)
        self.compare_scene()

    def test_trianglemesh(self):
        self.geo.createNode("box")
        self.compare_scene()

    def test_trianglemesh_vtxN(self):
        box = self.geo.createNode("box")
        box.parm("vertexnormals").set(True)
        self.compare_scene()

    def test_trianglemesh_ptN(self):
        box = self.geo.createNode("box")
        normal = self.geo.createNode("normal")
        normal.parm("type").set(0)
        normal.setRenderFlag(True)
        normal.setFirstInput(box)
        self.compare_scene()

    def test_trianglemesh_noauto_ptN(self):
        self.geo.createNode("box")
        ptg = self.geo.parmTemplateGroup()
        parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_computeN")
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm("pbrt_computeN").set(False)
        self.compare_scene()

    def test_trianglemesh_vtxN_vtxUV(self):
        box = self.geo.createNode("box")
        box.parm("vertexnormals").set(True)
        uvtex = self.geo.createNode("texture")
        uvtex.parm("type").set("polar")
        uvtex.setRenderFlag(True)
        uvtex.setFirstInput(box)
        self.compare_scene()

    def test_trianglemesh_vtxN_ptUV(self):
        box = self.geo.createNode("box")
        box.parm("vertexnormals").set(True)
        uvtex = self.geo.createNode("texture")
        uvtex.parm("type").set("polar")
        uvtex.parm("coord").set("point")
        uvtex.setRenderFlag(True)
        uvtex.setFirstInput(box)
        self.compare_scene()

    def test_loopsubdiv(self):
        self.geo.createNode("box")
        ptg = self.geo.parmTemplateGroup()
        parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_rendersubd")
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm("pbrt_rendersubd").set(True)
        self.compare_scene()

    def test_loopsubdiv_level_1(self):
        self.geo.createNode("box")
        ptg = self.geo.parmTemplateGroup()
        subd_parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_rendersubd")
        level_parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_subdlevels")
        ptg.append(subd_parm)
        ptg.append(level_parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm("pbrt_rendersubd").set(True)
        self.geo.parm("pbrt_subdlevels").set(1)
        self.compare_scene()

    def test_nurbs(self):
        box = self.geo.createNode("box")
        box.parm("type").set("nurbs")
        self.compare_scene()

    def test_nurbs_wrap(self):
        torus = self.geo.createNode("torus")
        torus.parm("type").set("nurbs")
        torus.parm("orderu").set(3)
        torus.parm("orderv").set(3)
        self.compare_scene()

    def test_curves(self):
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        convert = self.geo.createNode("convert")
        convert.setFirstInput(fur)
        convert.parm("totype").set("bezCurve")
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_vtxwidth(self):
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        wrangler = self.geo.createNode("attribwrangle")
        wrangler.parm("class").set("vertex")
        wrangler.parm("snippet").set("@width = fit(@ptnum%5,0,4,0.1,0.01);")
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode("convert")
        convert.setFirstInput(wrangler)
        convert.parm("totype").set("bezCurve")
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_ptwidth(self):
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        wrangler = self.geo.createNode("attribwrangle")
        wrangler.parm("class").set("point")
        wrangler.parm("snippet").set("@width = fit(@ptnum%5,0,4,0.1,0.01);")
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode("convert")
        convert.setFirstInput(wrangler)
        convert.parm("totype").set("bezCurve")
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_bspline(self):
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        fur.setRenderFlag(True)
        self.compare_scene()

    def test_curves_primwidth(self):
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        wrangler = self.geo.createNode("attribwrangle")
        wrangler.parm("class").set("primitive")
        wrangler.parm("snippet").set("@width = fit01(@primnum/10.0, 0.05, 0.1);")
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode("convert")
        convert.setFirstInput(wrangler)
        convert.parm("totype").set("bezCurve")
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_primcurvetype(self):
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        wrangler = self.geo.createNode("attribwrangle")
        wrangler.parm("class").set("primitive")
        wrangler.parm("snippet").set(
            'if (@primnum%3 == 0) s@curvetype = "ribbon";\n'
            'if (@primnum%3 == 1) s@curvetype = "cylinder";\n'
            'if (@primnum%3 == 2) s@curvetype = "flat";'
        )
        wrangler.setFirstInput(fur)
        convert = self.geo.createNode("convert")
        convert.setFirstInput(wrangler)
        convert.parm("totype").set("bezCurve")
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_curves_curvetype(self):
        parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_curvetype")
        ptg = self.geo.parmTemplateGroup()
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm("pbrt_curvetype").set("ribbon")
        grid = self.geo.createNode("grid")
        grid.parmTuple("size").set([2, 2])
        fur = self.geo.createNode("fur")
        fur.setFirstInput(grid)
        fur.parm("density").set(10)
        fur.parm("length").set(1)
        convert = self.geo.createNode("convert")
        convert.setFirstInput(fur)
        convert.parm("totype").set("bezCurve")
        convert.setRenderFlag(True)
        self.compare_scene()

    def test_heightfield(self):
        hf = self.geo.createNode("heightfield")
        hf.parm("gridspacing").set(0.05)
        hf.parmTuple("size").set([3, 3])
        hf_n = self.geo.createNode("heightfield_noise")
        hf_n.setFirstInput(hf)
        hf_n.parm("amp").set(1)
        hf_n.parm("elementsize").set(0.5)
        hf_n.setRenderFlag(True)
        self.compare_scene()

    def test_volume(self):
        volume = self.geo.createNode("volume")
        volume.parmTuple("size").set([10, 10, 10])
        wrangle = self.geo.createNode("volumewrangle")
        wrangle.parm("snippet").set("@density = floor(@P.x+0.5);")
        wrangle.setFirstInput(volume)
        wrangle.setRenderFlag(True)
        self.rop.parm("integrator").set("volpath")
        self.compare_scene()

    def test_volume_vdb(self):
        volume = self.geo.createNode("volume")
        volume.parmTuple("size").set([10, 10, 10])
        wrangle = self.geo.createNode("volumewrangle")
        wrangle.parm("snippet").set("@density = floor(@P.x+0.5);")
        wrangle.setFirstInput(volume)
        convertvdb = self.geo.createNode("convertvdb")
        convertvdb.setFirstInput(wrangle)
        convertvdb.parm("conversion").set("vdb")
        convertvdb.setRenderFlag(True)
        self.rop.parm("integrator").set("volpath")
        self.compare_scene()

    def test_tesselated(self):
        self.geo.createNode("metaball")
        self.compare_scene()

    def test_geo_materials(self):
        disney = hou.node("/mat").createNode(
            "pbrt_material_disney", run_init_scripts=False
        )
        box = self.geo.createNode("box")
        material = self.geo.createNode("material")
        material.parm("shop_materialpath1").set(disney.path())
        material.setFirstInput(box)
        material.setRenderFlag(True)
        self.compare_scene()

    def test_geo_material_overrides(self):
        disney = hou.node("/mat").createNode(
            "pbrt_material_disney", run_init_scripts=False
        )
        box = self.geo.createNode("box")
        material = self.geo.createNode("material")
        material.parm("shop_materialpath1").set(disney.path())
        material.parm("num_local1").set(1)
        material.parm("local1_name1").set("color")
        material.parm("local1_type1").set("color")
        material.parmTuple("local1_cval1").set([0.9, 0, 0])
        material.setFirstInput(box)
        material.setRenderFlag(True)
        self.compare_scene()

    def test_geo_material_overrides_spectrum_xyz(self):
        disney = hou.node("/mat").createNode(
            "pbrt_material_disney", run_init_scripts=False
        )
        box = self.geo.createNode("box")
        material = self.geo.createNode("material")
        material.parm("shop_materialpath1").set(disney.path())
        material.parm("num_local1").set(1)
        material.parm("local1_name1").set("color:xyz")
        material.parm("local1_type1").set("vector3")
        material.parmTuple("local1_vval1").set([0.9, 0.5, 0.1, 0.0])
        material.setFirstInput(box)
        material.setRenderFlag(True)
        self.compare_scene()

    def test_geo_material_overrides_spectrum_file(self):
        disney = hou.node("/mat").createNode(
            "pbrt_material_disney", run_init_scripts=False
        )
        box = self.geo.createNode("box")
        material = self.geo.createNode("material")
        material.parm("shop_materialpath1").set(disney.path())
        material.parm("num_local1").set(1)
        material.parm("local1_name1").set("color:spectrum")
        material.parm("local1_type1").set("string")
        material.parmTuple("local1_sval1").set(["myfile.spd"])
        material.setFirstInput(box)
        material.setRenderFlag(True)
        self.compare_scene()

    def test_geo_material_overrides_spectrum_spd(self):
        disney = hou.node("/mat").createNode(
            "pbrt_material_disney", run_init_scripts=False
        )
        box = self.geo.createNode("box")
        material = self.geo.createNode("material")
        material.parm("shop_materialpath1").set(disney.path())
        material.parm("num_local1").set(1)
        material.parm("local1_name1").set("color:spectrum")
        material.parm("local1_type1").set("string")
        material.parmTuple("local1_sval1").set(["[400, 0.5, 500, 1, 600, 0.5]"])
        material.setFirstInput(box)
        material.setRenderFlag(True)
        self.compare_scene()

    def test_geo_ignore_materials(self):
        parm = hou.properties.parmTemplate("pbrt-v3", "pbrt_ignorematerials")
        ptg = self.geo.parmTemplateGroup()
        ptg.append(parm)
        self.geo.setParmTemplateGroup(ptg)
        self.geo.parm("pbrt_ignorematerials").set(True)
        disney = hou.node("/mat").createNode(
            "pbrt_material_disney", run_init_scripts=False
        )
        box = self.geo.createNode("box")
        material = self.geo.createNode("material")
        material.parm("shop_materialpath1").set(disney.path())
        material.setFirstInput(box)
        material.setRenderFlag(True)
        self.compare_scene()


if __name__ == "__main__":
    unittest.main()
