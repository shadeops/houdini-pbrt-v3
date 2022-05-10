:warning: *Archived Repo* :warning: 
===========================

With the release of [pbrt-v4](https://github.com/mmp/pbrt-v4) and [houdini-pbrt-v4](https://github.com/shadeops/houdini-pbrt-v4) this exporter is no longer being maintained. Additionally when developing the exporter for houdini-pbrt-v4 various bugs were found with this release that were not backported. If there is a compelling reason to continue to support pbrt-v3 please log an issue under the houdini-pbrt-v4 repo.


Houdini Exporter for pbrt Version 3
===================================

**houdini-pbrt-v3** for [SideFX's Software Houdini](https://www.sidefx.com) is a scene exporter for the
[pbrt-v3 renderer](https://pbrt.org/). The goal is to provide complete coverage for the features avaiable within pbrt-v3 through
an interface familiar with Houdini user.

Motivation
----------
Support the amazing project that is pbrt and indirectly provide more test cases for the renderer.
More selfishly a common use case in a vfx production environment is to add functionality to an existing 3rd party rendering engine.
Often the internals of that engine are closed making it difficult to experiment with new algorithms.
With pbrt the development of new approaches can be developed within a well documented and open system.
By providing an exporter for Houdini to pbrt makes translating larger production scenes into a test environment much easier.

Design Goals
------------
* Full coverage of all pbrt features
* Standard (simple) interfaces for common use, with easy to use hooks for full functionality.
* Simple to read code with comments to help explain the [SOHO System](https://www.sidefx.com/docs/hdk/_h_d_k__s_o_h_o.html)

Installation
------------
For now clone the repo in anywhere within the HOUDINI_PATH. More details in the wiki.

Usage
-----
See the Wiki for documentation on usage.
