import types
import collections

import hou
import soho

# TODO is this the best name/location for this?
# should some of this functionality be in _hou_parm_to_pbrt_param()
def pbrt_param_from_ref(parm, parm_value, parm_name=None):
    """Convert hou.ParmTuple into a PBRT string

    Optional parm_name for overridding the name of a parm,
    useful in cases where you have different parm signatures
    """
    if parm_name is None:
        parm_name = parm.name()

    parm_tmpl = parm.parmTemplate()
    parm_type = parm_tmpl.type()
    parm_scheme = parm_tmpl.namingScheme()

    # PBRT: bool
    if parm_type == hou.parmTemplateType.Toggle:
        pbrt_type = 'bool'
    # PBRT: string (menu)
    elif parm_type == hou.parmTemplateType.Menu:
        pbrt_type = 'string'
    # PBRT: string
    elif parm_type == hou.parmTemplateType.String:
        pbrt_type = 'string'
    # PBRT: integer
    elif parm_type == hou.parmTemplateType.Int:
        pbrt_type = 'integer'
    # PBRT: spectrum
    elif parm_scheme == hou.parmNamingScheme.RGBA:
        pbrt_type = 'rgb'
    # PBRT: point*/vector*/normal
    elif ( parm_type == hou.parmTemplateType.Float and
            'pbrt.type' in parm_tmpl.tags() ):
        pbrt_type = parm_tmpl.tags()['pbrt.type']
    # PBRT: float (sometimes a float is just a float)
    elif parm_type == hou.parmTemplateType.Float:
        pbrt_type = 'float'
    else:
        raise hou.ValueError('Can\'t convert %s to pbrt type' % (parm))

    return PBRTParam(pbrt_type, parm_name, parm_value)

def _hou_parm_to_pbrt_param(parm, parm_name=None):
    """Convert hou.ParmTuple into a PBRT string

    Optional parm_name for overridding the name of a parm,
    useful in cases where you have different parm signatures
    """
    if parm_name is None:
        parm_name = parm.name()

    # 9 types
    # integer, float, point2, vector2, point3, vector3, normal, spectrum,
    # bool, and string
    # Houdini has the concept of float arrays as well as float vectors
    # parm0, parm1, parm2 and parmx, parmy, parmz respectively
    # Unfortunately there isn't a way to differentiate between a
    # point* and a vector* in the UI, to do this we'll use a parm tag,
    # "pbrt.type"

    # Additionally there is an extra pbrt.type defined which is "space"
    # This parameter will not be output, but instead will cause
    # the referenced parm's space to declared

    # Spectrum is another special case in that its a rgb type, but if it
    # has an input of pbrt_spectrum type then extra options are available.

    parm_tmpl = parm.parmTemplate()
    parm_type = parm_tmpl.type()
    parm_scheme = parm_tmpl.namingScheme()
    # Assuming there will only be a single coshader "plugin"
    # per parameter.
    coshaders = parm.node().coshaderNodes(parm_name)
    if coshaders:
        coshader = coshaders[0]
    else:
        coshader = None
    #print parm, parm_type
    # PBRT: bool
    if parm_type == hou.parmTemplateType.Toggle:
        pbrt_type = 'bool'
        pbrt_value = parm.eval()
    # PBRT: string (menu)
    elif parm_type == hou.parmTemplateType.Menu:
        pbrt_type = 'string'
        pbrt_value = parm.evalAsStrings()
    # PBRT: string
    elif parm_type == hou.parmTemplateType.String:
        pbrt_type = 'string'
        pbrt_value = parm.evalAsStrings()
    # PBRT: integer
    elif parm_type == hou.parmTemplateType.Int:
        pbrt_type = 'integer'
        pbrt_value = parm.eval()
    # PBRT: spectrum
    elif parm_scheme == hou.parmNamingScheme.RGBA:
        if coshader is None:
            pbrt_type = 'rgb'
            pbrt_value = parm.eval()
        elif coshader.type().nameComponents()[2] == 'pbrt_spectrum':
            # FIXME, implement wrangle_spectrum
            pbrt_type, pbrt_value = wrangle_spectrum(coshader)
        else:
            pbrt_type = 'texture'
            pbrt_value = coshader.path()
    # PBRT: float texture
    elif ( parm_type == hou.parmTemplateType.Float and
            coshader is not None ):
        pbrt_type = 'texture'
        pbrt_value = coshader.path()
    # PBRT: point*/vector*/normal
    elif ( parm_type == hou.parmTemplateType.Float and
            'pbrt.type' in parm_tmpl.tags() ):
        pbrt_type = parm_tmpl.tags()['pbrt.type']
        pbrt_value = parm.eval()
    # PBRT: float (sometimes a float is just a float)
    elif parm_type == hou.parmTemplateType.Float:
        pbrt_type = 'float'
        pbrt_value = parm.eval()
    # PBRT: wut is dis?
    else:
        raise hou.ValueError('Can\'t convert %s to pbrt type' % (parm))

    return PBRTParam(pbrt_type, parm_name, pbrt_value)



class PBRTParam(object):

    # NOTE: There is a typo on the pbrt website with regards to the allowed
    #       types. It lists normal as a valid type and normal as an synonym
    #       currently according to core/parser.cpp only normal is supported
    #       and not normal. (Most likely a typo since internally the type is
    #       Normal3f
    #       http://www.pbrt.org/fileformat-v3.html#parameter-lists

    pbrt_types = ('texture', 'float', 'point2', 'vector2', 'point3', 'normal',
                  'integer', 'spectrum', 'rgb', 'xyz', 'blackbody', 'string',
                  'bool')
    type_synonyms = {'point' : 'point3',
                     'vector' : 'vector3',
                     'color' : 'rgb',
                     }

    def __init__(self, param_type, param_name, param_value):
        param_type = self.type_synonyms.get(param_type, param_type)
        if param_type not in self.pbrt_types:
            raise TypeError('%s not a known PBRT type' % param_type)
        self.type = param_type
        self.name = param_name
        self._value = param_value

    def __str__(self):
        if isinstance(self.value, types.GeneratorType):
            value_str = '...'
        else:
            if len(self.value) > 3:
                suffix = ' ...'
            else:
                suffix = ''
            value_str = '%s' % (' '.join([str(x) for x in self.value[0:3]]))
            value_str += suffix
        return '%s [ %s ]' % (self.type_name, value_str)

    def __hash__(self):
        return hash((self.type, self.name))

    def __eq__(self, other):
        if not isinstance(other, PBRTParam):
            raise TypeError('Can not compare non PBRTParam type')
        return (self.type == other.type and self.name == other.name)

    def __ne__(self, other):
        if not isinstance(other, PBRTParam):
            raise TypeError('Can not compare non PBRTParam type')
        return (self.type != other.type or self.name != other.name)

    @property
    def value(self):
        if isinstance(self._value, types.GeneratorType):
            v = self._value
        elif not isinstance(self._value, (list, tuple)):
            v = [self._value,]
        else:
            v = self._value[:]
        if self.type == 'bool':
            v = ( 'true' if (x and x!='false') else 'false' for x in v )
        return v

    @property
    def type_name(self):
        return '%s %s' % (self.type, self.name)

    def as_str(self):
        return soho.arrayToString('"%s" [ ' % self.type_name, self.value, ' ]')

    def print_str(self):
        return soho.printArray('"%s" [ ' % self.type_name, self.value, ' ]')

class ParamSet(collections.MutableSet):

    def __init__(self, iterable=None):
        self._data = set()
        if not iterable:
            return
        self |= iterable

    def __contains__(self, item):
        return item in self._data

    def __iter__(self):
        # TODO: Sort based on type/name?
        for v in self._data:
            yield v

    def __len__(self):
        return len(self._data)

    def __str__(self):
        return ' , '.join(str(x) for x in self)

    def add(self, param):
        self._data.add(param)

    def discard(self, param):
        self._data.discard(param)

    def replace(self, param):
        self.discard(param)
        self.add(param)

    def find_param(self, ptype, name):
        for p in self._data:
            if p.type == ptype and p.name == name:
                return p
        return None

    def update(self, other):
        for o in other:
            self.replace(o)

class BasePlugin(object):

    def __init__(self, node, ignore_defaults=True):
        if isinstance(node, hou.VopNode):
            self.node = node
        elif isinstance(node, basestring):
            self.node = hou.node(node)
        else:
            raise hou.TypeError('%s is unknown type' % node)
        self.ignore_defaults = ignore_defaults

    @property
    def plugin_class(self):
        # FIXME
        # This returns op:_auto_/{node.path()}
        # when the node has inputs. The PxrNodes do not have this issue
        # I'm not sure why that is the case but I suspect its due to the
        # shopclerk althought further experiments are needed.
        # For now we'll bruteforce it
        # return self.node.shaderName()
        return self.node.type().definition().sections()['FunctionName'].contents()

    @property
    def name(self):
        return self.node.path()

    def get_used_parms(self):
        parms = {}
        for parm_tup in self.node.parmTuples():
            parm_tags = parm_tup.parmTemplate().tags()
            parm_name = parm_tup.name()

            if 'pbrt.meta' in parm_tags:
                # Ignore meta parameters that are used to
                # control the UI
                continue

            if self.node.coshaderNodes(parm_name):
                # Instead of adding checks for this multiple
                # times, check once and then continue
                parms[parm_name] = parm_tup
                continue

            if parm_tup.isDisabled() or parm_tup.isHidden():
                continue

            if (parm_tup.isAtDefault() and
                self.ignore_defaults and
               'pbrt.force' not in parm_tags):
                # If the parm is at its default but has an input
                # then consider it used, otherwise skip it...
                # unless we have metadata to says force its output
                continue

            parms[parm_name] = parm_tup

        return parms

    @property
    def coord_sys(self):
        return None

    @property
    def paramset(self):
        params = ParamSet()
        hou_parms = self.get_used_parms()
        for parm_name in sorted(hou_parms):
            parm = hou_parms[parm_name]
            param = _hou_parm_to_pbrt_param(parm, parm_name)
            params.add(param)
        return params

class MaterialPlugin(BasePlugin):

    # Can be a Material or Texture or a Spectrum Helper
    # spectrum helpers will be ignored as they are just
    # improved interfaces for a parm
    def inputs(self):
        # should this return the parm name and the input
        # or just the input
        for input_node in self.node.inputs():
            if input_node is None:
                continue
            node_type = input_node.type().nameComponents()[2]
            if node_type == 'pbrt_spectrum':
                continue
            yield input_node.path()

    @property
    def output_type(self):
        return 'string type'

    @property
    def paramset(self):
        params = super(MaterialPlugin, self).paramset
        # Materials might have a bumpmap input
        # which doesn't exist as a parameter
        # TODO, another approach is to actually
        # add the parameter but always make it
        # invisible so it gets passed over
        bump_coshaders = self.node.coshaderNodes('bumpmap')
        if bump_coshaders:
            params.replace(PBRTParam('texture', 'bumpmap',
                                 bump_coshaders[0].path()))
        return params


class TexturePlugin(MaterialPlugin):

    def get_used_parms(self):
        # Special handling for Texture plugins as they have a signature parm

        # Start off with the base filtering, we can do this because
        # so far this filters away everything we don't care about.
        # (Parms belonging to the other signature are hidden)
        parms = super(TexturePlugin, self).get_used_parms()

        # If the signature is the default then it means
        # parms won't have a suffix so we are done.
        signature = self.node.currentSignatureName()
        if signature == 'default':
            return parms

        # Otherwise we need to strip off the suffix
        new_parms = {}
        for parm_name,parm in parms.iteritems():
            if parm_name == 'signature':
                continue
            # We could also check for name == texture_space
            if parm.parmTemplate().tags().get('pbrt.type') == 'space':
                continue
            # Foolproof way:
            # re.sub('_%s$' % signature, '', parm_name)
            # Easy way:
            new_parm_name = parm_name.rsplit('_',1)[0]
            new_parms[new_parm_name] = parm
        return new_parms

    @property
    def coord_sys(self):
        space_parm = self.node.parm('texture_space')
        if not space_parm:
            return None
        node = space_parm.evalAsNode()
        if not node:
            return None
        try:
            return node.worldTransform().asTuple()
        except AttributeError:
            return None

    @property
    def output_type(self):
        if self.node.currentSignatureName() == 'default':
            return 'float'
        return 'spectrum'
