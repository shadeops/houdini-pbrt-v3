from __future__ import print_function, division, absolute_import

from contextlib import contextmanager

import soho
import sohoglue

from PBRTplugins import PBRTParam

class SohoPBRT(soho.SohoParm):
    """Simple subclass of soho.SohoParm that adds to_pbrt() method"""

    def to_pbrt(self, pbrt_type=None):
        """Convert SohoParm to PBRTParam"""
        # bounds not supported
        # shader not supported
        if pbrt_type is None:
            to_pbrt_type = {'real' : 'float',
                            'fpreal' : 'float',
                            'int' : 'integer'}
            pbrt_type = to_pbrt_type.get(self.Type, self.Type)
        pbrt_name = self.Key
        return PBRTParam(pbrt_type, pbrt_name, self.Value)

# This is a replacement for soho.PropertyOverride
@contextmanager
def soho_override_block(options):
    """Context for overriding properties"""
    sohoglue.pushOverrides(options)
    yield
    sohoglue.popOverrides()
