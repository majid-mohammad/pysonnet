import os
import yaml
import psutil
import logging
import subprocess
import pysonnet.blocks as b
from datetime import datetime


log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


def add_line(string, addition):
    """Append to string adding new line if empty."""
    if string:
        string.append(os.linesep + addition)
    else:
        string.append(addition)


class Project(dict):
    """
    Abstract base class for the Geometry and Netlist Projects. It should not be
    instantiated.

    :param load_path: path to the yaml file for this project if it was saved (optional)
    """
    def __init__(self, load_path=None):
        super().__init__()
        self.project_file_path = None
        self.sections = ['sonnet', 'dimensions', 'frequency', 'geometry', 'control',
                         'optimization', 'parameter_sweep', 'output_file',
                         'parameter_netlist', 'circuit', 'subdivider',
                         'quick_start_guide', 'component_data_files', 'translators']
        if load_path is not None:
            self.load(load_path)
        else:
            directory = os.path.dirname(__file__)
            load_path = os.path.join(directory, 'user_configuration.yaml')
            if not os.path.isfile(load_path):
                load_path = os.path.join(directory, 'default_configuration.yaml')
            self.load(load_path)

        # initialize internal boolean indicating if ports have been made
        if self['geometry']['ports']:
            self._has_ports = True
        else:
            self._has_ports = False

    def make_sonnet_file(self, file_path):
        """
        Convert the current state of this project into a Sonnet file.

        :param file_path: path where the file will be saved.
        """
        raise NotImplementedError

    def load(self, load_path):
        log.debug("loading configuration from '{}'".format(load_path))
        self.clear()
        # load configuration
        with open(load_path, "r") as file_handle:
            configuration = yaml.load(file_handle)
        for block in configuration.keys():
            if block not in self.sections:
                message = "{} is an unrecognized configuration section"
                raise ValueError(message.format(block))
        # add configuration to the object
        self.update(configuration)
        # add date if it doesn't exist
        if self['sonnet']['date'] == '':
            self['sonnet']['date'] = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
        log.debug("configuration loaded")

    def save(self, save_path):
        log.debug("saving current configuration to '{}'".format(save_path))
        self['sonnet']['date'] = datetime.now().strftime('%m/%d/%Y %H:%M:%S')
        with open(save_path) as file_handle:
            yaml.dump(dict(self), file_handle, default_flow_style=False)
        log.debug("configuration saved")

    def run(self, sweep_type, file_path=None, options='-v', external_frequency_file=None):
        """
        Run the project simulation.

        :param sweep_type: type of sweep to compute
            Valid options are 'frequency', 'parameter', or 'optimize'. The sweep
            corresponding to the sweep_type must have already been added to the project
            using add_frequency_sweep(), add_parameter_sweep(), or add_optimization().
            All sweeps of the specified type will be computed.
        :param file_path: path where the Sonnet file will be saved (optional)
            This parameter is optional if a Sonnet file has already been made and is
            consistent with the current project state.
        :param options: extra command line options to pass to Sonnet em
            Valid options are given on page 414 of the sonnet_users_guide.pdf. Verbose
            is turned on by default and the output is sent to the program log.
        :param external_frequency_file: path to the frequency control file (optional)
        """
        # check sweep_type
        message = "sweep_type must be either 'frequency' or 'parameter'"
        assert sweep_type in ['frequency', 'parameter', 'optimize'], message
        message = "add a sweep to the project before running"
        assert (self['frequency']['sweeps'] != '' or
                self['parameter_sweeps']['parameter_sweep'] != '' or
                self['optimization']['optimization_goals'] != ''), message
        # set sweep type
        if sweep_type == 'frequency':
            self['control']['sweep_type'] = "STD"
        elif sweep_type == 'parameter':
            self['control']['sweep_type'] = "VARSWP"
        else:
            self['control']['sweep_type'] = "OPTIMIZE"
        # check to make sure there is a project file to run
        if file_path is not None:
            self.make_sonnet_file(file_path)
        if self.project_file_path is None:
            message = ("run make_sonnet_file() or provide the 'file_path' argument "
                       "before running the simulation")
            raise ValueError(message)
        # check to make sure that sonnet has been configured
        if self['sonnet']["sonnet_path"] == '':
            raise ValueError("configure sonnet before running")
        # collect the command to run
        command = [os.path.join(self['sonnet']["sonnet_path"], "bin", "em "), options,
                   self.project_file_path, external_frequency_file]
        command = [element for element in command
                   if (element != '' and element != '-' and element is not None)]
        # run the command
        with psutil.Popen(command, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE) as process:
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    log.info(output.strip())

    def locate_sonnet(self, sonnet_path, version='', license_id=''):
        """
        Provide the project with the path to the Sonnet folder so that it can be run.

        :param sonnet_path: path to the Sonnet program
        :param version: Sonnet version number
        :param license_id: user license ID
        """
        assert os.path.isdir(sonnet_path), "'{}' is not a directory".format(sonnet_path)
        assert os.path.isfile(os.path.join(sonnet_path, 'bin', 'em')), \
            "the sonnet directory has an unrecognizable format"
        self['sonnet']['sonnet_path'] = sonnet_path
        self['sonnet']['version'] = version
        self['sonnet']['license_id'] = license_id

    def add_frequency_sweep(self, sweep_type, f1=None, f2=None, n_points=None,
                            f_step=None, frequency_list=None, s_parameter=None):
        """
        Add a frequency sweep to the analysis for the project. All added sweeps will be
        computed if the 'frequency' sweep_type is selected using run().

        :param sweep_type: sweep type to add to the project (str)
            Valid options are listed below with the additional arguments that can be used
            for each. Refer to the Sonnet documentation for details on the sweep types.
            linear:
                f1, f2, and (n_points or f_step)
            exponential:
                f1, f2, and n_points
            single:
                f1
            list:
                frequency_list
            dc:
                f1 (optional in units of kHz), if not specified a value is calculated for
                you by Sonnet
            abs:
                f1 and f2
            abs_min:
                s_parameter, f1, and f2
            abs_max:
                s_parameter, f1 and f2
        :param f1: a frequency (float)
        :param f2: a frequency (float)
        :param n_points: number of points in the sweep (int)
        :param f_step: frequency step in the sweep (float)
        :param frequency_list: list of frequencies for the sweep (list of floats)
        :param s_parameter: name of the scattering parameter (str), e.g. "S21"
        """
        # define some messages to be used throughout the function
        f1_f2_message = "'f1' and 'f2' must be defined for this sweep"
        f1_message = "'f1' must be defined for this sweep"
        n_points_message = "'n_points' must be defined for this sweep"
        frequency_list_message = "'frequency_list' must be defined for this sweep"
        s_parameter_message = "'s_parameter' must be defined for this sweep"
        # type check the input parameters
        type_message = "'{}' parameter must be of type '{}'"
        if f1 is not None:
            assert isinstance(f1, (int, float)), type_message.format('f1', 'float')
        if f2 is not None:
            assert isinstance(f2, (int, float)), type_message.format('f2', 'float')
        if n_points is not None:
            assert isinstance(n_points, int), type_message.format('n_points', 'int')
        if f_step is not None:
            assert isinstance(f_step, (int, float)), \
                type_message.format('f_step', 'float')
        if frequency_list is not None:
            assert isinstance(frequency_list, (tuple, list)), \
                type_message.format('frequency_list', 'list')
            for frequency in frequency_list:
                message = "each frequency in 'frequency_list' must be a float"
                assert isinstance(frequency, (int, float)), message
        if s_parameter is not None:
            assert isinstance(s_parameter, str), type_message.format('s_parameter', 'str')
        # format the sweep string depending on sweep type
        if sweep_type == 'linear':
            assert f1 is not None and f2 is not None, f1_f2_message
            if f_step is not None and n_points is None:
                sweep = b.SWEEP_FORMAT.format(f1=f1, f2=f2, f_step=f_step)
            elif f_step is None and n_points is not None:
                sweep = b.LSWEEP_FORMAT.format(f1=f1, f2=f2, n_points=n_points)
            else:
                message = ("one of 'f_step' or 'n_points' must be specified for a linear "
                           "sweep")
                raise ValueError(message)
        elif sweep_type == 'exponential':
            assert f1 is not None and f2 is not None, f1_f2_message
            assert n_points is not None, n_points_message
            sweep = b.ESWEEP_FORMAT.format(f1=f1, f2=f2, n_points=n_points)
        elif sweep_type == 'single':
            assert f1 is not None, f1_message
            sweep = b.STEP_FORMAT.format(f1=f1)
        elif sweep_type == 'list':
            assert frequency_list is not None, frequency_list_message
            sweep = b.LIST_FORMAT
            for frequency in frequency_list:
                sweep.append(str(frequency) + ' ')
        elif sweep_type == 'dc':
            if f1 is None:
                sweep = b.DC_FORMAT.format(fcalc="AUTO", frequency='')
            else:
                sweep = b.DC_FORMAT.format(fcalc="MAN", frequency=f1)
        elif sweep_type == 'abs':
            assert f1 is not None and f2 is not None, f1_f2_message
            sweep = b.ABS_FORMAT.format(f1=f1, f2=f2)
        elif sweep_type == 'abs_min':
            assert f1 is not None and f2 is not None, f1_f2_message
            assert s_parameter is not None, s_parameter_message
            sweep = b.ABS_MIN_FORMAT.format(s_parameter=s_parameter, f1=f1, f2=f2)
        elif sweep_type == 'abs_max':
            assert f1 is not None and f2 is not None, f1_f2_message
            assert s_parameter is not None, s_parameter_message
            sweep = b.ABS_MAX_FORMAT.format(s_parameter=s_parameter, f1=f1, f2=f2)
        else:
            message = ("'sweep_type' must be one of the following: 'linear', "
                       "'exponential', 'single', 'list', 'dc', 'abs', 'abs_min', "
                       "or 'abs_max'")
            raise ValueError(message)
        # add the sweep to the project
        add_line(self['frequency']['sweeps'], sweep)

    def clear_frequency_sweeps(self):
        """Removes all added frequency sweeps from the project."""
        self['frequency']['sweeps'] = ''

    def add_parameter_sweep(self):
        """Add a parameter sweep to the analysis for the project."""
        raise NotImplementedError

    def clear_parameter_sweeps(self):
        """Removes all added parameter sweeps from the project."""
        self['parameter_sweep']['parameter_sweep'] = ''

    def add_optimization(self):
        """Add an optimization to the analysis for the project."""
        raise NotImplementedError

    def clear_optimizations(self):
        """Removes all added optimizations from the project."""
        self['optimization']['optimization_parameters'] = ''
        self['optimization']['optimization_goals'] = ''


class GeometryProject(Project):
    """
    Class for creating and manipulating a Sonnet geometry project.
    """
    def make_sonnet_file(self, file_path):
        # convert the project format to the file format
        file_string = (b.GEOMETRY_PROJECT.format(**self['sonnet']) +
                       b.HEADER.format(**self['sonnet']) +
                       b.DIMENSIONS.format(**self['dimensions']) +
                       b.GEOMETRY.format(**self['geometry']) +
                       b.FREQUENCY.format(**self['frequency']) +
                       b.CONTROL.format(**self['control']) +
                       b.OPTIMIZATION.format(**self['optimization']) +
                       b.PARAMETER_SWEEP.format(**self['parameter_sweep']) +
                       b.OUTPUT_FILE.format(**self['output_file']) +
                       b.SUBDIVIDER.format(**self['subdivider']) +
                       b.QUICK_START_GUIDE.format(**self['quick_start_guide']) +
                       b.COMPONENT_DATA_FILES.format(**self['component_data_files']) +
                       b.TRANSLATORS.format(**self['translators']))

        log.debug("saving geometry project to '{}'".format(file_path))
        with open(file_path, "w") as file_handle:
            file_handle.write(file_string)
        self.project_file_path = file_path
        log.debug("geometry project saved")

    def add_reference_plane(self, position, plane_type='fixed', length=None):
        """
        Adds a reference plane to one side of the box.

        :param position: defines the box wall from which the reference plane extends.
            Valid values are 'left', 'right', 'top', and 'bottom'.
        :param plane_type: defines the method used to set the location of the plane
            Valid values are 'fixed' and 'linked'. Fixed reference planes must also
            specify the length parameter.
        :param length: number specifying the length of the reference plane
        """
        # check position parameter
        message = "valid values for the position are 'left', 'right', 'top', and 'bottom'"
        assert position in ['left', 'right', 'top', 'bottom'], message
        # check type parameter
        types = {"fixed": "FIX", "FIX": "FIX", "linked": "LINK", "LINK": "LINK"}
        message = "valid values for the plane_type are 'fixed' and 'linked'"
        assert plane_type in types.keys(), message
        # choose type
        if types[plane_type] == "FIX":
            # check length
            message = "length parameter must be defined for a fixed-type reference plane"
            assert length is not None, message
            message = "length parameter must be a float or an int"
            assert isinstance(length, (float, int)), message
            # format the plane
            plane = b.REFERENCE_PLANES_FORMAT.format(position=position,
                                                     type=types[plane_type],
                                                     length=length)
        else:
            raise NotImplementedError
        # add the reference plane to the geometry
        add_line(self['geometry']['reference_planes'], plane)

    def define_metal(self, metal_type, name, top=False, bottom=False, **kwargs):
        """
        Defines a metal that can be used in the project and sets the top and bottom box
        cover metals.

        :param metal_type: type of metal to add to the project (string)
            Valid types are listed below with any additional keyword arguments that may be
            used with them. Where ambiguous, the parameters' units are determined by the
            project level units.
            'waveguide load': only for the top and bottom layers.
            'free space': can only for the top and bottom layers.
            'normal': cannot be used for vias
            'resistor': cannot be used for vias
            'native': cannot be used for vias
            'general': cannot be used for vias
                r_dc: DC resistance [(m)Ohms/sq], zero by default (float)
                r_rf: skin effect coefficient [Ohms/sqrt(Hz)/sq], zero by default (float)
                x_dc: DC reactance [(m)Ohms/sq], zero by default (float)
                ls: surface inductance [pH/sq], zero by default (float)
            'sense': cannot be used for vias
            'thick metal': cannot be used for vias or the top and bottom layers
            'rough metal': cannot be used for vias or the top and bottom layers
            'volume loss': only for vias
            'surface loss': only for vias
            'array loss': only for vias
        :param name: metal name that must be unique in the project (string)
        :param top: determines if the metal is used for the top of the box (boolean)
        :param bottom: determines if the metal is used for the bottom of the box (boolean)
        """
        cover_types = ['waveguide load', 'free space', 'normal', 'resistor',
                       'native', 'general', 'sense']
        metal_types = cover_types.append(['thick metal', 'rough metal', 'volume loss',
                                          'surface loss', 'array loss'])
        # determine if the method needs to be run twice to set both the top and bottom
        if top and bottom:
            run_again = True
        else:
            run_again = False
        # check that valid types are given to top and bottom metals
        if top or bottom:
            cover_message = ("metals on the box top and bottom can only be of the "
                             "following types: {}").format(cover_types)
            assert metal_type in cover_types, cover_message
        # determine the pattern id and set the location string
        metals = self['geometry']['metals'].splitlines()
        if top:
            location = "TMET"
            replace = True
            pattern_id = 0
        elif bottom:
            location = "BMET"
            replace = True
            pattern_id = 0
        else:
            location = "MET"
            replace = False
            pattern_id = len(metals) - 2
        # if the top or bottom metal are being replaced keep the metal in the metals list
        if replace:
            names = [metal.split()[1].strip('"') for metal in metals]
            replace_metal = metals[0] if top else metals[1]
            replace_name = replace_metal.split()[1].strip('"')
            conditions = (replace_name not in names and replace_name != "Free Space" and
                          replace_name != "Freespace" and replace_name != "WG Load")
            if conditions:
                replace_metal = replace_metal.split()
                replace_metal[2] = len(metals) - 3
                replace_metal = " ".join(replace_metal)
                metals.append(replace_metal)
        # add the new metal to the metals list
        if metal_type == 'waveguide load':
            raise NotImplementedError
        elif metal_type == 'free space':
            metal = b.FREESPACE_FORMAT(location=location)
        elif metal_type == 'normal':
            raise NotImplementedError
        elif metal_type == 'resistor':
            raise NotImplementedError
        elif metal_type == 'native':
            raise NotImplementedError
        elif metal_type == 'general':
            r_dc = kwargs.pop('r_dc', 0)
            r_rf = kwargs.pop('r_rf', 0)
            x_dc = kwargs.pop('x_dc', 0)
            ls = kwargs.pop('ls', 0)
            metal = b.GENERAL_METAL_FORMAT.format(location=location, name=name,
                                                  pattern_id=pattern_id, r_dc=r_dc,
                                                  r_rf=r_rf, x_dc=x_dc, ls=ls)
        elif metal_type == 'sense':
            raise NotImplementedError
        elif metal_type == 'thick metal':
            raise NotImplementedError
        elif metal_type == 'rough metal':
            raise NotImplementedError
        elif metal_type == 'volume loss':
            raise NotImplementedError
        elif metal_type == 'surface loss':
            raise NotImplementedError
        elif metal_type == 'array loss':
            raise NotImplementedError
        else:
            message = "'metal_type' must be one of {}".format(metal_types)
            raise ValueError(message)
        metals = os.linesep.join(metals.append(metal))
        # add the metal definitions to the geometry
        self['geometry']['metals'] = metals
        # run again if the bottom layer needs to be set as well
        if run_again:
            self.define_metal(metal_type, name, top=False, bottom=True)

    def add_dimension(self):
        """Adds a dimension to the simulation geometry."""
        raise NotImplementedError

    def define_dielectric(self):
        """Defines a dielectric that can be used in the project."""
        raise NotImplementedError

    def add_variable(self, box_size_x=False, box_size_y=False):
        """Adds a variable to the project."""
        raise NotImplementedError

    def add_parameter(self):
        """Adds a dimension parameter to the project."""
        raise NotImplementedError

    def setup_box(self, box_width_x, box_width_y, x_cells, y_cells):
        """Set up box size and cell spacing.

        :param box_width_x: length of the box in the x direction (float)
        :param box_width_y: length of the box in the y direction (float)
        :param x_cells: number of cells in the x direction (int)
        :param y_cells: number of cells in the y direction (int)
        """
        self['box_width_x'] = float(box_width_x)
        self['box_width_y'] = float(box_width_y)
        self['x_cells2'] = 2 * int(x_cells)
        self['y_cells2'] = 2 * int(y_cells)

    def choose_layers(self):
        """Choose the dielectric layers to be used in the project."""
        raise NotImplementedError

    def define_technology_layer(self):
        """Defines a technology layer for the project."""
        raise NotImplementedError

    def add_edge_via(self):
        """Adds an edge via to the project."""
        raise NotImplementedError

    def set_origin(self):
        """Sets the origin for the project."""
        raise NotImplementedError

    def add_port(self):
        """Adds a port to the project."""
        raise NotImplementedError

    def add_calibration_group(self):
        """Adds a calibration group to the project."""
        raise NotImplementedError

    def add_component(self):
        """Adds a component to the project."""
        raise NotImplementedError

    def add_polygons(self):
        """Adds polygons to the project."""
        raise NotImplementedError

    def add_output_file(self, file_type, output_folder=None, deembed=True,
                        include_abs=True, include_comments=True, high_precision=True,
                        file_name=None, parameter_type='S', parameter_form='RI'):
        """
        Add an output file for the response data from the analysis of the project.

        :param file_type: output file type (string)
            Valid options are 'touchstone', 'touchstone2', 'databank', 'scompact',
            'spreadsheet'/'csv', 'cadance', 'mdif_s2p'/'mdif', and 'mdif_ebridge'.
        :param output_folder: relative path to where the data is saved (string)
            If no folder is chosen, data will be saved in the top level of the project
            directory. This option can only be set once per Project, and it's value is
            overwritten if selected again.
        :param deembed: save the deembeded data, defaults to True (boolean)
        :param include_abs: include the abs calculated data, defaults to True (boolean)
        :param include_comments: include comments in the file, defaults to True (boolean)
        :param high_precision: use high precision numbers, defaults to True (boolean)
        :param file_name: output data file name, defaults to the sonnet file name (string)
        :param parameter_type: type of parameter to output (string)
            Valid options are 'S' for the scattering parameters, 'Y' for the Y-parameters,
            and 'Z' for the Z-parameters.
        :param parameter_form: form of the output parameters (string)
            Valid options are 'MA' for magnitude-angle, 'DB' for dB-angle, and 'RI' for
            real-imaginary.
        """
        # check inputs
        file_types = {'touchstone': 'TS', 'TS': 'TS',
                      'touchstone2': 'TOUCH2', 'TOUCH2': 'TOUCH2',
                      'databank': 'DATA_BANK', 'DATA_BANK': 'DATA_BANK',
                      'scompact': 'SC', 'SC': 'SC',
                      'spreadsheet': 'CSV', 'csv': 'CSV', 'CSV': 'CSV',
                      'cadance': 'CADANCE', 'CADANCE': 'CADANCE',
                      'mdif_s2p': 'MDIF', 'mdif': 'MDIF', 'MDIF': 'MDIF',
                      'mdif_ebridge': 'EBMDIF', 'EBMDIF': 'EBMDIF'}
        message = "'file_type' parameter must be in {}".format(list(file_types.keys()))
        assert file_type in file_types.keys(), message
        message = "'parameter_type' parameter must be in {}".format(['S', 'Y', 'Z'])
        assert parameter_type in ['S', 'Y', 'Z'], message
        message = "'parameter_form' parameter must be in {}".format(['RI', 'MA', 'DB'])
        assert parameter_form in ['RI', 'MA', 'DB'], message
        # parse options
        deembed = 'D' if deembed else 'ND'
        include_abs = 'Y' if include_abs else 'N'
        include_comments = 'IC' if include_comments else 'NC'
        precision = 15 if high_precision else 8
        if file_name is None:
            file_name = '$BASENAME'
        # create ports string (defer if ports have not been made)
        if self._has_ports:
            raise NotImplementedError
        else:
            ports = "{ports}"
        # set the output folder if it was specified
        if output_folder is not None:
            self['output_file']['output_folder'] = output_folder
        # create output string
        output = b.RESPONSE_DATA_FORMAT.format(file_type=file_type,
                                               deembed=deembed,
                                               include_abs=include_abs,
                                               file_name=file_name,
                                               include_comments=include_comments,
                                               precision=precision,
                                               parameter_type=parameter_type,
                                               parameter_form=parameter_form,
                                               ports=ports)
        # add the output file to the project
        add_line(self['output_file']['response_data'], output)


class NetlistProject(Project):
    """
    Class for creating and manipulating a Sonnet netlist project.
    """
    # convert the project format to the file format
    def make_sonnet_file(self, file_path):
        file_string = (b.NETLIST_PROJECT.format(**self['sonnet']) +
                       b.HEADER.format(**self['sonnet']) +
                       b.DIMENSIONS.format(**self['dimensions']) +
                       b.FREQUENCY.format(**self['frequency']) +
                       b.CONTROL.format(**self['control']) +
                       b.OPTIMIZATION.format(**self['optimization']) +
                       b.PARAMETER_SWEEP.format(**self['parameter_sweep']) +
                       b.OUTPUT_FILE.format(**self['output_file']) +
                       b.PARAMETER_NETLIST.format(**self['parameter_netlist']) +
                       b.CIRCUIT.format(**self['circuit']) +
                       b.QUICK_START_GUIDE.format(**self['quick_start_guide']) +
                       b.COMPONENT_DATA_FILES.format(**self['component_data_files']) +
                       b.TRANSLATORS.format(**self['translators']))
        log.debug("saving netlist project to '{}'".format(file_path))
        with open(file_path, "w") as file_handle:
            file_handle.write(file_string)
        self.project_file_path = file_path
        log.debug("netlist project saved")

    def create_circuit(self):
        raise NotImplementedError
