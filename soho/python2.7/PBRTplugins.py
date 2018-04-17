import collections

import hou
import soho

def _hou_parm_to_pbrt_param(parm, parm_name=None):
    """Convert hou.ParmTuple into a PBRT string

    Optional parm_name for overridding the name of a parm,
    useful in cases where you have different parm signatures
    """
    if parm_name is None:
        parm_name = parm.name()

    # 9 types
    # integer, float, point2, vector2, point3, vector3, normal3, spectrum,
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
            pbrt_type, pbrt_value = wrangle_spectrum(coshader)
        else:
            pbrt_type = 'texture'
            pbrt_value = coshader.path()
    # PBRT: float texture
    elif ( parm_type == hou.parmTemplateType.Float and
            coshader is not None ):
        pbrt_type = 'texture'
        pbrt_value = coshader.path()
    # PBRT: point/vector/normal
    elif ( parm_type == hou.parmTemplateType.Float and
            'pbrt_type' in parm_tmpl.tags() ):
        pbrt_type = '%s%i' % ( parm_tmpl.tags()['pbrt_type'],
                               parm_tmpl.numComponents() )
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

    pbrt_types = ('texture', 'float', 'point2', 'vector2', 'point3', 'normal3',
                  'integer', 'spectrum', 'rgb', 'xyz', 'blackbody', 'string',
                  'bool')
    type_synonyms = {'point' : 'point3',
                     'normal' : 'normal3',
                     'vector' : 'vector3',
                     'color' : 'rgb',
                     }

    def __init__(self, param_type, param_name, param_value):
        param_type = self.type_synonyms.get(param_type, param_type)
        if param_type not in self.pbrt_types:
            raise hou.TypeError('%s not a known PBRT type' % param_type)
        self.type = param_type
        self.name = param_name
        self._value = param_value

    def __str__(self):
        if len(self.value) > 3:
            suffix = '... ]'
        else:
            suffix = ']'
        return '%s [ %s %s' % (self.type_name, ' '.join([str(x) for x in self.value[:3]]), suffix)

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
        if not isinstance(self._value, (list, tuple)):
            v = [self._value,]
        else:
            v = self._value[:]
        if self.type == 'bool':
            v = [ 'true' if (x and x!='false') else 'false' for x in v ]
        return v

    @property
    def type_name(self):
        return '%s %s' % (self.type, self.name)

    def as_str(self):
        return soho.arrayToString('"%s" [ ' % self.type_name, self.value, ' ]')

class ParamSet(collections.MutableSet):
    def __init__(self, iterable=None):
        self._data = {}
        if not iterable:
            return
        if not isinstance(iterable, PBRTParam):
            raise TypeError('Must be a PBRTParam type')
        for i in iterable:
            self._data[i.name] = i
    def __contains__(self, item):
        return item.name in self._data
    def __iter__(self):
        for k in sorted(self._data.keys()):
            yield self._data[k]
    def __len__(self):
        return len(self._data)
    def __getitem__(self,key):
        return self._data[key]
    def __str__(self):
        return ' , '.join(str(x) for x in self)
    def add(self, param):
        self._data[param.name] = param
    def discard(self, param):
        del self._data[param.name]

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
        return self.node.shaderName()

    @property
    def name(self):
        return self.node.path()

    @property
    def type(self):
        # Determine if this is needed
        # Another option is that the type is derived from
        # the shaderName() ie) texture/imagemap
        return node.type().nameComponents()[2].split('_')[1]

    def get_used_parms(self):
        parms = {}
        for parm_tup in self.node.parmTuples():
            if parm_tup.isDisabled() or parm_tup.isHidden():
                continue
            if 'pbrt.meta' in parm_tup.parmTemplate().tags():
                # Ignore meta parameters that are used to
                # control the UI
                continue
            parm_name = parm_tup.name()
            if ( not self.node.coshaderNodes(parm_name) and
                    (parm_tup.isAtDefault() and
                     self.ignore_defaults and
                     'pbrt.force' not in parm_tup.parmTemplate().tags())):
                # If the parm is at its default but has an input
                # then consider it used, otherwise skip it...
                # unless we have metadata to says force its output
                continue
            parms[parm_name] = parm_tup
        return parms

    @property
    def paramset(self):
        params = []
        params = ParamSet()
        hou_parms = self.get_used_parms()
        for parm_name in sorted(hou_parms):
            parm = hou_parms[parm_name]
            param = _hou_parm_to_pbrt_param(parm, parm_name)
            params.add(param)
        return params

class TexturePlugin(BasePlugin):

    def get_used_parms(self):
        # Special handling for Texture plugins as they have a signature parm

        # Start off with the base filtering, we can do this because
        # so far this filters away everything we don't care about.
        # (Parms belonging to the other signature are hidden)
        parms = super(BasePlugin, self).get_used_parms()

        # If the signature is the default then it means
        # parms won't have a suffix so we are done.
        signature = self.node.currentSignatureName()
        if signature == 'default':
            return parms

        # Otherwise we need to strip off the suffix
        new_parms = {}
        for parm_name,parm in parms.iteritems():
            if parm_name == 'signature':
                pass
            # Foolproof way:
            # re.sub('_%s$' % signature, '', parm_name)
            # Easy way:
            new_parm_name = parm_name.rsplit('_',1)[0]
            new_parms[new_parm_name] = parm
        return new_parms

    @property
    def output(self):
        if self.node.currentSignatureName() == 'default':
            return 'float'
        return 'spectrum'
