from __future__ import print_function, division, absolute_import

import re
import json
import types
import array
import collections

import hou
import soho


class HouParmException(Exception):
    pass


class PBRTParam(object):
    """Representation of a param in PBRT

    A PBRT param will hold the type, name and possibly values of a param in
    meant for passing to PBRT. PBRTparams can be compared with other PBRTparams
    but *only* their types and names are checked for equality NOT their values.
    This is done for easy use in ParamSets. ie) Is this param already defined
    in the ParamSet or not?

    This class is also responsible for serializing the data into a pbrt scene
    format. Values can be a POD, iterable or generator.

    Attributes:
        param_type (str): pbrt type name
        name (str): name of the param
        value (list/generator): Param's values
    """

    # NOTE: There is a typo on the pbrt website with regards to the allowed
    #       types. It lists normal as a valid type and normal as an synonym
    #       currently according to core/parser.cpp only normal is supported
    #       and not normal. (Most likely a typo since internally the type is
    #       Normal3f
    #       http://www.pbrt.org/fileformat-v3.html#parameter-lists

    pbrt_types = (
        "texture",
        "float",
        "point2",
        "vector2",
        "point3",
        "normal",
        "vector3",
        "integer",
        "spectrum",
        "rgb",
        "xyz",
        "blackbody",
        "string",
        "bool",
    )
    type_synonyms = {"point": "point3", "vector": "vector3", "color": "rgb"}
    spectrum_types = set(["color", "rgb", "blackbody", "xyz", "spectrum"])

    def __init__(self, param_type, param_name, param_value=None):
        """
        Args:
        param_type (str): PBRT param type
        param_name (str): Name of the param
        param_value (None, POD, list, generator): Value of the param (Optional)

        Raises:
            TypeError: If param_type does not match a known pbrt_type
        """
        param_type = self.type_synonyms.get(param_type, param_type)
        if param_type not in self.pbrt_types:
            raise TypeError("%s not a known PBRT type" % param_type)

        if param_type == "spectrum" and isinstance(param_value, basestring):
            # for convience these might either be a file path or an array
            # of wavelengths/values. Here we'll convert a string representation
            # of the array to an actual array if it
            try:
                param_value = eval(param_value, {}, {})
            except:  # noqa: E722
                # Be aggressive and catch anything
                pass

        if param_type in self.spectrum_types:
            self.type = "spectrum"
        else:
            self.type = param_type
        self.param_type = param_type
        self.name = param_name
        self._value = param_value if param_value is not None else []

    def __str__(self):
        if isinstance(self.value, types.GeneratorType):
            value_str = "..."
        else:
            if len(self.value) > 3:
                suffix = " ..."
            else:
                suffix = ""
            value_str = "%s" % (" ".join([str(x) for x in self.value[0:3]]))
            value_str += suffix
        return "%s [ %s ]" % (self.type_name, value_str)

    def __hash__(self):
        # We only hash on the type and name, not the value
        return hash((self.type, self.name))

    def __eq__(self, other):
        if not isinstance(other, PBRTParam):
            raise TypeError("Can not compare non PBRTParam type")
        return self.type == other.type and self.name == other.name

    def __ne__(self, other):
        if not isinstance(other, PBRTParam):
            raise TypeError("Can not compare non PBRTParam type")
        return self.type != other.type or self.name != other.name

    @property
    def value(self):
        """The value of the param, converted from python values to pbrt values"""
        if isinstance(self._value, types.GeneratorType):
            v = self._value
        elif not isinstance(self._value, (list, tuple, array.array)):
            v = [self._value]
        else:
            v = self._value[:]
        if self.type == "bool":
            v = ("true" if (x and x != "false") else "false" for x in v)
        return v

    @property
    def type_name(self):
        """The type and name of the param"""
        return "%s %s" % (self.param_type, self.name)

    def as_str(self):
        """Returns param as a string suitable for a pbrt scene file"""
        return soho.arrayToString('"%s" [ ' % self.type_name, self.value, " ]")

    def print_str(self):
        """Prints param as a string suitable for a pbrt scene file"""
        return soho.printArray('"%s" [ ' % self.type_name, self.value, " ]")


class ParamSet(collections.MutableSet):
    """Represents a collection of PBRTParams

    The behaviour is much like a set allowing for updating, removal and adding
    of PBRTParams.

    Set operations like
    paramset |= other_paramset
    are valid, in the case above the operation is similar to and add,
    not a replace.
    """

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
        return " , ".join(str(x) for x in self)

    def add(self, param):
        """Add a param if it does not already exist"""
        self._data.add(param)

    def discard(self, param):
        """Remove a param if it exists, no exception if it does not"""
        self._data.discard(param)

    def replace(self, param):
        """Remove a param then add the new one"""
        self.discard(param)
        self.add(param)

    def find_param(self, ptype, name):
        """Find a return a PBRTParam of ptype and name if in the ParamSet"""
        param_to_find = PBRTParam(ptype, name)
        for p in self._data:
            if p == param_to_find:
                return p
        return None

    def update(self, other):
        """Update (and replace) this ParamSet with another ParamSet"""
        if not other:
            return
        for o in other:
            self.replace(o)


def get_directive_from_nodetype(node_type):
    """Get the 'directive' of a Houdini PBRT VOP

    The directive will typically be something like 'texture', 'material', etc.
    These coorespond to the api calls. The type of directive the not represents
    is first searched for in the userInfo of the node's definition. If the
    userInfo does not contain the expected data then the type name of the node
    is parsed and derived from that. If that fails None is returned.

    An example of valid userInfo looks like -
    print hou.node('/mat/pbrt_material_plastic1').type().definition().userInfo()
    '{"dtype": "plastic", "directive": "material"}'
    """

    directive = None

    node_definition = node_type.definition()
    if node_definition is None:
        # PBRT nodes will always have a definition since they are HDAs.
        return None

    user_data_str = node_definition.userInfo()
    if user_data_str:
        user_data = json.loads(user_data_str)
        directive = user_data.get("directive")

    if directive:
        return directive.lower()

    typename_tokens = node_type.nameComponents()[2].lower().split("_")

    if typename_tokens[0] != "pbrt":
        return None

    try:
        if len(typename_tokens) == 2:
            directive = "soho_helper"
        elif len(typename_tokens) == 3:
            directive = typename_tokens[1]
    except IndexError:
        return None

    return directive


class BaseNode(object):
    """Base representation of a PBRT VOP node

    This node acts as a wrapper and translator from a standard Houdini VOP node
    to a PBRT call. It derives the directive type and paramset from the Houdini
    node.
    """

    override_pat = re.compile(
        "((?P<node>\w+)/)?" "(?P<parm>\w+)" "(:(?P<spectrum>\w+))?"  # noqa: W605
    )

    @staticmethod
    def from_node(node, ignore_defaults=True):
        """Factory method for creating *Node classes based on the input node"""
        if isinstance(node, basestring):
            node = hou.node(node)

        if isinstance(node, hou.VopNode):
            node = node
        else:
            return None

        directive = get_directive_from_nodetype(node.type())

        if directive is None:
            return None

        dtype = node.type().definition().sections()["FunctionName"].contents()

        if directive == "material":
            return MaterialNode(node, ignore_defaults)
        elif directive == "texture":
            return TextureNode(node, ignore_defaults)
        elif dtype == "pbrt_spectrum":
            return SpectrumNode(node)
        return BaseNode(node, ignore_defaults)

    def __init__(self, node, ignore_defaults=True):

        if isinstance(node, basestring):
            node = hou.node(node)

        if isinstance(node, hou.VopNode):
            self.node = node
        else:
            raise hou.TypeError("%s is unknown type" % node)

        # Since we rely on hidden and disabled states for which parms
        # to export, we need to ensure these are set
        self.node.updateParmStates()

        self.ignore_defaults = ignore_defaults
        self.directive = get_directive_from_nodetype(node.type())
        self.path_prefix = ""
        self.path_suffix = ""
        self.override_cache = {}

    @property
    def directive_type(self):
        # NOTE
        # return self.node.shaderName()
        #
        # The above returns op:_auto_/{node.path()}
        # when the node has inputs. The PxrNodes do not have this issue
        # I'm not sure why that is the case but I suspect its due to the
        # shopclerk althought further experiments are needed.
        # For now we'll brute force it
        return self.node.type().definition().sections()["FunctionName"].contents()

    @property
    def path(self):
        return self.node.path()

    @property
    def name(self):
        return self.node.name()

    @property
    def full_name(self):
        return "%s%s%s" % (self.path_prefix, self.path, self.path_suffix)

    @property
    def coord_sys(self):
        return None

    def get_used_parms(self):
        parms = {}
        for parm_tup in self.node.parmTuples():
            parm_tags = parm_tup.parmTemplate().tags()
            parm_name = parm_tup.name()

            if "pbrt.meta" in parm_tags:
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

            if (
                parm_tup.isAtDefault()
                and self.ignore_defaults
                and "pbrt.force" not in parm_tags
            ):
                # If the parm is at its default but has an input
                # then consider it used, otherwise skip it...
                # unless we have metadata to says force its output
                continue

            parms[parm_name] = parm_tup

        return parms

    @property
    def paramset(self):
        params = ParamSet()
        hou_parms = self.get_used_parms()
        for parm_name in sorted(hou_parms):
            parm = hou_parms[parm_name]
            # If we can't wrangle a parm type we'll skip it
            try:
                param = self._hou_parm_to_pbrt_param(parm, parm_name)
            except HouParmException:
                continue
            params.add(param)
        return params

    @property
    def type_and_paramset(self):
        return (self.directive_type, self.paramset)

    def pbrt_parm_name(self, name):
        return name

    def paramset_with_overrides(self, override_str):
        paramset = ParamSet(self.paramset)
        paramset.update(self.override_paramset(override_str))
        return paramset

    def override_paramset(self, override_str):
        """Get a paramset with overrides applied

        Args:
            override_str (str): A string with the overrides (material_override)

        Returns:
            ParamSet with matching overrides applied
        """

        paramset = ParamSet()
        if not override_str:
            return paramset

        override = eval(override_str, {}, {})
        if not override:
            return paramset

        for override_name in override:
            # The override can have a node_name/parm format which allows for point
            # instance overrides to override parms in a network.

            cached_override = self.override_cache.get(override_name, None)
            if cached_override is not None:
                # Hint to just skip
                if cached_override == -1:
                    continue
                if isinstance(cached_override, PBRTParam):
                    # textures which can't be overriden
                    paramset.add(cached_override)
                    continue
                pbrt_name, pbrt_type, tuple_names = cached_override
                if tuple_names:
                    value = [override[x] for x in tuple_names]
                else:
                    value = override[override_name]
                pbrt_param = PBRTParam(pbrt_type, pbrt_name, value)
                paramset.add(pbrt_param)
                continue

            override_match = self.override_pat.match(override_name)
            spectrum_type = override_match.group("spectrum")
            parm_name = override_match.group("parm")
            override_node = override_match.group("node")
            if override_node is not None and override_node != self.name:
                self.override_cache[override_name] = -1
                continue

            # There can be two style of "overrides" one is a straight parm override
            # which is similar to what Houdini does. The other style of override is
            # for the spectrum type parms. Since spectrum parms can be of different
            # types and the Material Overrides only support "rgb" we are limited
            # in the types of spectrum overrides we can do. To work around this we'll
            # support a different style, override_parm:spectrum_type. If the parm name
            # ends in one of the "rgb/color" types then we'll handle it differently.
            # TODO add a comment as to what the value would look like

            # NOTE: The material SOP will use a parm style dictionary if there
            #       parm name matches exactly
            #       ie) if there is a color parm you will get
            #       {'colorb':0.372511,'colorg':0.642467,'colorr':0.632117,}
            #       But if the parm name doesn't match (which we are allowing
            #       for you will get something like this -
            #       {'colora':(0.632117,0.642467,0.372511),}

            # Once we have a parm name, we need to determine what "style" it is.
            # Whether its a hou.ParmTuple or hou.Parm style.
            tuple_names = tuple()
            parm_tuple = self.node.parmTuple(parm_name)
            if parm_tuple is None:
                # We couldn't find a tuple of that name, so let's try a parm
                parm = self.node.parm(parm_name)
                if parm is None:
                    # Nope, not valid either, let's move along
                    self.override_cache[override_name] = -1
                    continue
                # if its a parm but not a parmtuple it must be a split.
                parm_tuple = parm.tuple()
                # we need to "combine" these and process them all at once and
                # then skip any other occurances. The skipping is handled by
                # the overall caching mechanism. self.override_cache
                tuple_names = tuple([x.name() for x in parm_tuple])

            # This is for wrangling parm names of texture nodes due to having a
            # signature parm.
            pbrt_parm_name = self.pbrt_parm_name(parm_tuple.name())

            if spectrum_type is None and tuple_names:
                # This is a "traditional" override, no spectrum or node name prefix
                value = [override[x] for x in tuple_names]
                pbrt_param = self._hou_parm_to_pbrt_param(
                    parm_tuple, pbrt_parm_name, value
                )
            elif spectrum_type in ("spectrum", "xyz", "blackbody"):
                pbrt_param = PBRTParam(
                    spectrum_type, pbrt_parm_name, override[override_name]
                )
            elif not tuple_names:
                pbrt_param = self._hou_parm_to_pbrt_param(
                    parm_tuple, pbrt_parm_name, override[override_name]
                )
            else:
                raise ValueError("Unable to wrangle override name: %s" % override_name)

            paramset.add(pbrt_param)

            # From here to the end of the loop is to allow for caching

            if pbrt_param.type == "texture":
                self.override_cache[override_name] = pbrt_param
                continue

            # we are making an assumption a split parm will never be a spectrum
            # or have a node prefix. The Material SOP doesn't allow for it as well.
            for name in tuple_names:
                # The -1 means "continue"
                self.override_cache[name] = -1
            # Sanity check
            if tuple_names and override_name not in tuple_names:
                raise ValueError(
                    "Override name: %s, not valid for a parmTuple" % override_name
                )
            # override_name must match one of the tuple_names
            self.override_cache[override_name] = (
                pbrt_param.name,
                pbrt_param.param_type,
                tuple_names,
            )
        return paramset

    def _hou_parm_to_pbrt_param(self, parm, parm_name=None, value_override=None):
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
        # Assuming there will only be a single coshader "node"
        # per parameter.
        coshaders = parm.node().coshaderNodes(parm_name)
        if coshaders:
            coshader = BaseNode.from_node(coshaders[0])
            coshader.path_prefix = self.path_prefix
            coshader.path_suffix = self.path_suffix
        else:
            coshader = None
        # PBRT: bool
        if parm_type == hou.parmTemplateType.Toggle:
            pbrt_type = "bool"
            pbrt_value = parm.eval()
        # PBRT: string (menu)
        elif parm_type == hou.parmTemplateType.Menu:
            pbrt_type = "string"
            pbrt_value = parm.evalAsStrings()
        # PBRT: string
        elif parm_type == hou.parmTemplateType.String:
            pbrt_type = "string"
            pbrt_value = parm.evalAsStrings()
        # PBRT: integer
        elif parm_type == hou.parmTemplateType.Int:
            pbrt_type = "integer"
            pbrt_value = parm.eval()
        # PBRT: spectrum
        elif parm_scheme == hou.parmNamingScheme.RGBA:
            if coshader is None:
                pbrt_type = "rgb"
                pbrt_value = parm.eval()
            elif coshader.directive_type == "pbrt_spectrum":
                # If the coshader is a spectrum node then it will
                # only have one param in the paramset
                spectrum_parm = coshader.paramset.pop()
                pbrt_type = spectrum_parm.param_type
                pbrt_value = spectrum_parm.value
            elif coshader.directive == "texture":
                pbrt_type = "texture"
                pbrt_value = coshader.full_name
            else:
                raise HouParmException("Can't convert %s to pbrt type" % (parm))
        # PBRT: float texture
        elif (
            parm_type == hou.parmTemplateType.Float
            and coshader is not None
            and coshader.directive == "texture"
        ):
            pbrt_type = "texture"
            pbrt_value = coshader.full_name
        # PBRT: point*/vector*/normal
        elif (
            parm_type == hou.parmTemplateType.Float and "pbrt.type" in parm_tmpl.tags()
        ):
            pbrt_type = parm_tmpl.tags()["pbrt.type"]
            pbrt_value = parm.eval()
        # PBRT: float (sometimes a float is just a float)
        elif parm_type == hou.parmTemplateType.Float:
            pbrt_type = "float"
            pbrt_value = parm.eval()
        # PBRT: wut is dis?
        else:
            raise HouParmException("Can't convert %s to pbrt type" % (parm))

        # If there is a coshader we can't override the value as there is a connection
        if value_override is not None and coshader is None:
            pbrt_value = value_override

        return PBRTParam(pbrt_type, parm_name, pbrt_value)


class SpectrumNode(BaseNode):
    @property
    def paramset(self):
        params = ParamSet()

        spectrum_type = self.node.parm("type").evalAsString()
        values = self.node.parmTuple(spectrum_type).eval()
        if spectrum_type == "ramp":
            ramp = values[0]
            samples = self.node.parm("ramp_samples").eval()
            ramp_range = self.node.parmTuple("ramp_range").eval()
            sample_step = 1.0 / samples
            values = [
                (
                    hou.hmath.fit01(sample_step * x, ramp_range[0], ramp_range[1]),
                    ramp.lookup(sample_step * x),
                )
                for x in xrange(samples + 1)
            ]
        elif spectrum_type == "spd":
            # TODO: Houdini bug? key/value pairs return None
            #       when evaluated as a parmTuple, so we'll
            #       reevaluate as a parm
            spd = self.node.parm("spd").eval()
            values = []
            for spec in sorted(spd, key=lambda x: float(x)):
                values.append(float(spec))
                values.append(float(spd[spec]))
        if spectrum_type in ("file", "spd", "ramp"):
            spectrum_type = "spectrum"
        params.add(PBRTParam(spectrum_type, None, values))
        return params

    @property
    def get_used_parms(self):
        return None


class MaterialNode(BaseNode):

    # Can be a Material or Texture or a Spectrum Helper
    # spectrum helpers will be ignored as they are just
    # improved interfaces for a parm
    def inputs(self):
        # should this return the parm name and the input
        # or just the input
        for input_node in self.node.inputs():
            if input_node is None:
                continue
            directive = get_directive_from_nodetype(input_node.type())
            if directive not in ("material", "texture"):
                continue
            yield input_node.path()

    @property
    def output_type(self):
        return "string type"

    @property
    def paramset(self):
        params = super(MaterialNode, self).paramset

        # Materials might inputs that don't exist as parms
        # (bumpmap float textures, and materials for example)
        input_names = self.node.inputNames()
        input_types = self.node.inputDataTypes()

        for idx, input_node in enumerate(self.node.inputs()):
            if input_node is None:
                continue
            input_name = input_names[idx]
            if self.node.parmTuple(input_name) is not None:
                continue
            coshaders = self.node.coshaderNodes(input_name)
            if not coshaders:
                continue
            pbrt_parm_type = "texture"
            if input_types[idx] == "struct_PBRTMaterial":
                pbrt_parm_type = "string"
            coshader = BaseNode.from_node(coshaders[0])
            coshader.path_prefix = self.path_prefix
            coshader.path_suffix = self.path_suffix
            params.replace(PBRTParam(pbrt_parm_type, input_name, coshader.full_name))

        return params


class TextureNode(MaterialNode):
    def get_used_parms(self):
        # Special handling for Texture nodes as they have a signature parm

        # Start off with the base filtering, we can do this because
        # so far this filters away everything we don't care about.
        # (Parms belonging to the other signature are hidden)
        parms = super(TextureNode, self).get_used_parms()

        # If the signature is the default then it means
        # parms won't have a suffix so we are done.
        signature = self.node.currentSignatureName()
        if signature == "default":
            return parms

        # Otherwise we need to strip off the suffix
        new_parms = {}
        for parm_name, parm in parms.iteritems():
            if parm_name == "signature":
                continue
            # We could also check for name == texture_space
            if parm.parmTemplate().tags().get("pbrt.type") == "space":
                continue
            # Foolproof way:
            # re.sub('_%s$' % signature, '', parm_name)
            # Easy way:
            new_parm_name = parm_name.rsplit("_", 1)[0]
            new_parms[new_parm_name] = parm
        return new_parms

    def pbrt_parm_name(self, name):
        signature = self.node.currentSignatureName()
        if signature != "default":
            return name.rsplit("_", 1)[0]
        return name

    @property
    def coord_sys(self):
        space_parm = self.node.parm("texture_space")
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
        # We assume that the first output is always representative
        # of the node's output_type
        if self.node.outputDataTypes()[0] == "float":
            return "float"
        elif self.node.outputDataTypes()[0] == "struct_PBRTSpectrum":
            return "spectrum"
        return None
