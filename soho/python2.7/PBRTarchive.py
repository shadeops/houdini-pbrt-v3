from __future__ import print_function, division, absolute_import

import os

import hou
import soho
from soho import SohoParm

# Houdini does not reload modules at each render, so when doing dev work it
# can be a pain to have to manually load modules, by setting this environment
# variable all the modules will be reloaded.
if "SOHO_PBRT_DEV" in os.environ:  # noqa # pragma: no coverage
    import PBRTapi

    reload(PBRTapi)
    import PBRTstate

    reload(PBRTstate)
    import PBRTnodes

    reload(PBRTnodes)
    import PBRTsoho

    reload(PBRTsoho)
    import PBRTinstancing

    reload(PBRTinstancing)
    import PBRTgeo

    reload(PBRTgeo)
    import PBRTwranglers

    reload(PBRTwranglers)
    import PBRTscene

    reload(PBRTscene)

import PBRTscene
from PBRTstate import scene_state


def soho_render():
    control_parms = {
        # The time at which the scene is being rendered
        "now": SohoParm("state:time", "real", [0], False, key="now")
    }

    parms = soho.evaluate(control_parms)

    now = parms["now"].Value[0]
    camera = None

    options = {}
    if not soho.initialize(now, camera, options):
        soho.error("Unable to initialize rendering module with given camera")

    object_selection = {
        # Candidate object selection
        "vobject": SohoParm("vobject", "string", ["*"], False),
        "forceobject": SohoParm("forceobject", "string", [""], False),
        "excludeobject": SohoParm("excludeobject", "string", [""], False),
    }

    objparms = soho.evaluate(object_selection, now)

    stdobject = objparms["vobject"].Value[0]
    forceobject = objparms["forceobject"].Value[0]
    excludeobject = objparms["excludeobject"].Value[0]

    # First, we add objects based on their display flags or dimmer values
    soho.addObjects(
        now, stdobject, "", "", True, geo_parm="vobject", light_parm="", fog_parm=""
    )
    soho.addObjects(
        now,
        forceobject,
        "",
        "",
        False,
        geo_parm="forceobject",
        light_parm="",
        fog_parm="",
    )
    soho.removeObjects(
        now, excludeobject, "", "", geo_parm="excludeobject", light_parm="", fog_parm=""
    )

    # Lock off the objects we've selected
    soho.lockObjects(now)

    with hou.undos.disabler(), scene_state:
        if "SOHO_PBRT_DEV" in os.environ:  # pragma: no coverage
            import cProfile

            pr = cProfile.Profile()
            pr.enable()
            try:
                PBRTscene.archive(now)
            finally:
                pr.disable()
                pr.dump_stats("hou-prbtarchive.stats")
        else:
            PBRTscene.archive(now)
    return


if __name__ in ("__builtin__", "__main__"):
    soho_render()
