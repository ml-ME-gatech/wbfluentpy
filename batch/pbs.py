#native imports
from abc import ABC,abstractstaticmethod
from datetime import timedelta
from copy import deepcopy
import math
from ..pace import PaceScript
import os

#package imports
from ..disk import SerializableClass

"""
Author: Michael Lanahan
Date Created: 08.01.2021
Last Edit: 01.03.2021

scripts for working with fluent using the PACE computational cluster at GT
"""

LINE_BREAK = '\n'

class PBS:

    """
    Abstract base class for the pbs header. Provides a base initialization method that formats the various
    initializer arguments into the required form for the pbs script. The formatting is done 
    in the property methods and is formatted into a script by the method "format_pbs_header()"
    this formatted text is then called like-so: 

    pbs = PBS(*args,**kwargs)
    text = pbs()

    where the variable "text" now contains the text in a pbs script

    note that the key word argument "memory_request" has options 'p' and 't'
    where 'p' is per core and 't' is total memory

    Example PBS script
    https://docs.pace.gatech.edu/software/PBS_script_guide/
    
    #PBS -N <job-name>                  -> name that shows up on the queue
    #PBS -A [Account]                   -> Account - the account that is required to run the jobs - who to charge
    #PBS -l nodes=1:ppn=8: cores24      -> resource-list; number of nodes and processers per node, specify number of cores
    #PBS -l pmem=8gb                    -> memory allocated PER CORE
    #PBS -l mem = 2gb                   -> total memory allocated over all nodes
    #PBS -l walltime=2:00:00            -> projected walltime - hard stop here
    #PBS -q inferno                     -> which que to submit too
    #PBS -j oe                          -> combines output and error into one file
    #PBS -o fluent.out                  -> names output files
    #PBS -m <a,b,e>                     -> will send job satus
                                        -> a - if job aborted; b- when job begins; e - when job ends

    cd $PBS_O_WORKDIR                               -> change to working directroy - where script is submited from
    module load ansys/<version.number>              -> load ansys, with version number in <int>.<int> i.e. 19.12
    fluent -t8 -g <inputfile> outputfile            -> run fluent command with input file and output file
    """
    
    line_leader = '#PBS '
    def __init__(self, name: str,
                       account: str,
                       queue: str,
                       output_file: str,
                       walltime: float,
                       memory:float,
                       nodes: int,
                       processors: int,
                       email = None,
                       email_permissions = None,
                       memory_request = 'p',
                       *args,
                       **kwargs):

        self.__name = name
        self.__account = account
        self.__queue = queue
        self.__output_file = output_file
        self.__walltime = walltime
        self.__memory = memory
        self.__nodes = nodes
        self.__processors = processors
        self.__email = email
        self.__email_permissions = email_permissions
        self.memory_request = memory_request.lower()
        if self.memory_request != 'p' and self.memory_request != 't':
            raise ValueError('memory must be requested on a per node "p" or total "t" basis')

    @property
    def name(self):
        return '-N ' + self.__name 
    
    @property
    def account(self):
        return '-A ' + self.__account
    
    @property
    def queue(self):
        return '-q ' + self.__queue
    
    @property
    def output_file(self):
        return '-o ' + self.__output_file
    
    @staticmethod
    def wall_time_formatter(td: timedelta) -> str:
        """
        you get issues upon direct string conversion of time delta
        because pace doesn't allow a "date" field for walltime - the largest
        unit of time is hour and it wants the wall time in:

        HH:MM:SS

        format
        """

        def _str_formatter(integer: int) -> str:

            if integer < 10:
                return '0' + str(integer)
            else:
                return str(integer)
    
        HOURS_PER_DAY = 24.0
        MINUTES_PER_HOUR = 60.0
        SECONDS_PER_MINUTE = 60.0

        hours = td.days*HOURS_PER_DAY
        hours += math.floor(td.seconds/(MINUTES_PER_HOUR*SECONDS_PER_MINUTE))
        hours =int(hours)
        _minutes = td.seconds % (MINUTES_PER_HOUR*SECONDS_PER_MINUTE)
        minutes = int(math.floor(_minutes/SECONDS_PER_MINUTE))
        seconds = int(_minutes % SECONDS_PER_MINUTE)

        td_str = ''
        for unit in [hours,minutes,seconds]:
            td_str += _str_formatter(unit) + ':'

        return td_str[0:-1]

    @property
    def walltime(self):
        td = timedelta(seconds = self.__walltime)
        return '-l walltime=' + self.wall_time_formatter(td)
    
    @property
    def memory(self):
        msg = '-l {}mem=' + str(self.__memory) + 'gb'
        if self.memory_request == 'p':
            return msg.format('p')
        else:
            return msg.format('')
    
    
    @property
    def processesors_nodes(self):
        return '-l nodes=' + str(self.__nodes) + ':ppn=' + str(self.__processors)
    
    @property
    def email(self):
        if self.__email is None:
            return self.__email
        else:
            return '-M '+  self.__email
    
    @property
    def email_permissions(self):
        if self.__email_permissions is None:
            return self.__email_permissions
        else:
            return '-m ' + self.__email_permissions

    @name.setter
    def name(self,n):
        self.__name = n
    
    def format_pbs_header(self):

        txt = ''
        for item in [self.name,self.account,self.queue,self.output_file,self.walltime,
                     self.memory,self.processesors_nodes,self.email,self.email_permissions]:
        
            if item is not None:
                txt += self.line_leader + ' ' + item + LINE_BREAK
        
        return txt

    def copy(self):
        return deepcopy(self)

    def __call__(self):
        return self.format_pbs_header()

class DefaultPBS(PBS):

    """
    a default pbs script. The account and queue are now hardcoded into the initializer
    while variables such as walltime,memory, nodes and processors are still required
    """
    
    def __init__(self,name: str,
                       walltime: float,
                       memory:float,
                       nodes: int,
                       processors: int,
                       output_file = 'fluent.out',
                       email = None,
                       email_permissions = 'abe',
                       memory_request = 'p',
                       account = 'GT-my14'):


        super().__init__(name,account,'inferno',output_file,walltime,
                        memory,nodes,processors,email = email,
                        email_permissions= email_permissions,memory_request = memory_request)

class PythonPBS(SerializableClass):

    PBS_PDIR = '$PBS_O_WORKDIR'
    def __init__(self,
                 script: PaceScript,
                 version = '2019.10',
                 name = 'python_deployment',
                 WALLTIME = 10,
                 MEMORY = 1,
                 N_NODES = 1,
                 N_PROCESSORS = 1,
                 pbs = DefaultPBS,
                 account = 'GT-my14',
                 memory_request = 'p'):

        self.pbs = pbs(name,WALLTIME,MEMORY,N_NODES,N_PROCESSORS,
                            'python_pace.out',memory_request = memory_request,
                            account = account)
        
        self.script = script
        try:
            if not os.path.exists(self.script.target_dir):
                os.mkdir(self.script.target_dir)
        except TypeError:
            pass
        
        self.version = version

    @staticmethod
    def format_change_dir(chdir)-> str:
        """
        this is important to change to the PBS dir which is an environment variable 
        native to the bash shell on PACE
        """
        return 'cd ' + chdir
    
    def format_load_anaconda(self) -> str:

        return 'module load anaconda3/{}'.format(self.version)

    def format_run_script(self) -> str:

        return 'python ' + self.script.script_name
    
    def format_call(self):

        txt = self.pbs() + LINE_BREAK
        txt += self.format_change_dir(self.PBS_PDIR) +LINE_BREAK
        txt += self.format_load_anaconda() + LINE_BREAK
        txt += self.script.setup() 
        txt += self.format_run_script() + LINE_BREAK

        return txt
    
    def __call__(self):
        """
        callable interface here
        """
        return self.format_call()
    
    def write(self,f = None):
        """
        write the script to a file or IOStream (whatever its called in python)
        """
        
        if self.script.target_dir is None:
            self.script.target_dir,_ = os.path.split(f)

        try:
            with open(f,'w',newline = LINE_BREAK) as file:
                file.write(self.format_call())

        except TypeError:
            f.write(self.format_call())

    def _from_file_parser(dmdict):
        """
        parser from the file that allows instantation from file
        """
        dmdict['_cached_pbs'] = dmdict.pop('pbs')
        dmdict.pop('class')
        input_file = dmdict.pop('input_file')
        dmdict['mpi_option'] = dmdict.pop('mpi_opt')
        return [input_file],dmdict