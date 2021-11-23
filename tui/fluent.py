#native imports
from abc import ABC,abstractmethod,abstractstaticmethod
import os
from typing import OrderedDict, Type, Union
import os
import subprocess
import numpy as np 

#package imports
from ..fluentio.disk import SerializableClass
from ..tui.util import _surface_construction_arg_validator
from ..fluentio.classes import SurfaceIntegralFile

"""
Author: Michael Lanahan
Date Created: 08.05.2021
Last Edit: 11.23.2021

The purpose of this file is provide python class interfaces to TUI commands in 
the command line or batch mode fluent software. The hope is that this will make 
the batch submission of jobs more intelligble & easier to create for use on the 
PACE computing cluster @ GT

Huge bug on 09.10.2021 - 
all of the global variabels cannot be ported with the classes for caching
this will require further research to see if serializing globals from a particular file is allowed/
a good idea.
"""

WARNINGS = True
LINE_BREAK = '\n'
EXIT_CHAR = 'q' + LINE_BREAK
FLUENT_INIT_STATEMENT = 'fluent 3ddp -t{} < {} > {}'
SURFACE_INTEGRAL_FILE_DELIM = '-'
SURFACE_INTEGRAL_EXT = '.srp'

ALLOWABLE_SOLVERS = ['pressure-based']
ALLOWABLE_VISCOUS_MODELS = ['ke-standard','kw-standard','ke-realizable','ke-rng']
ALLOWABLE_MODELS = ['energy','viscous'] 
ALLOWABLE_MODELS += ['viscous/' + vm for vm in ALLOWABLE_VISCOUS_MODELS]
ALLOWABLE_BOUNDARY_TYPES = ['mass-flow-inlet','pressure-outlet','wall']

ALLOWABLE_DISCRITIZATION_SCHEMES = ['density','epsilon','k','mom','pressure','temperature']
ALLOWABLE_DISCRITIZATION_ORDERS = {'First Order Upwind':0,
                                   'Second Order Upwind':1,
                                   'Power Law': 2,
                                   'Central Differencing':3,
                                   'QUICK':4,
                                   'Standard':10,
                                   'Linear':11,
                                   'Second Order':12,
                                   'Body Force Weighted':13,
                                   'PRESTO!': 14,
                                   'Continuity Based':15,}

ALLOWABLE_VARIABLE_RELAXATION = ['body-force','epsilon','temperature','density', 'k', 'turb-viscosity']
ALLOWABLE_RELAXATION = {'courant number':200,
                        'momentum':0.75,
                        'pressure':0.75}


WINDOWS_FLUENT_INIT_STATEMENT = 'fluent {} -t{} -g -i {} -o {}'
FLUENT_INPUT_NAME = 'input.fluent'
FLUENT_OUTPUT_NAME = 'output.fluent'
LINE_BREAK = '\n'
EXIT_CHAR = 'q' + LINE_BREAK
EXIT_STATEMENT = 'exit'

class Initializer:

    """
    representation of the initializer object in Fluent
    """
    
    _prefix = 'solve/initialize/'
    ALLOWABLE_INITIALIZER_TYPES = ['hyb-initialization','initialize-flow']
    def __init__(self,init_type = 'hyb-initialization'):

        if init_type not in self.ALLOWABLE_INITIALIZER_TYPES:
            raise ValueError('initializer must be one of: {}'.format(self.ALLOWABLE_INITIALIZER_TYPES))
        
        self.__init_type = init_type

    @property
    def init_type(self):
        return self.__init_type
    
    def __str__(self):
        return self._prefix + self.init_type

class Relaxation(ABC):

    def __init__(self,variable: str,
                      value: float,
                      *args,**kwargs) -> None:
        
        if isinstance(variable,str) and (isinstance(value,int) or isinstance(value,float)):
            self._check_allowable_variables(variable,value)
            variable = [variable]
            value = [value]

        elif isinstance(variable,list) and isinstance(value,list):
            if len(variable) != len(value):
                raise AttributeError('lists of variables and values must be the same length')
            else:
                for var,val in zip(variable,value):
                    self._check_allowable_variables(var,val)

        else:
            raise ValueError('cannot make relaxation from variable: {} and value: {}'.format(variable,value))
                
        self.__var_value_dict = dict(zip(variable,value))

    @abstractstaticmethod
    def _check_allowable_variables(variable: str,
                                    value: float):
        pass

    @classmethod
    def from_dict(cls,
                  input_dict: dict):

        vars = []
        vals = []
        for var,val in input_dict.items():
            vars.append(var)
            vals.append(val)
        
        return cls(vars,vals)

    @property
    def var_value_dict(self):
        return self.__var_value_dict
    
    @var_value_dict.setter
    def var_value_dict(self,vvd):
        self.__var_value_dict = vvd

    def format_relaxation(self):
        txt = self._prefix + LINE_BREAK
        for variable,value in self.var_value_dict.items():
            txt += str(variable) + LINE_BREAK
            txt += str(value) + LINE_BREAK
        
        txt += EXIT_CHAR + EXIT_CHAR + EXIT_CHAR
        return txt
    
    def __str__(self):
        return self.format_relaxation()

class ScalarRelaxation(Relaxation):

    _prefix = 'solve/set/under-relaxation'

    def __init__(self,variable: str,
                      value: float):

        super().__init__(variable,value)

    @staticmethod
    def _check_allowable_variables(variable: str,
                                    value: float) -> None:
                    
        if variable in ALLOWABLE_VARIABLE_RELAXATION:        
            if value > 1 or value < 0:
                raise ValueError('Value must be between 0 and 1, not {}'.format(value))
        
        else:
            raise ValueError('{} not an allowable variable for relaxation'.format(variable))

class EquationRelaxation(Relaxation):

    """
    class for allowing the adjustment of relaxation factors
    to aid in the convergence of difficult solutions
    This treats explicitly the equation relaxations so 
    momentum
    pressure
    and allows adjustment of the Courant number
    """
    _prefix = 'solve/set/p-v-controls'

    def __init__(self,variable: str,
                      value: float):

        super().__init__(variable,value)

        #unlike the other relaxation, the prompt requires all three
        #relaxation inputs regardless - we will provide the defaults if none
        #are provided
        for key,value in ALLOWABLE_RELAXATION.items():
            if key not in self.var_value_dict:
                self.var_value_dict[key] = value

        #this needs to be in the correct order
        self.var_value_dict = OrderedDict((k,self.var_value_dict[k]) for 
                                            k in ALLOWABLE_RELAXATION.keys())
        
    @staticmethod
    def _check_allowable_variables(variable: str,
                                   value: float) -> None:
        if variable in ALLOWABLE_RELAXATION:
            if value == 'default':
                value = ALLOWABLE_RELAXATION[variable]
            
            if variable == 'momentum' or variable == 'pressure':
                if value > 1 or value < 0:
                    raise ValueError('Value must be between 0 and 1, not {}'.format(value))
        else:
            raise ValueError('{} not an allowable variable for relaxation'.format(variable))
    
    def format_relaxation(self):
        txt = self._prefix + LINE_BREAK
        for _,value in self.var_value_dict.items():
            txt += str(value) + LINE_BREAK
        
        txt += EXIT_CHAR + EXIT_CHAR + EXIT_CHAR 
        return txt
        
class NISTRealGas:

    """
    class for setting up a real gas model for fluent. This is required if 
    we want to shift from interpolated/constant properties in fluent to 
    NIST real gas models after a few iterations - you may want to do this 
    because NIST real gas models can make convergence very difficult/
    can error fluent out if the solutions are very outside of the reccomended
    range of the correlation used. 

    this will check to make sure that the fluid supplied is allowable within the
    fluent database so that this doesn't cause errors at runtime
    """

    _prefix = '/define/user-defined/real-gas-models/nist-real-gas-model'
    
    def __init__(self,gas: str):
        lib = self.read_lib()
        if '.fld' not in gas:
            gas += '.fld'
        
        if gas not in lib:
            raise FileExistsError('Gas property: {} not available in the NIST Real Gas Library'.format(gas))
        
        self.__gas = gas

    @property
    def gas(self):
        return self.__gas

    def format_real_gas(self):

        txt = self._prefix + LINE_BREAK
        txt += 'yes' + LINE_BREAK
        txt += self.gas + LINE_BREAK
        txt += 'no' + LINE_BREAK
        return txt

    def __str__(self):
        return self.format_real_gas()

    @staticmethod
    def read_lib():
        """
        reads in the list of fluids taken from fluent - or rather the real 
        gas models taken from fluent. This is to check
        the supplied fluid again. 

        This is very computationally inefficient practice to do this parsing everytime
        but I am lazy and because this function shoud not be called a bunch of times
        it should be fine.
        """

        path = os.path.split(os.path.split(__file__)[0])[0]
        lib_name = os.path.join(path,'dat/nist_real_gas_lib')
        with open(lib_name,'r') as file:
            string = file.read()
        
        lines = string.split(LINE_BREAK)
        flds = []
        for line in lines:
            fld = [f.strip() for f in line.split(' ')]
            flds += fld
        
        return flds

class Discritization:

    """
    class for changing discritization schemes. This can be useful if you are
    having issues with convergence of the solution i.e. starting out at first order
    and working to second order/higher orders
    """

    _prefix = '/solve/set/discretization-scheme'
    pmap = {'Second Order Upwind':'Second Order',
            'First Order Upwind':'Linear'}
        
    def __init__(self,schemes = 'all',orders = None):

        if schemes == 'all':
            self.__schemes = ALLOWABLE_DISCRITIZATION_SCHEMES
        else:
            if not isinstance(schemes,list):
                schemes = [schemes]

            for scheme in schemes:
                if scheme not in ALLOWABLE_DISCRITIZATION_SCHEMES:
                    raise ValueError('No discritization scheme for field variable: {}'.format(scheme))

            self.__schemes = schemes
        
        if orders is None:
            self.__orders = ['Second Order Upwind' for _ in range(len(self.schemes))]
        else:
            if not isinstance(orders,list):
                orders = [orders for _ in range(len(self.schemes))]
            if len(orders) != len(self.schemes):
                raise AttributeError('Orders and schemes must be of the same length')
            
            for order in orders:
                if order not in ALLOWABLE_DISCRITIZATION_ORDERS: 
                    raise ValueError('order of {} not allowed'.format(order))
            
            self.__orders = orders

    @property
    def schemes(self):
        return self.__schemes
    
    @property
    def orders(self):
        return self.__orders
    
    def format_default_scheme(self,scheme,order):
        """
        schemes for most variables here
        """
        txt = ''
        txt += scheme + LINE_BREAK
        txt += str(ALLOWABLE_DISCRITIZATION_ORDERS[order]) + LINE_BREAK
        return txt
    
    def format_pressure_scheme(self,scheme,order):
        """
        the scheme for presure is different for some reason
        """
        txt = ''
        try:
            order = self.pmap[order]
        except KeyError:
            pass

        txt += scheme + LINE_BREAK
        txt += str(ALLOWABLE_DISCRITIZATION_ORDERS[order]) + LINE_BREAK
        return txt
    
    def format_discritization(self):
        """
        format the discrization scheme for TUI
        """
        txt = self._prefix + LINE_BREAK
        for s,o in zip(self.schemes,self.orders):
            if s == 'pressure':
                txt += self.format_pressure_scheme(s,o)
            else:
                txt += self.format_default_scheme(s,o)
        
        txt += EXIT_CHAR + EXIT_CHAR + EXIT_CHAR
        return txt
    
    def __str__(self):
        """
        string representation
        """
        return self.format_discritization()
    
class FileIO(ABC):

    """
    Base class for file-io in fluent - inherited by various reader's and writers
    """
    _prefix = ''
    _suffix = ''

    def __init__(self,file,*args,**kwargs):

        self.__file = file
    
    @property
    def file(self):
        return self.__file
    
    def __str__(self):
        return self._prefix + ' ' + self.file + self._suffix

class CaseReader(FileIO):

    """
    representation of the read-case command
    """
    
    _prefix = 'file/read-case'

    def __init__(self,file):

        if '.cas' not in file and WARNINGS:
            print('Warning:: file: {} is not of .cas type, fluent may be unable to read'.format(file))
        
        super().__init__(file)

class CaseMeshReplaceReader(FileIO):

    """
    read-case and then replace with another mesh
    
    Parameters
    ----------0
    case_file: str - the string file name of the case file you want to read
    mesh_file: str - the mesh file string name of the case file you want to read
    """

    _prefix = 'mesh/replace'

    def __init__(self,case_file: str,
                      mesh_file: str) -> None:

        _case_reader = CaseReader(case_file)
        self._prefix = str(_case_reader) + LINE_BREAK + self._prefix
        super().__init__(mesh_file)
    
class CaseDataReader(CaseReader):

    """
    read case and data
    """
    _prefix = 'file/read-case-data'

    def __init__(self,file,
                      warnings = None):

        if warnings is None:
            warnings = WARNINGS
        
        head,tail = os.path.split(os.path.abspath(file))
        name,ext = os.path.splitext(tail)
        
        super().__init__(file)

class FluentEngine:

    """
    main class for the post processing engine using fluent
    """
    def __init__(self,file: str,
                      specification = '3ddp',
                      num_processors = 1,
                      reader = CaseDataReader):
        
        self.path,file_name = os.path.split(file)
        self.spec = specification
        self.__num_processors = num_processors
        self.__input = reader(file_name)
        self._additional_txt = ''
        self.input_file = os.path.join(self.path,FLUENT_INPUT_NAME)
        self.output_file = os.path.join(self.path,FLUENT_OUTPUT_NAME)
    

    def insert_text(self,other):
        self._additional_txt += other
    
    @property
    def num_processors(self):
        return str(self.__num_processors)

    def _fluent_initializer(self,
                            system = 'windows'):
        
        if system == 'windows':
            return WINDOWS_FLUENT_INIT_STATEMENT.format(self.spec,
                                                        self.num_processors,
                                                        FLUENT_INPUT_NAME,
                                                        FLUENT_OUTPUT_NAME) + EXIT_CHAR
    

    @property
    def input(self):
        return str(self.__input)
    
    def format_call(self):
        """
        format the text for the call, and also write the input file for 
        fluent
        """
        call_text = self._fluent_initializer()
        self.format_input_file()
        return call_text
    
    def format_input_file(self) -> None:
        """
        format the input file to fluent to read and create the surface integral
        """
        txt = self.input + LINE_BREAK
        txt += self._additional_txt + LINE_BREAK
        txt += EXIT_STATEMENT + LINE_BREAK

        with open(self.input_file,'w') as file:
            file.write(txt)
    
    def clean(self):
        """ 
        clean directory from input and output files
        """
        if os.path.exists(self.input_file):
            os.remove(self.input_file)
        
        if os.path.exists(self.output_file):
            os.remove(self.output_file)
        
    def __call__(self):
        """
        This call does the following:
        (1) cleans the directory of the fluent case file from input and output files
        (2) formats the call
        (3) opens fluent and submits commands to fluent
        (4) cleans up the directory again
        """

        self.clean()
        txt = self.format_call()
        cwd = os.getcwd()
        os.chdir(self.path)
        process = subprocess.call(txt)
        os.chdir(cwd)
        self.clean()
        return process

class BatchCaseReader(CaseReader):

    """
    case reader for batched inputs
    """
    _prefix = 'sync-chdir ..' + LINE_BREAK + 'file/read-case'
    def __init__(self,file):

        super().__init__(file)

    @property
    def _suffix(self):
        return LINE_BREAK + 'sync-chdir {}'.format(self.pwd)
        
    @property
    def pwd(self):
        return self.__pwd

    @pwd.setter
    def pwd(self,pwd):
        self.__pwd = pwd
    
class DataWriter(FileIO):

    """
    representation of the write-data command
    """
    
    _prefix = 'file/write-data'

    def __init__(self,file):

        super().__init__(file)

class CaseWriter(FileIO):

    """
    representation of the write-case command
    """
    
    _prefix = 'file/write-case'

    def __init__(self,file):

        super().__init__(file)

class Solver_Iterator:

    """
    base representation of a solver iterator - this could be replace by a significnatly
    more complex procedure, but for now just iterates a case for a given amount of time
    """
    _prefix = 'solve/iterate'
    def __init__(self,niter = 200):
        self.__niter = niter
    
    @property
    def niter(self):
        return self.__niter
    
    def __str__(self):
        return self._prefix + ' ' + str(self.niter)

class Solver:

    """
    the solver class, must be initialzed with an initializer (for the solver)
    and a Solver_Iterator
    """
    
    def __init__(self,
                 initializer = Initializer(),
                 solver_iterator = Solver_Iterator()):

        self.__initializer = initializer
        self.__solver_iterator = solver_iterator

    @property
    def initializer(self):
        return self.__initializer
    
    @property
    def solver_iterator(self):
        return self.__solver_iterator

    @property
    def usage(self):
        return 'parallel timer usage'

class ConvergenceConditions:

    _prefix = '/solve/convergence-conditions'

    def __init__(self,variables: list,
                      condition = 'all',
                      initial_values_to_ignore = 0,
                      previous_values_to_consider = 1,
                      stop_criterion = 1e-3,
                      print_value = True,
                      ):

        self.__variables = variables
        self.__condition = condition.lower()
        self.__initial_values_to_ignore = initial_values_to_ignore
        self.__previous_values_to_consider = previous_values_to_consider
        self.__print = print_value
        self.__stop_criterion = stop_criterion

    @property
    def variables(self):
        return self.__variables
    
    @property
    def condition(self):
        if self.__condition == 'all':
            return '1'
        elif self.__condition == 'any':
            return '2'
        else:
            raise ValueError('condition must be "all" or "any"')

    @property
    def print_value(self):
        if self.__print:
            return 'yes' 
        else:
            return 'no'
        
    @property
    def initial_values_to_ignore(self):
        return self.__initial_values_to_ignore
    
    @property
    def previous_values_to_consider(self):
        return self.__previous_values_to_consider
    
    @property
    def stop_criterion(self):
        return self.__stop_criterion
    
    def format_condition(self):

        txt = 'condition' + LINE_BREAK
        txt += self.condition + LINE_BREAK
        return txt
    
    def add_condition(self,name):

        txt = 'add' + LINE_BREAK
        txt += name + '-convergence' +  LINE_BREAK
        txt += 'initial-values-to-ignore' + LINE_BREAK
        txt += str(self.initial_values_to_ignore) + LINE_BREAK
        txt += 'previous-values-to-consider' + LINE_BREAK
        txt += str(self.previous_values_to_consider) + LINE_BREAK
        txt += 'print' + LINE_BREAK
        txt += self.print_value + LINE_BREAK
        txt += 'stop-criterion' + LINE_BREAK
        txt += str(self.stop_criterion) + LINE_BREAK
        txt += 'report-defs' + LINE_BREAK
        txt += name + LINE_BREAK
        txt += EXIT_CHAR

        return txt
    
    def format_convergence_conditions(self):

        txt = self._prefix + LINE_BREAK
        txt += self.format_condition()
        txt += 'conv-reports' + LINE_BREAK
        for var in self.variables:
            txt += self.add_condition(var)
        
        txt += EXIT_CHAR + EXIT_CHAR
        return txt

    def __str__(self):
        return self.format_convergence_conditions()

class FluentCase:
    
    """ 
    class for representing a fluent case
    """
    
    def __init__(self,case_name: str):

        self.__case_file = case_name

    @property
    def case_file(self):
        return self.__case_file

class TurbulentBoundarySpecification(ABC):

    _line_break = LINE_BREAK

    def __init__(self):
        pass

    @abstractmethod
    def turbulence_spec(self):
        pass

    def skip_choices(self,num):

        return ''.join(['no' + self._line_break for _ in range(num)])

class TwoEquationTurbulentBoundarySpecification(TurbulentBoundarySpecification):

    def __init__(self):
        self.__tke = 1
        self.__length_scale = None
        self.__intensity = None
        self.__viscosity_ratio = None
        self.__hydraulic_diameter = None

    @property
    def intensity(self):
        return self.__intensity
    
    @property
    def tke(self):
        return self.__tke

    @property
    def length_scale(self):
        return self.__length_scale

    @property
    def viscosity_ratio(self):
        return self.__viscosity_ratio

    @property
    def hydraulic_diameter(self):
        return self.__hydraulic_diameter
    
    @intensity.setter
    def intensity(self,intensity):
        self.__intensity = intensity
    
    @tke.setter
    def tke(self,tke):
        self.__tke = tke

    @length_scale.setter
    def length_scale(self,ls):
        self.__length_scale = ls

    @viscosity_ratio.setter
    def viscosity_ratio(self,vr):
        self.__viscosity_ratio = vr
    
    @hydraulic_diameter.setter
    def hydraulic_diameter(self,hd):
        self.__hydraulic_diameter = hd

    def _intensity_and_hydraulic_diameter(self) -> str:

        txt = self.skip_choices(3)
        txt += 'yes' + self._line_break
        #no to profile
        #txt += 'no' + self._line_break
        txt += str(self.intensity) + self._line_break
        #no to profile
        #txt += 'no' + self._line_break
        txt += str(self.hydraulic_diameter) + self._line_break

        return txt
    
    def turbulence_spec(self,specification):
        if specification == 'intensity and hydraulic diameter':
            return self._intensity_and_hydraulic_diameter()
        elif specification == 'k and omega':
            return self._k_and_omega_specification()
        elif specification == 'k and epsilon':
            return self._k_and_epsilon_specification()
        else:
            raise NotImplementedError('Havent implemented boundary specification mechanisms beyond Intensity and Hydraulic Diameter and K and Omega')
    
class StandardKOmegaSpecification(TwoEquationTurbulentBoundarySpecification):

    def __init__(self):

        super().__init__()
        self.__omega = 1
    
    @property
    def omega(self):
        return self.__omega
    
    @omega.setter
    def omega(self,o):
        self.__omega = o
    
    def _k_and_omega_specification(self) -> str:
        
        #no to profile
        txt = 'yes' + self._line_break + 'no' + self._line_break
        txt += str(self.tke) + self._line_break
        #no to profile
        txt += 'no' + self._line_break
        txt += str(self.omega) + self._line_break
        return txt

class StandardKEpsilonSpecification(TwoEquationTurbulentBoundarySpecification):

    def __init__(self):

        super().__init__()
        self.__tdr = 1

    @property
    def tdr(self):
        return self.__tdr

    @tdr.setter
    def tdr(self,tdr):
        self.__tdr = tdr

    def _k_and_epsilon_specification(self) -> str:
        
        #no to profile
        txt = 'yes' + LINE_BREAK + 'no' + LINE_BREAK
        txt += str(self.tke) + LINE_BREAK
        #no to profile
        txt += 'no' + LINE_BREAK
        txt += str(self.tdr) + LINE_BREAK
        return txt

def _assign_turbulence_model(model:str) -> TurbulentBoundarySpecification:

    assignment = {'ke-standard':StandardKEpsilonSpecification,
                  'ke-realizable':StandardKEpsilonSpecification,
                  'ke-rng': StandardKEpsilonSpecification,
                  'kw-standard':StandardKOmegaSpecification}

    try:
        return assignment[model]()
    except KeyError:
        raise ValueError('cannot identify the requested model: {}'.format(model))

class ModelModification(ABC):

    _prefix = 'define/models/{}'
    """
    abstract base class for modifying models
    """
    def __init__(self,model_class: str):

        self.model_class = model_class
    
    def __str__(self):

        txt = self._prefix.format(self.model_class) + LINE_BREAK
        txt += self.format_model_modification()
        return txt

    @abstractmethod
    def format_model_modification():
        pass

class ViscousModelModification(ModelModification):
    """
    Description
    ------------
    class implemented in order to facilitate modification of turbulence models
    in Fluent.

    The allowable models (listed) below are limited here because I am unsure of the
    behavior of the fluent case if two-equation models are not selected at this time
    this list may be appended to in the future
    """

    allowable_viscous = ['ke-realizable',
                         'ke-rng',
                         'ke-standard',
                         'kw-bsl',
                         'kw-sst',
                         'kw-standard',
                         'k-kl-w']


    def __init__(self,name: str):
        
        if name not in self.allowable_viscous:
            txt = [allow + '\n' for allow in self.allowable_viscous]
            raise ValueError('name: {} not allowed, must be one of: {}'.format(txt))
        
        super().__init__('viscous')
        self.name = name

    def format_model_modification(self):

        txt = self.name + LINE_BREAK
        txt += 'yes' + LINE_BREAK
        txt += EXIT_CHAR + LINE_BREAK
        return txt

class FluentCellZone(ABC):

    _prefix = '/define/boundary-conditions/{}'
    _line_break = LINE_BREAK
    def __init__(self,name: str,
                      boundary_type: str):
        
        self.name = name
        self.boundary_type = boundary_type
        
        #material change
        self._mat_change = False
        self._new_material = None

        #add source
        self._add_const_src = False
        self._source_value = None

        #change zone type
        self._modify_zone = False
        self._zone_type = None


    def change_material(self, new_material: str) -> None:
        """
        stores wether or not to change the material
        """

        self._mat_change = True
        self._new_material = new_material
    
    def add_constant_source(self,source_value: Union[float,list]) -> None:
        """
        add a constant source to a cell zone
        """
        self._add_const_src = True
        self._source_value = source_value
    
    def modify_zone_type(self,new_type: str) -> str:
        """
        modify the cell zone type
        """
        if new_type != 'fluid' and new_type!= 'solid':
            raise ValueError('only types of fluid or solid supported')
        
        self._modify_zone = True
        self._zone_type = new_type

    def format_change_material(self) -> str:
        """
        format changing the material
        """
        if self._mat_change:
            txt = self._prefix.format(self.boundary_type) + self._line_break
            txt += self.name + self._line_break
            txt += 'yes' + self._line_break
            txt += self._new_material + self._line_break
        else:
            txt = 'no' + self._line_break

        return txt

    def format_add_constant_source(self) -> str:
        """
        formatt the addition of a source
        """
        if isinstance(self._source_value,list):
            raise NotImplementedError('gonna have to support list source terms here')
            len_src = len(self._source_value)
        else:
            len_src = 1

        if len_src > 10:
            raise ValueError('Fluent doesnt allow specification of more than 10 sources')
        
        if self._add_const_src:
            txt = 'yes' + self._line_break
            txt += str(len_src) + self._line_break
            txt += 'yes' + self._line_break
            txt += str(self._source_value) + self._line_break

        else:
            txt = 'no' + self._line_break
        
        return txt

    def format_modify_zone(self) -> str:
        """
        format the modification of a zone type
        """
        txt = self._prefix.format('modify-zones/zone-type') + self._line_break
        txt += self.name + self._line_break
        txt += self._zone_type + self._line_break
        return txt


    def __call__(self) -> str:

        return self.format_boundary_condition()
    
    def format_boundary_condition(self) -> str:

        if self._modify_zone:
            txt = self.format_modify_zone()
        else:
            txt = ''

        txt += self.format_change_material()
        txt += self.format_add_constant_source()
        
        txt += 'no' + self._line_break
        txt += 'no' + self._line_break
        txt += 'no' + self._line_break
        txt += '0' + self._line_break
        txt += 'no'  + self._line_break
        txt += '0' + self._line_break
        txt += 'no'  + self._line_break
        txt += '0' + self._line_break
        txt += 'no'  + self._line_break
        txt += '0' + self._line_break
        txt += 'no'  + self._line_break
        txt += '0' + self._line_break
        txt += 'no'  + self._line_break
        txt += '1'  + self._line_break
        txt += 'no'  + self._line_break
        txt += 'no'  + self._line_break

        return txt

class SolidCellZone(FluentCellZone):

    def __init__(self,name: str) -> None:

        super().__init__(name,'solid')

class UDF:

    """
    Description
    -----------
    class for representing a UDF for loading into boundary conditions in fluent
    
    Parameters
    -----------
    file_name: str - the name of the udf file
    udf_name: str - the name of the udf in fluent
    data_name: str - the name of the data name in fluent
    condition_name: str - the name of the condition (i.e. convection_coefficient, 
                          heat_flux, ect.. the UDF is intended to be applied to)

    compile = False - option to compile the UDF at runtime. Default is False
    """

    _line_break = '\n'
    _compile_prefix = 'define/user-defined'
    def __init__(self,file_name: str,
                      udf_name: str,
                      data_name: str,
                      condition_name: str,
                      compile = False) -> None:


        if not os.path.exists(file_name):
            raise FileNotFoundError('file: {} does could not be found'.format(file_name))
        
        self.file_name = file_name
        self.udf_name = udf_name
        self.__data_name = data_name
        self.condition_name = condition_name
        self.compile = compile

    @property
    def data_name(self):
        return r'"' + self.__data_name + r'"'

    def format_enable_udf(self):
        """
        string sequence to enable using udf
        """
        text = 'yes' + self._line_break
        text += 'yes' + self._line_break
        text += self.udf_name + self._line_break
        text += self.data_name + self._line_break

        return text

    def format_compile_udf(self):
        """
        format string sequence to compile udf if required
        """
        return ''

    def __str__(self):
        """
        string sequence to enablle
        """

        return self.format_enable_udf()

def enable_udf(condition_name: str) -> callable:
    """
    decorator meant to enable all conditions 
    that can have  udf profile to have one 
    
    udf - the udf that could be enabled
    """
    def udf_enabled_condition(condition: callable) -> callable:

        """
        wrapper for a udf enabled condition that 
        takes in the arguments of 

        1. condition - a callable with the specifications for the condition
        
        if the udf is None, the condition is returned. If the udf is not None
        then the text for the udf is returned as well as the condition

        """

        def enabled_condition(self,*args,**kwargs) -> str:
            
            try:
                return str(self.udf[condition_name])
            except KeyError:
                additional_text = 'no' + self._line_break
                return additional_text + condition(self,*args,**kwargs)
            
        return enabled_condition
    
    return udf_enabled_condition

class FluentBoundaryCondition(ABC):
    """
    Description
    -----------
    Base class for all fluent boundary conditions. This class contains many of the basic 
    routines required for parsing in other boudnary conditions, and does some basic
    parsing and checking of inputs as well

    Parameters
    ------------
    boundary_type: the type of the boundary, will raise ValueError if not in ALLOWABLE_BOUNDARY_TYPES
    models: a list of models that are being used in Fluent, will raise ValueError if not in ALLOWABLE_VISCOUS_MODELS
            or not in ALLOWABLE_MODELS
    solver: the solver that is being used in Fluent. Will raise ValueError if not in ALLOWABLE_SOLVERS
    reference_frame: whether or not the reference frame is absolute

    Methods
    -------------
    add_udf() - add a udf to the boundary condition
    remove_udf() - remove a udf from the boundary condition

    """
    _prefix = '/define/boundary-conditions/'
    _line_break = LINE_BREAK
    _line_start = '/'

    def __init__(self,name: str,
                      boundary_type: str,
                      models: list,
                      solver: str,
                      *args,
                      reference_frame = 'absolute',
                      **kwargs):
        
        if solver not in ALLOWABLE_SOLVERS:
            raise ValueError('solver: {} is not allowed'.format(solver))
        
        for model in models:
            if model not in ALLOWABLE_VISCOUS_MODELS and model not in ALLOWABLE_MODELS:
                raise ValueError('model: {} is not allowed'.format(model))
        
        if boundary_type not in ALLOWABLE_BOUNDARY_TYPES:
            raise ValueError('Cannot parse boundary of type: {}'.format(boundary_type))
        
        self.__btype = boundary_type
        self.__name = name
        self.__models = models
        self.__solver = solver
        self.__udf = {}
        self.__reference_frame = reference_frame

    @property
    def name(self):
        return self.__name

    @property
    def models(self):
        return self.__models
    
    @property
    def solver(self):
        return self.__solver

    @property
    def btype(self):
        return self.__btype

    @property
    def udf(self):
        return self.__udf
    
    @property
    def reference_frame(self):
        if self.__reference_frame == 'absolute':
            return 'yes'
        else:
            return 'no'
    
    @udf.setter
    def udf(self,udf):
        self.__udf = udf
    
    def enter_statement(self):
        return self._prefix + self.btype + self._line_break + self.name + self._line_break        

    def add_udf(self,new_udf: UDF) -> None:
        """
        add a new udf to the udf dictionary
        """
        if new_udf.condition_name not in self.udf:
            self.udf[new_udf.condition_name] = new_udf
        else:
            raise ValueError('Cannot have multiple udfs with the same condition name for the same boundary')

    def remove_udf(self,udf_condition_name: str) -> UDF:
        """
        remove a UDF by condition name and return that UDF
        """
        try:
            self.udf.pop(udf_condition_name)
        except KeyError as ke:
            raise KeyError('Cannot find UDF with condition name:{} in udf dictionary'.format(udf_condition_name))
        
    def _configure_udf_from_mapping(self,mapping: dict) -> str:
        """
        base function for configuring the udfs for a boundary condition
        """
        _compile_text = ''
        for formatter,property_name in mapping.items():
            #assign values of -1 to all properties with udf
            if formatter in self.udf:
                self.__setattr__(property_name,-1)
                if self.udf[formatter].compile:
                    _compile_text += self.udf[formatter].format_compile_udf()

        return _compile_text

    @abstractmethod
    def format_boundary_condition(self):

        pass

class FluentSolidBoundaryCondition(FluentBoundaryCondition):
    
    def __init__(self,name: str,
                      boundary_type: str,
                      models: list,
                      solver: str,
                      *args,**kwargs):

        super().__init__(name,boundary_type,models,solver,*args,**kwargs)

    def __call__(self):

        return self.format_boundary_condition()
    
    def format_boundary_condition(self):

        return super().format_boundary_condition()
    
class WallBoundaryCondition(FluentSolidBoundaryCondition):


    """
    caf - convective augmentation factor
    """
    
    def __init__(self,name: str,
                      models: list,
                      solver: str,
                      shell_conduction = False):

        if 'energy' not in models:
            raise NotImplementedError('boundary condition not configured to work without energy equation')
        
        super().__init__(name,'wall',models,solver)
        self.__wall_thickness = 0
        self.__generation = 0
        self.__heat_flux = None
        self.__convection_coefficient = None
        self.__free_stream_temperature = None
        self.__caf = 1
        
        if shell_conduction:
            self.shell_conduction = 'yes'
        else:
            self.shell_conduction = 'no'

    @property
    def wall_thickness(self):
        return self.__wall_thickness
    
    @property
    def generation(self):
        return self.__generation

    @property
    def convection_coefficient(self):
        return self.__convection_coefficient
    
    @property
    def heat_flux(self):
        return self.__heat_flux
    
    @property
    def free_stream_temperature(self):
        return self.__free_stream_temperature
    
    @property
    def caf(self):
        return self.__caf

    @wall_thickness.setter
    def wall_thickness(self,wt):
        self.__wall_thickness = wt
    
    @generation.setter
    def generation(self,g):
        self.__generation = g
    
    @heat_flux.setter
    def heat_flux(self,hf):
        self.__heat_flux = hf
    
    @convection_coefficient.setter
    def convection_coefficient(self,cc):
        self.__convection_coefficient = cc
    
    @free_stream_temperature.setter
    def free_stream_temperature(self,fst):
        self.__free_stream_temperature = fst
    
    @caf.setter
    def caf(self,caf):
        self.__caf = caf
    
    def __str__(self):

        txt = 'wall thickness: ' + str(self.wall_thickness) + self._line_break
        txt += 'heat generation: ' + str(self.generation) + self._line_break
        txt += 'heat flux: ' + str(self.heat_flux) + self._line_break
        
        return txt
    
    @enable_udf('heat_generation')
    def format_heat_generation(self):
            
        return str(self.generation) + self._line_break
    
    @enable_udf('heat_flux')
    def format_heat_flux(self):

        return str(self.heat_flux) + self._line_break

    @enable_udf('convection_coefficient')
    def format_convection_coefficient(self):

        return str(self.convection_coefficient) + self._line_break

    @enable_udf('free_stream_temperature')
    def format_free_stream_temperature(self):

        return str(self.free_stream_temperature) + self._line_break

    @enable_udf('convective_augmentation')
    def format_convective_augmentation(self):

        return str(self.caf) + self._line_break
        
    def format_shell_conduction(self):

        txt = self.shell_conduction + self._line_break
        return txt
    
    def _configure_udf(self):
        """
        configure mapping of udfs
        """
        mapping = {'heat_generation': 'generation',
                   'heat_flux': 'heat_flux',
                   'convection_coefficient': 'convection_coefficient',
                   'free_stream_temperature': 'free_stream_temperature',
                   'convective_augmentation': 'caf'}
        
        return self._configure_udf_from_mapping(mapping)

    def format_boundary_condition(self):

        txt = self._configure_udf()
        txt += self.enter_statement()
        txt += str(self.wall_thickness) + self._line_break
        txt += self.format_heat_generation()
        #no to change material
        txt += 'no' + self._line_break
        #no to change Thermal BC Type
        txt += 'no' + self._line_break
        if self.heat_flux is None:
            if self.convection_coefficient is None or self.free_stream_temperature is None:
                raise ValueError('cannot have None value for convection coefficient and free stream temperature if heat flux is None')
            
            txt += self.format_convection_coefficient()
            txt += self.format_free_stream_temperature()

        elif self.convection_coefficient is None:
            txt += self.format_heat_flux()
        
        txt += self.format_shell_conduction()
        txt += self.format_convective_augmentation()

        return txt
        
class FluentFluidBoundaryCondition(FluentBoundaryCondition):

    
    """
    Note on variable names: 
    tke - total kinetic energy
    tdr - total dissipation rate
    """ 

    def __init__(self,name:str,
                      boundary_type: str,
                      models: list,
                      solver: str,
                      turbulence_model: str,
                      *args,
                      direction_vector = None,
                      temperature = None,
                      **kwargs):

        super().__init__(name,boundary_type,models,solver,*args,**kwargs)
        self.__direction_vector = direction_vector
        self.__temperature = temperature
        self.__turbulence_model = _assign_turbulence_model(turbulence_model)
        self.__turbulence_specification = None

    def add_statement(self,text: str,
                           newtext: str) -> str:
        
        return text + self._line_start + newtext + self._line_start
    
    @property
    def turbulence_model(self):
        return self.__turbulence_model
    
    @property
    def direction_vector(self):
        return self.__direction_vector

    @property
    def temperature(self):
        return self.__temperature
      
    @direction_vector.setter
    def direction_vector(self,dv):
        self.__direction_vector = dv

    @temperature.setter
    def temperature(self,t):
        self.__temperature = t
    
    @property
    def turbulence_specification(self):
        return self.__turbulence_specification
    
    @turbulence_specification.setter
    def turbulence_specification(self,ts):
        self.__turbulence_specification = ts
    
    def direction_spec(self) -> str:

        """
        deals with setting the direction vector
        options consist of 
        (1) normal to boundary - selected if direction_vector is None
        (2) sets the direction vector asssuming a list or numpy array
            strict checking of the shape of the direction vector
         """
    
        txt = ''
        if self.direction_vector is None:
            txt = 'no' + self._line_break
            #normal to boundary
            txt += 'yes' + self._line_break
        else:
            msg = 'direction vector (if specified) must be a list or 1D numpy array'
            if isinstance(self.direction_vector,list):
                self.direction_vector = np.array(self.direction_vector).squeeze()
            elif isinstance(self.direction_vector,np.ndarray):
                self.direction_vector = self.direction_vector.squeeze()
            else:
                raise TypeError(msg)
            
            if self.direction_vector.ndim != 1:
                raise ValueError(msg)
            
            if self.direction_vector.shape[0] > 3:
                raise ValueError('direction vector cannot contain more than 3 components')

            txt = 'yes' + self._line_break + 'yes' + self._line_break
            for i in range(self.direction_vector.shape[0]):
                txt += 'no' + self._line_break + str(self.direction_vector[i]) + self._line_break
            
        return txt
    
    @enable_udf('temperature')
    def format_temperature(self) -> str:

        """
        deals with the tempearture specifications
        """
        return str(self.temperature) + self._line_break


    def __call__(self):
        return self.format_boundary_condition(turbulent_specification= self.turbulence_specification)

class MassFlowInlet(FluentFluidBoundaryCondition):

    """
    Mass flow rate boundary condition class
    """
    
    def __init__(self,name: str,
                      models: list,
                      solver: str,
                      turbulence_model: str,
                      *args,**kwargs):

        super().__init__(name,'mass-flow-inlet',models,solver,turbulence_model,*args,**kwargs)
        self.__mass_flow_rate = None
        self.__mass_flux = None
        self.__init_pressure = 0
    
    @property
    def mass_flow_rate(self):
        return self.__mass_flow_rate
    
    @property
    def mass_flux(self):
        return self.__mass_flux

    @property
    def init_pressure(self):
        return self.__init_pressure
    
    @mass_flow_rate.setter
    def mass_flow_rate(self,mfr):
        self.__mass_flow_rate = mfr
    
    @mass_flux.setter
    def mass_flux(self,mf):
        self.__mass_flux = mf

    @init_pressure.setter
    def init_pressure(self,ip):
        self.__init_pressure = ip

    @enable_udf('mass_flow_rate')
    def format_mass_flow_rate(self):
        return 'mass flow: {}'.format(self.mass_flow_rate) + self._line_break

    @enable_udf('mass_flux')
    def format_mass_flux(self):
        return 'mass flux: {}'.format(self.mass_flux) + self._line_break
    
    @enable_udf('pressure')
    def format_pressure(self):
        return 'pressure: {}'.format(self.init_pressure) + self._line_break
    
    def __str__(self):

        if self.mass_flow_rate is not None:
            txt = self.format_mass_flow_rate()
        elif self.mass_flux is not None:
            txt = self.format_mass_flux()
        else:
            raise ValueError('cannot have both mass flux and mass flow rate as None for MassFlowINlet Boundary condition')
        
        txt += self.format_temperature()
        txt += self.format_pressure()
        
        return txt
        
    def mass_specification(self) -> str:

        """ 
        deal with the mass flow rate specifications. Formats either the mass flow rate
        or the mass flux depending upon user specification. Allows specification through
        UDF. 
        """ 

        if self.mass_flow_rate is None:
            if self.mass_flux is None:
                raise ValueError('cannot leave both mass flow rate and mass flux unspecified')
            
            txt = 'no' + self._line_break + 'yes' + self._line_break
            txt += self.format_mass_flux()
        
        else:
            if self.mass_flux is not None:
                raise ValueError('You cannot specify both the mass flux and the mass flow rate')
            
            txt = 'yes' + self._line_break + 'no' + self._line_break
            txt += self.format_mass_flow_rate()
        
        return txt

    def _configure_udf(self):
        """
        configure mapping of udfs
        """
        mapping = {'temperature': 'temperature',
                   'pressure': 'init_pressure',
                   'mass_flux': 'mass_flux',
                   'mass_flow_rate': 'mass_flow_rate'}
        
        return self._configure_udf_from_mapping(mapping)
    
    def format_boundary_condition(self,turbulent_specification = 'K and Epsilon') -> str:

        txt = self._configure_udf()
        txt += self.enter_statement()
        txt += self.reference_frame + self._line_break     
        txt += self.mass_specification()
        if 'energy' in self.models:
            txt += self.format_temperature()
        txt += self.format_pressure()
        txt += self.direction_spec()
        txt += self.turbulence_model.turbulence_spec(turbulent_specification)
        
        return txt

class PressureOutlet(FluentFluidBoundaryCondition):

    def __init__(self,name:str,
                      models: list,
                      solver: str,
                      turbulence_model: str):

        super().__init__(name,'pressure-outlet',models,solver,turbulence_model)
        self.__pressure = None

    @property
    def pressure(self):
        return self.__pressure
    
    @pressure.setter
    def pressure(self,p):
        self.__pressure = p
    
    @enable_udf('pressure')
    def format_pressure(self):
        """
        specifications for the pressure
        """ 
        return str(self.pressure) + self._line_break

    def _configure_udf(self):
        """
        configure mapping of udfs
        """
        mapping = {'temperature': 'temperature',
                   'pressure': 'pressure'}
        
        return self._configure_udf_from_mapping(mapping)
    
    def format_boundary_condition(self,turbulent_specification = 'K and Epsilon') -> str:

        txt = self.enter_statement()
        txt += 'yes' + self._line_break
        txt += self.format_pressure()
        if 'energy' in self.models:
            txt += self.format_temperature()
        txt += self.direction_spec()
        txt += self.turbulence_model.turbulence_spec(turbulent_specification)
        #no to a couple of end options that are pretty obscure:
        #Radial Equiliibrium Pressure Distribution
        #Average Pressure Specification
        #Specify Targeted Mass Flow Rate
        txt += 'yes' + self._line_break + ''.join(['no' + self._line_break for _ in range(3)])

        return txt
    
    def __str__(self):

        txt = 'pressure: {}'.format(self.pressure) + self._line_break
        txt += 'temperature: {}'.format(self.temperature) + self._line_break
        
        return txt

class SurfaceIntegrals:
    """ 
    base class for all surface integrals that can be generated using 
    fluent. Hooks into an engine and executes upon inserting commands

    Instatation Arguments
    ---------------------
    file: str - string of the file to apply the surface integrals to
    id: str - the string of the boundary condition identification
    variable: str - the name of the variable to compute the surface integral for
    surface_type: str - the type of surface integral - i.e. area-weighted-avg
    engine: default - PostEngine - the engine to open fluent with
    """
    _prefix = '/report/surface-integrals/{}'

    def __init__(self,file:str,
                      id: str,
                      variable: str,
                      surface_type: str,
                      engine = FluentEngine,
                      id_pad = 1,
                      **engine_kwargs
                  ):
        
        #attempt to instantiate the engine - if the engine isn't callable
        #then assume that this is being used at the end of computation
        try:
            self.engine = engine(file,**engine_kwargs)
        except TypeError:
            self.engine = None
        
        self.file = file
        self.id,self.variable,self.surface_type  = \
             self._validate_constructor_args(id,variable,surface_type)
        
        file_names = [self._generate_file_name(self.file,st,id,var) for st,id,var 
                      in zip(self.surface_type,self.id,self.variable)]

        self.delete = {fname: True for fname in file_names}
        self.id_pad = id_pad

    @staticmethod
    def _validate_constructor_args(id: list,
                                   variable: list,
                                   surface_type: list) -> tuple:

        return _surface_construction_arg_validator(id,variable,surface_type)
    
    def prefix(self,surface_type: str):
        return self._prefix.format(surface_type)
    
    def file_name(self,id: str,
                       surface_type: str,
                       variable: str):
        """
        get the filename to write the surface integral to
        """
        fname = self._generate_file_name(self.file,
                                         surface_type,
                                         id,
                                         variable)
        
        if self.delete[fname]:
            self.delete[fname] = False
            if os.path.exists(fname):
                os.remove(fname)
            
        return fname
    
    def format_text(self):
        """
        format the text for the call to the surface integral here
        """

        txt = ''
        
        shortest_id = min([len(id) for id in self.id])
        for ids,variable,surface_type in zip(self.id,self.variable,self.surface_type):
            txt += self.prefix(surface_type) + LINE_BREAK
            for id in ids:
                txt += id + LINE_BREAK
            
            
            if len(ids) < shortest_id + self.id_pad:
                diff = len(ids) - shortest_id
                for _ in range(self.id_pad - diff):
                    txt += ' , ' + LINE_BREAK 
            else:
                txt += ' , ' + LINE_BREAK
            
            txt += variable + LINE_BREAK
            txt += 'yes' + LINE_BREAK
            _,_file = os.path.split(self.file_name(ids,surface_type,variable))
            txt += _file + LINE_BREAK
        
        return txt

    def __call__(self,
                 return_engine = False):

        #enables the post module to simply be passed as txt
        #if the engine is not callable
        if self.engine is not None:

            self.engine.insert_text(self.format_text())
            engine_ouput = self.engine()
            sif = []
            for ids,variable,surface_type in zip(self.id,self.variable,self.surface_type):
                sif.append(SurfaceIntegralFile(self.file_name(ids,surface_type,variable)))

            if return_engine:
                return sif,engine_ouput
            else:
                return sif
        else:
            return self.format_text()

    @staticmethod
    def _generate_file_name(file: str,
                            surface_type: str,
                            ids: list,
                            variable: str) -> str:
        
        _ids = ''.join([id + SURFACE_INTEGRAL_FILE_DELIM for id in ids])[0:-1]

        path,_file = os.path.split(file)
        _file = os.path.splitext(_file)[0]

        write_file = ''.join([item + SURFACE_INTEGRAL_FILE_DELIM for item in [_file,surface_type,_ids,variable]])[0:-1]
         
        return os.path.join(path,write_file)
    
class FluentRun(SerializableClass):
    
    """
    class for producing a fluent batch job file using provided information.
    The intent is to make this as easy to use as possible, so the only required argument
    is the case_file as a string argument, and everything else should be handled
    automatically
    """
    
    _line_break = LINE_BREAK
    def __init__(self,case_file: str,
                      output_name = 'result',
                      transcript_file = 'solution.trn',
                      reader = CaseReader,
                      data_writer = DataWriter,
                      case_writer = CaseWriter,
                      solver = Solver(),
                      post = [],
                      convergence_condition = None,
                      model_modifications = [],
                      boundary_conditions = []):

        self.__case = FluentCase(case_file)
        
        try:
            self.__reader = reader(case_file)
        except TypeError:
            self.__reader = reader
        
        #potentially immense storage savings here if we do not write every single case
        if case_writer is None:
            self.write_case = False
            self.__case_writer = None
        else:
            self.write_case = True
            self.__case_writer = case_writer(output_name + '.cas')
        
        self.__data_writer = data_writer(output_name + '.dat')
        self.__solver = solver
        self.__transcript_file = transcript_file
        self.__file_name = case_file
        self.__boundary_conditions = boundary_conditions
        self.__convergence_condition = convergence_condition
        self.__post = post
        self.model_modifications = model_modifications

    @property
    def case(self):
        return self.__case

    @property
    def file_name(self):
        return self.__file_name
    
    @file_name.setter
    def file_name(self,fn):
        self.__file_name = fn
    
    @property
    def reader(self):
        return self.__reader
    
    @property
    def case_writer(self):
        return self.__case_writer
    
    @property
    def convergence_condition(self):
        return self.__convergence_condition

    @property
    def data_writer(self):
        return self.__data_writer
    
    @property 
    def solver(self):
        return self.__solver
    
    @property
    def transcript_file(self):
        return self.__transcript_file
    
    @property
    def boundary_conditions(self):
        return self.__boundary_conditions
    
    @property
    def post(self):
        return self.__post
    
    @post.setter
    def post(self,p):
        self.__post = p

    @boundary_conditions.setter
    def boundary_conditions(self,bc):
        self.__boundary_conditions = bc
    

    def model_modification_spec(self):
        """
        must have a str method
        """

        txt = LINE_BREAK + ';Model Modifications' + LINE_BREAK + LINE_BREAK
        for model_mod in self.model_modifications:
            txt += str(model_mod)
        
        return txt

    def boundary_conditions_spec(self):
        """
        boundary conditions must be callable 
        """
        txt = LINE_BREAK + ';Boundary Conditions' + LINE_BREAK + LINE_BREAK
        for bc in self.boundary_conditions:
            txt += bc()
        
        return txt

    def format_convergence_condition(self):
        """ 
        convergence conditions must have a __str__ method defined
        """
        if self.convergence_condition is None:
            return ''
        else:
            txt = LINE_BREAK + ';Convergence Conditions' + LINE_BREAK + LINE_BREAK
            return txt + str(self.converence_condition)
    
    def post_spec(self):
        """
        everything from post must have a method format_text() that can be called 
        this bypasses the __call__ which would open another instance of fluent
        """
        txt = LINE_BREAK + ';Post Processing' + LINE_BREAK + LINE_BREAK
        for p in self.post:
            txt += p.format_text()
        
        return txt

    def format_fluent_file(self) -> str:

        """
        format the fluent input file
        """
        
        txt = 'file/start-transcript ' + self.transcript_file + self._line_break     
        
        txt +=  str(self.reader) + self._line_break
        txt += self.format_convergence_condition()
        txt += self.model_modification_spec()
        txt += self.boundary_conditions_spec()
        txt += str(self.solver.initializer) + self._line_break
        txt += str(self.solver.solver_iterator) + self._line_break
        txt += str(self.solver.usage) + self._line_break
        txt += self.post_spec()
        if self.write_case:
            txt += str(self.case_writer) + self._line_break
        
        txt += str(self.data_writer) + self._line_break
        
        txt += 'exit' + self._line_break

        return txt

    def __call__(self):
        return self.format_fluent_file()

    def write(self,f) -> None:

        try:
            with open(f,'w',newline = LINE_BREAK) as file:
                file.write(self.format_fluent_file())

        except TypeError:
            f.write(self.format_fluent_file())
    
    def _from_file_parser(dmdict):
        """
        allows for the parsing of the class from a file
        """
        dmdict.pop('class')
        dmdict.pop('case')
        dmdict.pop('write_case')
        case_file = dmdict.pop('file_name')
        dmdict['reader'] = dmdict.pop('reader').__class__
        dmdict['case_writer'] = dmdict.pop('case_writer').__class__
        dmdict['data_writer'] = dmdict.pop('data_writer').__class__


        return [case_file],dmdict
    




    
def main():

    #test_fluent_run()
    #test_mass_flow_rate_bc()
    #test_pressure_outlet_bc()
    #test_format_convergence_conditions()
    #test_discritization()
    #test_real_gas()
    #test_scalar_relaxation()
    #test_equation_relaxation()
    test_wall_udf()

if __name__ == '__main__':
    main()