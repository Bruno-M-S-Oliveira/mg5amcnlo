#############################################################################
#
# Copyright (c) 2009 The MadGraph5_aMC@NLO Development team and Contributors
#
# This file is a part of the MadGraph5_aMC@NLO project, an application which 
# automatically generates Feynman diagrams and matrix elements for arbitrary
# high-energy processes in the Standard Model and beyond.
#
# It is subject to the MadGraph5_aMC@NLO license which should accompany this 
# distribution.
#
# For more information, visit madgraph.phys.ucl.ac.be and amcatnlo.web.cern.ch
#
################################################################################
""" How to import a UFO model to the MG5 format """

from __future__ import absolute_import
import collections
import fractions
import inspect
import logging
import math
import os
import re
import sys
import time
import collections

import madgraph
from madgraph import MadGraph5Error, MG5DIR, ReadWrite
import madgraph.core.base_objects as base_objects
import madgraph.loop.loop_base_objects as loop_base_objects
import madgraph.core.color_algebra as color
import madgraph.iolibs.files as files
import madgraph.iolibs.save_load_object as save_load_object
from madgraph.core.color_algebra import *
import madgraph.various.misc as misc
import madgraph.iolibs.ufo_expression_parsers as parsers

import aloha
import aloha.create_aloha as create_aloha
import aloha.aloha_fct as aloha_fct
import aloha.aloha_object as aloha_object
import aloha.aloha_lib as aloha_lib
import models as ufomodels
import models.model_reader as model_reader
import six
from six.moves import range
from six.moves import zip
logger = logging.getLogger('madgraph.model')
logger_mod = logging.getLogger('madgraph.model')

root_path = os.path.dirname(os.path.realpath( __file__ ))
sys.path.append(root_path)

sys.path.append(os.path.join(root_path, os.path.pardir, 'Template', 'bin', 'internal'))
from . import check_param_card 

pjoin = os.path.join

# Suffixes to employ for the various poles of CTparameters
pole_dict = {-2:'2EPS',-1:'1EPS',0:'FIN'}

class UFOImportError(MadGraph5Error):
    """ a error class for wrong import of UFO model""" 

class InvalidModel(MadGraph5Error):
    """ a class for invalid Model """

last_model_path =''
def find_ufo_path(model_name, web_search=True):
    """ find the path to a model """

    global last_model_path

    # Check for a valid directory
    if model_name.startswith(('./','../')) and os.path.isdir(model_name):
        return model_name
    elif os.path.isdir(os.path.join(MG5DIR, 'models', model_name)):
        return os.path.join(MG5DIR, 'models', model_name)
    elif 'PYTHONPATH' in os.environ:
        for p in os.environ['PYTHONPATH'].split(':'):
            if os.path.isdir(os.path.join(MG5DIR, p, model_name)):
                if last_model_path != os.path.join(MG5DIR, p, model_name):
                    logger.info("model loaded from PYTHONPATH: %s", os.path.join(MG5DIR, p, model_name))
                    last_model_path = os.path.join(MG5DIR, p, model_name)
                return os.path.join(MG5DIR, p, model_name)
    if os.path.isdir(model_name):
        logger.warning('No model %s found in default path. Did you mean \'import model ./%s\'',
                       model_name, model_name)
        if os.path.sep in model_name:
            raise UFOImportError("Path %s is not a valid pathname" % model_name)    
    elif web_search and '-' not in model_name:
        found = import_model_from_db(model_name)
        if found:
            return find_ufo_path(model_name, web_search=False)
        else:
            raise UFOImportError("Path %s is not a valid pathname" % model_name)    
    else:
        raise UFOImportError("Path %s is not a valid pathname" % model_name)    
    
    raise UFOImportError("Path %s is not a valid pathname" % model_name)
    return


def get_model_db():
    """return the file with the online model database"""

    data_path = ['http://madgraph.phys.ucl.ac.be/models_db.dat',
                     'http://madgraph.mi.infn.it//models_db.dat']
    import random
    import six.moves.urllib.request, six.moves.urllib.parse, six.moves.urllib.error
    r = random.randint(0,1)
    r = [r, (1-r)]

    if 'MG5aMC_WWW' in os.environ and os.environ['MG5aMC_WWW']:
        data_path.append(os.environ['MG5aMC_WWW']+'/models_db.dat')
        r.insert(0, 2)


    for index in r:
        cluster_path = data_path[index]
        try:
            data = six.moves.urllib.request.urlopen(cluster_path)
        except Exception as err:
            misc.sprint(err)
            continue
        if data.getcode() != 200:
            continue
        break
    else:
        raise MadGraph5Error('''Model not found locally and Impossible to connect any of us servers.
        Please check your internet connection or retry later''')

    return data

def import_model_from_db(model_name, local_dir=False):
    """ import the model with a given name """

    if os.path.sep in model_name and os.path.exists(os.path.dirname(model_name)):
        target = os.path.dirname(model_name)
        model_name = os.path.basename(model_name)
    else:
        target = None
    data =get_model_db()
    link = None
    for line in data:
        split = line.decode(errors='ignore').split()
        if model_name == split[0]:
            link = split[1]
            break
    else:
        logger.debug('no model with that name (%s) found online', model_name)
        return False
    
    #get target directory
    # 1. PYTHONPATH containing UFO --only for omattelaer user
    # 2. models directory
    
    username = ''
    if not target:
        try:
            import pwd
            username =pwd.getpwuid( os.getuid() )[ 0 ]  
        except Exception as error:
            username = ''
    if username in ['omatt', 'mattelaer', 'olivier', 'omattelaer'] and target is None and \
                                    'PYTHONPATH' in os.environ and not local_dir:
        for directory in os.environ['PYTHONPATH'].split(':'):
            #condition only for my setup --ATLAS did not like it
            if 'UFOMODEL' == os.path.basename(directory) and os.path.exists(directory) and\
                misc.glob('*/couplings.py', path=directory) and 'matt' in directory:
                target= directory
                   
    if target is None:
        target = pjoin(MG5DIR, 'models')    
    try:
        os.remove(pjoin(target, 'tmp.tgz'))
    except Exception:
        pass
    logger.info("download model from %s to the following directory: %s", link, target, '$MG:color:BLACK')
    misc.wget(link, 'tmp.tgz', cwd=target)

    #untar the file.
    # .tgz
    if link.endswith(('.tgz','.tar.gz','.tar')):
        try:
            proc = misc.call('tar -xzpvf tmp.tgz', shell=True, cwd=target)#, stdout=devnull, stderr=devnull)
            if proc: raise Exception
        except:
            proc = misc.call('tar -xpvf tmp.tgz', shell=True, cwd=target)#, stdout=devnull, stderr=devnull)
    # .zip
    if link.endswith(('.zip')):
        try:
            proc = misc.call('unzip tmp.tgz', shell=True, cwd=target)#, stdout=devnull, stderr=devnull)
            if proc: raise Exception
        except:
            proc = misc.call('tar -xzpvf tmp.tgz', shell=True, cwd=target)#, stdout=devnull, stderr=devnull)
    if proc:
        raise Exception("Impossible to unpack the model. Please install it manually")
    return True

def get_path_restrict(model_name, restrict=True):
    # check if this is a valid path or if this include restriction file       
    try:
        model_path = find_ufo_path(model_name)
    except UFOImportError:
        if '-' not in model_name:
            if model_name == "mssm":
                logger.error("mssm model has been replaced by MSSM_SLHA2 model.\n The new model require SLHA2 format. You can use the \"update to_slha2\" command to convert your slha1 param_card.\n That option is available at the time of the edition of the cards.")
            raise
        split = model_name.split('-')
        model_name = '-'.join([text for text in split[:-1]])
        try:
            model_path = find_ufo_path(model_name)
        except UFOImportError:
            if model_name == "mssm":
                logger.error("mssm model has been replaced by MSSM_SLHA2 model.\n The new model require SLHA2 format. You can use the \"update to_slha2\" command to convert your slha1 param_card.\n That option is available at the time of the edition of the cards.")
            raise
        restrict_name = split[-1]
         
        restrict_file = os.path.join(model_path, 'restrict_%s.dat'% restrict_name)
        
        #if restriction is full, then we by pass restriction (avoid default)
        if split[-1] == 'full':
            restrict_file = None
    else:
        # Check if by default we need some restrictions
        restrict_name = ""
        if restrict and os.path.exists(os.path.join(model_path,'restrict_default.dat')):
            restrict_file = os.path.join(model_path,'restrict_default.dat')
        else:
            restrict_file = None

        if isinstance(restrict, str):
            if os.path.exists(os.path.join(model_path, restrict)):
                restrict_file = os.path.join(model_path, restrict)
            elif os.path.exists(restrict):
                restrict_file = restrict
            else:
                raise Exception("%s is not a valid path for restrict file" % restrict)
    
    return model_path, restrict_file, restrict_name

def import_model(model_name, decay=False, restrict=True, prefix='mdl_',
                                                    complex_mass_scheme = None,
                                                    options={}):
    """ a practical and efficient way to import a model"""
    
    model_path, restrict_file, restrict_name = get_path_restrict(model_name, restrict)
    
    #import the FULL model
    model = import_full_model(model_path, decay, prefix)

    if os.path.exists(pjoin(model_path, "README")):
        logger.info("Please read carefully the README of the model file for instructions/restrictions of the model.",'$MG:color:BLACK') 
    # restore the model name
    if restrict_name:
        model["name"] += '-' + restrict_name
    
    # Decide whether complex mass scheme is on or not
    useCMS = (complex_mass_scheme is None and aloha.complex_mass) or \
                                                      complex_mass_scheme==True
    #restrict it if needed       
    if restrict_file:
        try:
            logger.info('Restrict model %s with file %s .' % (model_name, os.path.relpath(restrict_file)))
        except OSError:
            # sometimes has trouble with relative path
            logger.info('Restrict model %s with file %s .' % (model_name, restrict_file))
            
        if logger_mod.getEffectiveLevel() > 10:
            logger.info('Run \"set stdout_level DEBUG\" before import for more information.')
        # Modify the mother class of the object in order to allow restriction
        model = RestrictModel(model)

        # Change to complex mass scheme if necessary. This must be done BEFORE
        # the restriction.
        if useCMS:
            # We read the param_card a first time so that the function 
            # change_mass_to_complex_scheme can know if a particle is to
            # be considered massive or not and with zero width or not.
            # So we read the restrict card a first time, with the CMS set to
            # False because we haven't changed the model yet.
            model.set_parameters_and_couplings(param_card = restrict_file,
                                                      complex_mass_scheme=False)
            if 'allow_qed_cms' in options and options['allow_qed_cms']:
                allow_qed = True
            else:
                allow_qed = False

            model.change_mass_to_complex_scheme(toCMS=True, bypass_check=allow_qed)
        else:
            # Make sure that the parameter 'CMSParam' of the model is set to 0.0
            # as it should in order to have the correct NWA renormalization condition.
            # It might be that the default of the model is CMS.
            model.change_mass_to_complex_scheme(toCMS=False)

        blocks = model.get_param_block()
        if model_name == 'mssm' or os.path.basename(model_name) == 'mssm':
            keep_external=True
        elif all( b in blocks for b in ['USQMIX', 'SL2', 'MSOFT', 'YE', 'NMIX', 'TU','MSE2','UPMNS']):
            keep_external=True
        elif model_name == 'MSSM_SLHA2' or os.path.basename(model_name) == 'MSSM_SLHA2':
            keep_external=True            
        else:
            keep_external=False
        if keep_external:
            logger.info('Detect SLHA2 format. keeping restricted parameter in the param_card')
            
        model.restrict_model(restrict_file, rm_parameter=not decay,
           keep_external=keep_external, complex_mass_scheme=complex_mass_scheme)
        model.path = model_path
    else:
        if 'allow_qed_cms' in options and options['allow_qed_cms']:
            allow_qed = True
        else:
            allow_qed = False
        # Change to complex mass scheme if necessary
        if useCMS:
            model.change_mass_to_complex_scheme(toCMS=True, bypass_check=allow_qed)
        else:
            # It might be that the default of the model (i.e. 'CMSParam') is CMS.
            model.change_mass_to_complex_scheme(toCMS=False, bypass_check=allow_qed)
      
    return model
    

_import_once = []
def import_full_model(model_path, decay=False, prefix=''):
    """ a practical and efficient way to import one of those models 
        (no restriction file use)"""

    assert model_path == find_ufo_path(model_path)
    
    if prefix is True:
        prefix='mdl_'
        
    # Check the validity of the model
    files_list_prov = ['couplings.py','lorentz.py','parameters.py',
                       'particles.py', 'vertices.py', 'function_library.py',
                       'propagators.py', 'coupling_orders.py']
    
    if decay:
        files_list_prov.append('decays.py')    
    
    files_list = []
    for filename in files_list_prov:
        filepath = os.path.join(model_path, filename)
        if not os.path.isfile(filepath):
            if filename not in ['propagators.py', 'decays.py', 'coupling_orders.py']:
                raise UFOImportError("%s directory is not a valid UFO model: \n %s is missing" % \
                                                         (model_path, filename))
        files_list.append(filepath)
    files_list.append(__file__) # include models/import_ufo.py itself, see mg5amcnlo/mg5amcnlo#89
    # use pickle files if defined and up-to-date
    if aloha.unitary_gauge == 1: 
        pickle_name = 'model.pkl'
    elif aloha.unitary_gauge == 3:
        pickle_name = 'model_FDG.pkl'
    else:
        pickle_name = 'model_Feynman.pkl'
    if decay:
        pickle_name = 'dec_%s' % pickle_name
    if six.PY3:
        pickle_name = 'py3_%s' % pickle_name
    
    allow_reload = False
    if files.is_uptodate(os.path.join(model_path, pickle_name), files_list):
        allow_reload = True
        try:
            model = save_load_object.load_from_file( \
                                          os.path.join(model_path, pickle_name))
        except Exception as error:
            logger.info('failed to load model from pickle file. Try importing UFO from File')
        else:
            # We don't care about the restrict_card for this comparison
            if 'version_tag' in model and not model.get('version_tag') is None and \
                model.get('version_tag').startswith(os.path.realpath(model_path)) and \
                model.get('version_tag').endswith('##' + str(misc.get_pkg_info())):
                #check if the prefix is correct one.
                for key in model.get('parameters'):
                    for param in model['parameters'][key]:
                        value = param.name.lower()
                        if value in ['as','mu_r', 'zero','aewm1']:
                            continue
                        if prefix:
                            if value.startswith(prefix):
                                _import_once.append((model_path, aloha.unitary_gauge, prefix, decay))
                                return model
                            else:
                                logger.info('reload from .py file')
                                break
                        else:
                            if value.startswith('mdl_'):
                                logger.info('reload from .py file')
                                break                   
                            else:
                                _import_once.append((model_path, aloha.unitary_gauge, prefix, decay))
                                return model
                    else:
                        continue
                    break                                         
            else:
                logger.info('reload from .py file')

    if (model_path, aloha.unitary_gauge, prefix, decay) in _import_once and not allow_reload:
        raise MadGraph5Error('This model %s is modified on disk. To reload it you need to quit/relaunch MG5_aMC ' % model_path)
     
    # Load basic information
    ufo_model = ufomodels.load_model(model_path, decay)
    ufo2mg5_converter = UFOMG5Converter(ufo_model)    
    model = ufo2mg5_converter.load_model()
    if model_path[-1] == '/': model_path = model_path[:-1] #avoid empty name
    model.set('name', os.path.split(model_path)[-1])

    # Load the Parameter/Coupling in a convenient format.
    parameters, couplings = OrganizeModelExpression(ufo_model).main(\
             additional_couplings =(ufo2mg5_converter.wavefunction_CT_couplings
                           if ufo2mg5_converter.perturbation_couplings else []))
    
    model.set('parameters', parameters)
    model.set('couplings', couplings)
    model.set('functions', ufo_model.all_functions)

    # Optional UFO part: decay_width information


    if decay and hasattr(ufo_model, 'all_decays') and ufo_model.all_decays:       
        start = time.time()
        for ufo_part in ufo_model.all_particles:
            name =  ufo_part.name
            if not model['case_sensitive']:
                name = name.lower() 
            p = model['particles'].find_name(name)
            if hasattr(ufo_part, 'partial_widths'):
                p.partial_widths = ufo_part.partial_widths
            elif p and not hasattr(p, 'partial_widths'):
                p.partial_widths = {}
            # might be None for ghost
        logger.debug("load width takes %s", time.time()-start)
    
    if prefix:
        start = time.time()
        model.change_parameter_name_with_prefix()
        logger.debug("model prefixing  takes %s", time.time()-start)
                     
    path = os.path.dirname(os.path.realpath(model_path))
    path = os.path.join(path, model.get('name'))
    model.set('version_tag', os.path.realpath(path) +'##'+ str(misc.get_pkg_info()))
    
    # save in a pickle files to fasten future usage
    if ReadWrite and model['allow_pickle']:
        save_load_object.save_to_file(os.path.join(model_path, pickle_name),
                                   model, log=False, allow_fail=True)

    #if default and os.path.exists(os.path.join(model_path, 'restrict_default.dat')):
    #    restrict_file = os.path.join(model_path, 'restrict_default.dat') 
    #    model = import_ufo.RestrictModel(model)
    #    model.restrict_model(restrict_file)

    return model

class UFOMG5Converter(object):
    """Convert a UFO model to the MG5 format"""

    def __init__(self, model, auto=False):
        """ initialize empty list for particles/interactions """

        if hasattr(model, '__header__'):
            header = model.__header__
            if len(header) > 500 or header.count('\n') > 5:
                logger.debug("Too long header")
            else:
                logger.info("\n"+header)
        else:
            f =collections.defaultdict(lambda : 'n/a')
            for key in ['author', 'version', 'email', 'arxiv']:
                if hasattr(model, '__%s__' % key):
                    val = getattr(model, '__%s__' % key)
                    if 'Duhr' in val:
                        continue
                    f[key] = getattr(model, '__%s__' % key)
                    
            if len(f)>2:
                logger.info("This model [version %(version)s] is provided by %(author)s (email: %(email)s). Please cite %(arxiv)s" % f, '$MG:color:BLACK')
            elif hasattr(model, '__arxiv__'):
                logger.info('Please cite %s when using this model', model.__arxiv__, '$MG:color:BLACK')
            
        self.particles = base_objects.ParticleList()
        self.interactions = base_objects.InteractionList()
        self.non_qcd_gluon_emission = 0 # vertex where a gluon is emitted withou QCD interaction
                                  # only trigger if all particles are of QCD type (not h>gg)
        self.colored_scalar = False # in presence of color scalar particle the running of a_s is modified
                                    # This is not supported by madevent/systematics
        self.wavefunction_CT_couplings = []
 
        # Check here if we can extract the couplings perturbed in this model
        # which indicate a loop model or if this model is only meant for 
        # tree-level computations
        self.perturbation_couplings = {}
        try:
            for order in model.all_orders:
                if(order.perturbative_expansion>0):
                    self.perturbation_couplings[order.name]=order.perturbative_expansion
        except AttributeError as error:
            pass

        if self.perturbation_couplings!={}:
            self.model = loop_base_objects.LoopModel({'perturbation_couplings':\
                                                list(self.perturbation_couplings.keys())})
        else:
            self.model = base_objects.Model()                        
        self.model.set('particles', self.particles)
        self.model.set('interactions', self.interactions)
        self.conservecharge = set(['charge'])
        
        self.ufomodel = model
        self.checked_lor = set()

        if hasattr(self.ufomodel, 'all_running_elements'):
            self.model.set('running_elements', self.ufomodel.all_running_elements)
        
        if auto:
            self.load_model()

    def load_model(self):
        """load the different of the model first particles then interactions"""

        # Check the validity of the model
        # 1) check that all lhablock are single word.
        def_name = []
        for param in self.ufomodel.all_parameters:
            if param.nature == "external":
                if len(param.lhablock.split())>1:
                    raise InvalidModel('''LHABlock should be single word which is not the case for
    \'%s\' parameter with lhablock \'%s\' ''' % (param.name, param.lhablock))
            if param.name in def_name:
                raise InvalidModel("name %s define multiple time. Please correct the UFO model!" \
                                                                  % (param.name))
            else:
                def_name.append(param.name)
                                                                  
        # For each CTParameter, check that there is no name conflict with the
        # set of re-defined CTParameters with EPS and FIN suffixes.
        if hasattr(self.ufomodel,'all_CTparameters'):
            for CTparam in self.ufomodel.all_CTparameters:
                for pole in pole_dict:
                    if CTparam.pole(pole)!='ZERO':
                        new_param_name = '%s_%s_'%(CTparam.name,pole_dict[pole])
                        if new_param_name in def_name:
                            raise InvalidModel("CT name %s"% (new_param_name)+\
                                           " the model. Please change its name.")

        if hasattr(self.ufomodel, 'gauge'):    
            self.model.set('gauge', self.ufomodel.gauge)
        logger.info('load particles')
        # Check if multiple particles have the same name but different case.
        # Otherwise, we can use lowercase particle names.
        if len(set([p.name for p in self.ufomodel.all_particles] + \
                   [p.antiname for p in self.ufomodel.all_particles])) == \
           len(set([p.name.lower() for p in self.ufomodel.all_particles] + \
                   [p.antiname.lower() for p in self.ufomodel.all_particles])):
            self.model['case_sensitive'] = False
            

        # check which of the fermion/anti-fermion should be set as incoming
        self.detect_incoming_fermion()

        for particle_info in self.ufomodel.all_particles:            
            self.add_particle(particle_info)

        if self.colored_scalar:
            logger.critical("Model with scalar colored particles. The running of alpha_s does not support such model.\n" + \
                             "You can ONLY run at fix scale")
            self.model['limitations'].append('fix_scale')

        # Find which particles is in the 3/3bar color states (retrun {id: 3/-3})
        color_info = self.find_color_anti_color_rep()

        # load the lorentz structure.
        self.model.set('lorentz', list(self.ufomodel.all_lorentz))
        
        # Substitute the expression of CT couplings which include CTparameters
        # in their definition with the corresponding dictionaries, e.g.
        #      CTCoupling.value = 2*CTParam           ->
        #      CTCoupling.value = {-1: 2*CTParam_1EPS_, 0: 2*CTParam_FIN_}
        # for example if CTParam had a non-zero finite and single pole.
        # This change affects directly the UFO model and it will be reverted in
        # OrganizeModelExpression only, so that the main() function of this class
        # *must* be run on the UFO to have this change reverted.
        if hasattr(self.ufomodel,'all_CTparameters'):
            logger.debug('Handling couplings defined with CTparameters...')
            start_treat_coupling = time.time()
            self.treat_couplings(self.ufomodel.all_couplings, 
                                                 self.ufomodel.all_CTparameters)
            tot_time = time.time()-start_treat_coupling
            if tot_time>5.0:
                logger.debug('... done in %s'%misc.format_time(tot_time))        

        logger.info('load vertices')
        for interaction_info in self.ufomodel.all_vertices:
            self.add_interaction(interaction_info, color_info)

        if aloha.unitary_gauge == 3:
            self.merge_all_goldstone_with_vector()

    
        if self.non_qcd_gluon_emission:
            logger.critical("Model with non QCD emission of gluon (found %i of those).\n  This type of model is not fully supported within MG5aMC.\n"+\
            "  Restriction on LO dynamical scale and MLM matching/merging can occur for some processes.\n"+\
            "  Use such features with care.", self.non_qcd_gluon_emission)

            self.model['allow_pickle'] = False 
            self.model['limitations'].append('MLM')
            
        if self.perturbation_couplings:
            try:
                self.ufomodel.add_NLO()
            except Exception as error:
                pass 

            for interaction_info in self.ufomodel.all_CTvertices:
                self.add_CTinteraction(interaction_info, color_info)
    

        for interaction in list(self.interactions):
            self.optimise_interaction(interaction)
            if not interaction['couplings']:
                self.interactions.remove(interaction)
    
    
        self.model.set('conserved_charge', self.conservecharge)

        # If we deal with a Loop model here, the order hierarchy MUST be 
        # defined in the file coupling_orders.py and we import it from 
        # there.
        all_orders = []
        try:
            all_orders = self.ufomodel.all_orders
        except AttributeError:
            if self.perturbation_couplings:
                raise MadGraph5Error("The loop model MG5 attemps to import does not specify the attribute 'all_order'.") 
            else:
                pass            

        hierarchy={}
        try:
            for order in all_orders:
                hierarchy[order.name]=order.hierarchy
        except AttributeError:
            if self.perturbation_couplings:
                raise MadGraph5Error('The loop model MG5 attemps to import does not specify an order hierarchy.') 
            else:
                pass
        else:
            self.model.set('order_hierarchy', hierarchy)            
        
        # Also set expansion_order, i.e., maximum coupling order per process
        expansion_order={}
        # And finally the UVCT coupling order counterterms        
        coupling_order_counterterms={}        
        try:
            for order in all_orders:
                expansion_order[order.name]=order.expansion_order
                coupling_order_counterterms[order.name]=order.expansion_order                
        except AttributeError:
            if self.perturbation_couplings:
                raise MadGraph5Error('The loop model MG5 attemps to import does not specify an expansion_order for all coupling orders.') 
            else:
                pass
        else:
            self.model.set('expansion_order', expansion_order)
            self.model.set('expansion_order', expansion_order)            
            
        #clean memory
        del self.checked_lor

        return self.model
    
    def optimise_interaction(self, interaction):
        
        
        #  Check if two couplings have exactly the same definition. 
        #  If so replace one by the other
        if not hasattr(self, 'iden_couplings'):
            coups = collections.defaultdict(list)
            coups['0'].append('ZERO')
            for coupling in self.ufomodel.all_couplings:
                #if isinstance(coupling.value, str):
                coups[str(coupling.value)].append( coupling.name)
            
            self.iden_couplings = {}
            for idens in [c for c in coups.values() if len(c)>1]:
                for i in range(1, len(idens)):
                    self.iden_couplings[idens[i]] = idens[0]

        # apply the replacement by identical expression
        for key, coup in list(interaction['couplings'].items()):
            if coup in self.iden_couplings:
                interaction['couplings'][key] = self.iden_couplings[coup] 
            if interaction['couplings'][key] == 'ZERO':
                del interaction['couplings'][key]
                
        
        # we want to check if the same coupling is used for two lorentz strucutre 
        # for the same color structure. 
        to_lor = {}
        for (color, lor), coup in interaction['couplings'].items():
            key = (color, coup)
            if key in to_lor:
                to_lor[key].append(lor)
            else:
                to_lor[key] = [lor]

        nb_reduce = []
        optimize = False
        for key in to_lor:
            if len(to_lor[key]) >1:
                nb_reduce.append(len(to_lor[key])-1)
                optimize = True
           
        if not optimize:
            return
        
        if not hasattr(self, 'defined_lorentz_expr'):
            self.defined_lorentz_expr = {}
            self.lorentz_info = {}
            self.lorentz_combine = {}
            for lor in self.model['lorentz']:
                self.defined_lorentz_expr[lor.get('structure')] = lor.get('name')
                self.lorentz_info[lor.get('name')] = lor #(lor.get('structure'), lor.get('spins'))
        
        for key in to_lor:
            if len(to_lor[key]) == 1:
                continue
            def get_spin(l):
                return self.lorentz_info[interaction['lorentz'][l]].get('spins')
                
            if any(get_spin(l1) != get_spin(to_lor[key][0]) for l1 in to_lor[key]):
                logger.warning('not all same spins for a given interactions')
                continue 

            names = [interaction['lorentz'][i] for i in to_lor[key]]
            names.sort()
            if self.lorentz_info[names[0]].get('structure') == 'external':
                continue
            # get name of the new lorentz
            if tuple(names) in self.lorentz_combine:
                # already created new loretnz
                new_name = self.lorentz_combine[tuple(names)]
            else:
                new_name = self.add_merge_lorentz(names)

            # remove the old couplings 
            color, coup = key
            to_remove = [(color, lor) for lor in to_lor[key]]  
            for rm in to_remove:
                del interaction['couplings'][rm]
                
            #add the lorentz structure to the interaction            
            if new_name not in [l for l in interaction.get('lorentz')]:
                interaction.get('lorentz').append(new_name)

            #find the associate index
            new_l = interaction.get('lorentz').index(new_name)
            # adding the new combination (color,lor) associate to this sum of structure
            interaction['couplings'][(color, new_l)] = coup  
                
    
    def merge_all_goldstone_with_vector(self):
        """For Feynman Diagram gauge need to merge interaction of scalar/boson"""

        # Here identify the pair and then delegates to another function
        # This routine also removes the goldstone from the list of particles of the model
        for particle in self.particles[:]:
            if particle.get('type') == 'goldstone':
                self.particles.remove(particle)
                vector = [p for p in self.particles if p.get('mass') == particle.get('mass')]
                if len(vector) != 1:
                    raise Exception("Failed to idendity goldstone/boson relation")
                
                self.merge_goldstone_with_vector(particle, vector[0])
                if not particle.get('self_antipart') and particle.get('is_part'):
                    particle = copy.copy(particle)
                    particle.set('is_part', False)
                    vector = copy.copy(vector[0])
                    vector.set('is_part', False)
                    self.merge_goldstone_with_vector(particle, vector)

    def merge_goldstone_with_vector(self, goldstone, vector):
        """For Feynman Diagram gauge need to merge interaction of scalar/boson
           In this routine we identify the interactions that needs to be merge into a single one.
           And delegate the actual merging to another routine
        """

                    
                    
        
        g_name = goldstone.get_name()
        v_name = vector.get_name()

        goldstone_interactions = [vertex for vertex in self.interactions if goldstone in  vertex.get('particles')]
        vector_interactions = [vertex for vertex in self.interactions 
                               if vector in vertex.get('particles') and
                               goldstone not in vertex.get('particles')]

        # create an easy way (dict) to find the equivalent vertex with boson
        search_int = {}
        for vertex in vector_interactions:
            names = tuple(sorted([p.get_name() for p in vertex.get('particles')]))
            if names in search_int:
                search_int[names].append(vertex)
            else:
                search_int[names] = [vertex]


        # now loop over goldstone interaction, identify if the a vector interactions
        # does exists and act accordingly (call dedicated routine)
        for vertex in goldstone_interactions:
            self.interactions.remove(vertex)

            #old_names = tuple(sorted([p.get_name() for p in vertex.get('particles')]))
            names = tuple(sorted([p.get_name() if p.get_name() != g_name else v_name
                      for p in vertex.get('particles')]))
            if names in search_int:
                self.update_vertex_for_goldstone(search_int[names], vertex, goldstone, vector)
            else:
                new_vertex = self.convert_goldstone_to_V(vertex, goldstone, vector)
                self.interactions.append(new_vertex)
                search_int[names] = [new_vertex]

        #raise Exception


    def convert_goldstone_to_V(self, vertex, goldstone, vector):
        """create a new vertex where goldstone are replace by the associated vector"""

        gold_vertex = copy.deepcopy(vertex)
        nb_vector = 0
        nb_gold = 0
        for p in vertex.get('particles'):
            if p.get_pdg_code() == goldstone.get_pdg_code():
                nb_gold += 1

        to_print=False
        if nb_gold != nb_vector:
            to_print=True

        particles_list = base_objects.ParticleList(vertex.get('particles'))
        for i, part in enumerate(vertex.get('particles')):
            if part == goldstone:
                particles_list[i] = vector
        vertex.set('particles', particles_list)

        for p in vertex.get('particles'):
            if p.get_pdg_code() == vector.get_pdg_code():
                nb_vector += 1

        if nb_vector != nb_gold:
            mappings = self.get_identical_goldstone_mapping(gold_vertex,vertex,goldstone, vector)
            for lorentz in list(vertex.get('lorentz')):
                for mapping in  mappings:
                    new_lorentz = self.get_symmetric_lorentz(str(lorentz), mapping)
                    new_lorentz_index = len(vertex.get('lorentz'))
                    vertex.get('lorentz').append(str(new_lorentz))
                    for (color, lorentz2), value in list(vertex.get('couplings').items()):
                        if vertex.get('lorentz')[lorentz2] != lorentz:
                            continue
                        vertex.get('couplings')[color, new_lorentz_index] = value            
            return vertex
        else:
            return vertex

    def reorder_vertex(self, vertex, mapping):
        """change the order of the particle within a given interaction"""

        new_vertex = copy.deepcopy(vertex)

        # reorder the particle within the new vertex
        old_particles = vertex.get('particles')
        new_particles = old_particles.__class__()
        for i in range(len(old_particles)):
            new_particles.append(old_particles[mapping[i]])
        new_vertex.set('particles', new_particles)

        restricted_mapping = {i:j for i,j in mapping.items() if i!=j}

        # change the lorentz structure within the new vertex
        all_lor = new_vertex.get('lorentz')
        for i,lor in enumerate(all_lor):
            new_lorentz = self.get_symmetric_lorentz(lor, restricted_mapping, change_number=True)
            all_lor[i] = str(new_lorentz)
        all_color = new_vertex.get('color')
        for i, col in enumerate(all_color):
            new_color = self.get_symmetric_color(str(col), restricted_mapping)
            if new_color not in  ['1 ','1 1']:
                all_color[i] = ColorString(new_color)

        return new_vertex


    @staticmethod
    def get_symmetric_color(old_color, substitution):
        """ """
        all_color_flag = ['f','d', 'Epsilon', 'EpsilonBar', 'K6', 'K6Bar', 'T', 'T6', 'Tr' ]
        split = re.split("(%s)\(([\d,\s\-\+]*)\)" % '|'.join(all_color_flag), old_color)
        new_expr = ''
        for i in range(len(split)):
            if i % 3 == 0:
                new_expr += split[i]
            if i % 3 == 1:
                new_expr += split[i]+'('
            if i %3 == 2:
                indices = split[i].split(',')
                for i, oneindex in enumerate(indices):
                    if int(oneindex) in substitution: # +1/-1 since not python ordering
                        indices[i] = str(substitution[int(oneindex)])

                new_expr += ','.join(indices)+')'
        return old_color.__class__(new_expr)



    def get_symmetric_lorentz(self, old_lorentz, substitution, change_number=False):
        """ """
        
        lor_orig = [l for l in self.model['lorentz'] if l.name==old_lorentz][0]
        FR_name = True 
        for key in substitution:
            if old_lorentz[key] not in ['S','V']:
                FR_name = False

        if not FR_name:
            raise Exception("need to think how to setup a name in this case. Please report")
        else:
            new_name = list(old_lorentz)
            for old,new in substitution.items():
                new_name[new] = old_lorentz[old]
            new_name = ''.join(new_name)

        if change_number:
            base = new_name[:len(lor_orig.spins)]
            try:
                index = int(new_name[len(lor_orig.spins):]) + 1
            except:
                base = new_name
                index = 1
            if not hasattr(self.model, 'lorentz_name2obj'):
                self.model.create_lorentz_dict()
            while str(base)+str(index) in self.model.lorentz_name2obj:
                index += 1
            new_name = str(base)+str(index)

        if not hasattr(self, 'all_aloha_obj'):
            self.all_aloha_obj = [n for n, obj in aloha_object.__dict__.items() 
                                  if inspect.isclass(obj) and issubclass(obj, aloha_lib.FactoryLorentz)]

        new_spins = list(lor_orig.spins)
        for old,new in substitution.items():
                new_spins[new] = lor_orig.spins[old]

        split = re.split("(%s)\(([\d,\s\-\+]*)\)" % '|'.join(self.all_aloha_obj), lor_orig.structure )
        new_expr = ''
        for i in range(len(split)):
            if i % 3 == 0:
                new_expr += split[i]
            if i % 3 == 1:
                new_expr += split[i]+'('
            if i %3 == 2:
                indices = split[i].split(',')
                for i, oneindex in enumerate(indices):
                    if int(oneindex)-1 in substitution: # +1/-1 since not python ordering
                        indices[i] = str(substitution[int(oneindex)-1]+1)

                new_expr += ','.join(indices)+')'
        
        new_formfact = lor_orig.formfactors if hasattr(lor_orig, 'formfactors') else None

        if change_number:
            #need to check that the new structure does not exists yet
            all_prev_expr = [(l.structure,l.spins) for l in self.model.get('lorentz')]
            if (new_expr,new_spins) in all_prev_expr:
                return self.model.get('lorentz')[all_prev_expr.index((new_expr,new_spins))]
            else:
                new_lor = self.add_lorentz(new_name, new_spins, new_expr, formfact=new_formfact)
        else:
            try:
                new_lor = self.add_lorentz(new_name, new_spins, new_expr, formfact=new_formfact)
            except AssertionError:
                prev_def = [l for l in self.model['lorentz'] if l.name==new_name][0]
                if prev_def.structure != new_expr:
                    misc.sprint("WARNING, two different definition for one lorentz name", prev_def.structure, new_expr)
                new_lor = prev_def
        return new_lor


    
    def update_vertex_for_goldstone(self, vertex, gold_vertex, goldstone, vector):
        """put the content of the gold_vertex within the vertex.
           So far we do assume that ordering is preserved between interaction
        """

        if len(vertex) !=1 :
            raise Exception
        vertex = vertex[0]

        nb_vector = 0
        nb_gold = 0
        for p in gold_vertex.get('particles'):
            if p.get_pdg_code() == goldstone.get_pdg_code():
                nb_gold += 1
        for p in vertex.get('particles'):
            if p.get_pdg_code() == vector.get_pdg_code():
                nb_vector += 1

        # need to check here if the ordering is the same.
        gold_pdg = [p.get_pdg_code() if p.get_pdg_code() != goldstone.get_pdg_code() else vector.get_pdg_code()
                    for p in gold_vertex.get('particles')]
        vert_pdg = [p.get_pdg_code() for p in vertex.get('particles')]

        # check if the order of the particle is the same
        if gold_pdg != vert_pdg:
            mapping = {}
            for orig in range(len(gold_pdg)):
                if vert_pdg[orig] == gold_pdg[orig]:
                    mapping[orig] = orig
                    vert_pdg[orig] = 0
            for orig in range(len(gold_pdg)):
                if orig in mapping:
                    continue
                new_pos = vert_pdg.index(gold_pdg[orig])
                mapping[orig] = new_pos
                vert_pdg[new_pos] = 0

            gold_vertex = self.reorder_vertex(gold_vertex, mapping)

        # check how to translate the color:
        # the translate_color track the index of the color in gold_vertex (key)
        # and the value is associate to the identical color in vertex. 
        # If that color does not exists it is added to the mix (should never happen. I guess)
        translate_color = {}
        for i, color in enumerate(gold_vertex.get('color')):
            if color in vertex.get('color'):
                translate_color[i] = vertex.get('color').index(color)
            else:
                misc.sprint("why a new color appear?", color, vertex.get('color'))
                raise Exception
                translate_color[i] = len(vertex.get('color'))
                vertex.get('color').append(color)
        
        # check now the lorentz structure. Some strategy as for the color
        # But lorentz structure should not repeat in principle...
        translate_lorentz = {}
        for i, lor in enumerate(gold_vertex.get('lorentz')):
            if lor in vertex.get('lorentz'):
                #raise Exception("lorentz should not repeat. Please report for investigation.")
                translate_lorentz[i] = vertex.get('lorentz').index(lor)
            else:
                translate_lorentz[i] = len(vertex.get('lorentz'))
                vertex.get('lorentz').append(lor)

        # now we can add the coupling to the original vertex
        for (color, lorentz), value in gold_vertex.get('couplings').items():
            key = (translate_color[color], translate_lorentz[lorentz])
            assert key not in vertex.get('couplings')
            vertex.get('couplings')[key] = value



        if nb_vector != nb_gold:
            mappings = self.get_identical_goldstone_mapping(gold_vertex,vertex,goldstone, vector)
            for mapping in mappings:
                color_map = {}
                for i, col in enumerate(gold_vertex.get('color')):
                    new_col = self.get_symmetric_color(str(col), mapping)
                    if new_col not in  ['1 ', '1 1']:
                        new_col = ColorString(new_col)
                    else:
                        color_map[i]=i
                        continue 
                    if new_col in vertex.get('color'):
                        new_col_index = vertex.get('color').index(new_col)
                    else:
                        new_col_index = len( vertex.get('color'))
                        vertex.get('color').append(new_col)
                    color_map[i] = new_col_index

                for lorentz in list(gold_vertex.get('lorentz')):
                    new_lorentz = self.get_symmetric_lorentz(lorentz, mapping)
                    new_lorentz_index = len(vertex.get('lorentz'))
                    if new_lorentz in vertex.get('lorentz'):
                        misc.sprint(lorentz)
                        misc.sprint(new_lorentz)
                        misc.sprint(vertex)
                        raise Exception("lorentz structure already in the vertex")
                    vertex.get('lorentz').append(str(new_lorentz))
                    for (color, lorentz2), value in list(vertex.get('couplings').items()):
                        if vertex.get('lorentz')[lorentz2] != lorentz:
                            continue
                        vertex.get('couplings')[color_map[color],new_lorentz_index] = value        

    def get_identical_goldstone_mapping(self, gold_vertex, v_vertex, goldstone, vector):
        """generate a mapping of the various possible assignment.
           This is called only if the number of particle does not match (so no need to check)
        """

        #input_pos=[i for i,p in enumerate(gold_vertex.get('particles')) if p.get_pdg_code() == goldstone.get_pdg_code()]
        final_pos=[i for i,p in enumerate(v_vertex.get('particles')) if p.get_pdg_code() == vector.get_pdg_code()]  
        pdgs = [p.get_pdg_code() for p in gold_vertex.get('particles')]
        valid = []
        for candidate in set(itertools.permutations(pdgs)):
            for i, pdg in enumerate(candidate):
                if i not in final_pos:
                    if pdg != pdgs[i]:
                        break
            else:
                valid.append(candidate) 
        # now that we have all the valid permutation, convert that to a dictionary of mappings
        # drop the identity permutation
        mappings = []
        for v in valid:
            if tuple(v) == tuple(pdgs):
                continue
            input_pos=[i for i,p in enumerate(gold_vertex.get('particles')) if p.get_pdg_code() == goldstone.get_pdg_code()]
            new_pos = [i for i in range(len(v)) if v[i] == goldstone.get_pdg_code()]
            mydict = {}#{i:i for i in range(len(v))}
            #check if they are overlap between input_pos and new_pos
            for i in input_pos:
                if i in new_pos:
                    input_pos.remove(i)
                    new_pos.remove(i)
            # now that identity is correctly handle, takes permutation of particle to the mapping
            for i in range(len(v)):
                if i in input_pos:
                    mydict[i] = new_pos.pop()
                    mydict[mydict[i]] = i
            mappings.append(mydict)
        return mappings

    def add_merge_lorentz(self, names):
        """add a lorentz structure which is the sume of the list given above"""
        
        
        #create new_name
        ii = len(names[0])
        while ii>0:
            if not all(n.startswith(names[0][:ii]) for n in names[1:]):
                ii -=1
            else:
                base_name = names[0][:ii]
                break
        else:
            base_name = 'LMER'
            
        i = 1
        while '%s%s' %(base_name, i) in self.lorentz_info:
            i +=1
        new_name = '%s%s' %(base_name, i)
        self.lorentz_combine[tuple(names)] = new_name
        assert new_name not in self.lorentz_info
        assert new_name not in [l.name for l in self.model['lorentz']]
        
        # load the associate lorentz expression
        new_struct = ' + '.join([self.lorentz_info[n].get('structure') for n in names])
        spins = self.lorentz_info[names[0]].get('spins')
        formfactors = sum([ self.lorentz_info[n].get('formfactors') for n in names \
                            if hasattr(self.lorentz_info[n], 'formfactors') \
                            and self.lorentz_info[n].get('formfactors') \
                      ],[])
                        
        new_lor = self.add_lorentz(new_name, spins, new_struct, formfactors)
        self.lorentz_info[new_name] = new_lor
        
        return new_name
                
                # We also have to create the new lorentz
                
                    
            
            
    
    def add_particle(self, particle_info):
        """ convert and add a particle in the particle list """
                
        loop_particles = [[[]]]
        counterterms = {}
        
        # MG5 have only one entry for particle and anti particles.
        #UFO has two. use the color to avoid duplictions
        pdg = particle_info.pdg_code
        if pdg in self.incoming or (pdg not in self.outcoming and pdg <0):
            return
        
        # MG5 doesn't use ghost for tree models: physical sum on the polarization
        if not self.perturbation_couplings and particle_info.spin < 0:
            return
        
        if (aloha.unitary_gauge in [1,2] and 0 in self.model['gauge']) \
                            or (1 not in self.model['gauge']): 
        
            # MG5 doesn't use goldstone boson 
            if hasattr(particle_info, 'GoldstoneBoson') and particle_info.GoldstoneBoson:
                return
            if hasattr(particle_info, 'goldstoneboson') and particle_info.goldstoneboson:
                return
            elif hasattr(particle_info, 'goldstone') and particle_info.goldstone:
                return
                  
        # Initialize a particles
        particle = base_objects.Particle()

        # MG5 doesn't use goldstone boson 
        if (hasattr(particle_info, 'GoldstoneBoson') and particle_info.GoldstoneBoson) \
                or (hasattr(particle_info, 'goldstoneboson') and particle_info.goldstoneboson):
            particle.set('type', 'goldstone')
        elif hasattr(particle_info, 'goldstone') and particle_info.goldstone:
            particle.set('type', 'goldstone')
        
        nb_property = 0   #basic check that the UFO information is complete
        # Loop over the element defining the UFO particles
        for key,value in particle_info.__dict__.items():
            # Check if we use it in the MG5 definition of a particles
            if key in base_objects.Particle.sorted_keys and not key=='counterterm':
                nb_property +=1
                if key in ['name', 'antiname']:
                    if not self.model['case_sensitive']:
                        particle.set(key, value.lower())
                    else:
                        particle.set(key, value)
                elif key == 'charge':
                    particle.set(key, float(value))
                elif key in ['mass','width']:
                    particle.set(key, str(value))
                elif key == 'spin':
                    # MG5 internally treats ghost with positive spin for loop models and 
                    # ignore them otherwise
                    particle.set(key,abs(value))
                    if value<0:
                        particle.set('type','ghost')
                elif key == 'propagating':
                    if not value:
                        particle.set('line', None)
                elif key == 'line':
                    if particle.get('line') is None:
                        pass # This means that propagating is on False 
                    else:
                        particle.set('line', value)
                elif key == 'propagator':
                    if value:
                        if isinstance(value, (list,dict)):
                            if aloha.unitary_gauge:
                                particle.set(key, str(value[0]))
                            else: 
                                particle.set(key, str(value[1]))
                        else:
                            particle.set(key, str(value))
                    else:
                        particle.set(key, '')
                else:
                    particle.set(key, value)    
            elif key == 'loop_particles':
                loop_particles = value
            elif key == 'counterterm':
                counterterms = value
            elif key.lower() not in ('ghostnumber','selfconjugate','goldstone',
                                             'goldstoneboson','partial_widths',
                                     'texname', 'antitexname', 'propagating', 'ghost'
                                             ):
                # add charge -we will check later if those are conserve 
                self.conservecharge.add(key)
                particle.set(key,value, force=True)

        if not hasattr(particle_info, 'propagator'):
            nb_property += 1
            if particle.get('spin') >= 3:
                if particle.get('mass').lower() == 'zero':
                    particle.set('propagator', 0) 
                elif particle.get('spin') == 3 and not aloha.unitary_gauge:
                    particle.set('propagator', 0)
               
        assert(10 == nb_property) #basic check that all the information is there         

        #check if we have scalar colored particle in the model -> issue with the running of alpha_s
        if particle['spin'] == 1 and particle['color'] != 1:
            if particle['type'] != 'ghost' and particle.get('mass').lower() == 'zero':
                self.colored_scalar = True

        
        # Identify self conjugate particles
        if particle_info.name == particle_info.antiname:
            particle.set('self_antipart', True)
                    
        # Proceed only if we deal with a loop model and that this particle
        # has wavefunction renormalization
        if not self.perturbation_couplings or counterterms=={}:
            self.particles.append(particle)
            return
        
        # Set here the 'counterterm' attribute to the particle.
        # First we must change the couplings dictionary keys from the entry format
        # (order1,order2,...,orderN,loop_particle#):LaurentSerie
        # two a dictionary with format 
        # ('ORDER_OF_COUNTERTERM',((Particle_list_PDG))):{laurent_order:CTCouplingName}
        particle_counterterms = {}
        for key, counterterm in counterterms.items():
            # Makes sure this counterterm contributes at one-loop.
            if len([1 for k in key[:-1] if k==1])==1 and \
               not any(k>1 for k in key[:-1]):
                newParticleCountertermKey=[None,\
#                  The line below is for loop UFO Model with the 'attribute' 
#                  'loop_particles' of the Particle objects to be defined with
#                  instances of the particle class. The new convention is to use
#                  pdg numbers instead.
#                  tuple([tuple([abs(part.pdg_code) for part in loop_parts]) for\
                  tuple([tuple(loop_parts) for\
                    loop_parts in loop_particles[key[-1]]])]
                for i, order in enumerate(self.ufomodel.all_orders[:-1]):
                    if key[i]==1:
                        newParticleCountertermKey[0]=order.name
                newCouplingName='UVWfct_'+particle_info.name+'_'+str(key[-1])
                particle_counterterms[tuple(newParticleCountertermKey)]=\
                  dict([(key,newCouplingName+('' if key==0 else '_'+str(-key)+'eps'))\
                        for key in counterterm])
                # We want to create the new coupling for this wavefunction
                # renormalization.
                self.ufomodel.object_library.Coupling(\
                    name = newCouplingName,
                    value = counterterm,
                    order = {newParticleCountertermKey[0]:2})
                self.wavefunction_CT_couplings.append(self.ufomodel.all_couplings.pop())

        particle.set('counterterm',particle_counterterms)
        self.particles.append(particle)
        return

    def treat_couplings(self, couplings, all_CTparameters):
        """ This function scan each coupling to see if it contains a CT parameter.
        when it does, it changes its value to a dictionary with the CT parameter
        changed to a new parameter for each pole and finite part. For instance,
        the following coupling:
              coupling.value = '2*(myCTParam1 + myParam*(myCTParam2 + myCTParam3)'
        with CTparameters
              myCTParam1 = {0: Something, -1: SomethingElse}
              myCTParam2 = {0: OtherSomething }
              myCTParam3 = {-1: YetOtherSomething }              
        would be turned into
              coupling.value = {0: '2*(myCTParam1_FIN_ + myParam*(myCTParam2_FIN_ + ZERO)'
                               -1: '2*(myCTParam1_EPS_ + myParam*(ZERO + myCTParam2_EPS_)'}              
        
        all_CTParameter is the list of all CTParameters in the model"""
        
        # First define a list of regular expressions for each CT parameter 
        # and put them in a dictionary whose keys are the CT parameter names
        # and the values are a tuple with the substituting patter in the first
        # entry and the list of substituting functions (one for each pole)
        # as the second entry of this tuple.
        CTparameter_patterns = {}
        zero_substitution = lambda matchedObj: matchedObj.group('first')+\
                                               'ZERO'+matchedObj.group('second')
        def function_factory(arg):
            return lambda matchedObj: \
                    matchedObj.group('first')+arg+matchedObj.group('second')
        for CTparam in all_CTparameters:
            pattern_finder = re.compile(r"(?P<first>\A|\*|\+|\-|\(|\s)(?P<name>"+
                        CTparam.name+r")(?P<second>\Z|\*|\+|\-|\)|/|\\|\s)")
            
            sub_functions = [None if CTparam.pole(pole)=='ZERO' else
                function_factory('%s_%s_'%(CTparam.name,pole_dict[-pole]))
                                                           for pole in range(3)]
            CTparameter_patterns[CTparam.name] = (pattern_finder,sub_functions)
        
        times_zero = re.compile(r'\*\s*-?ZERO')
        zero_times = re.compile(r'ZERO\s*(\*|\/)')
        def is_expr_zero(expresson):
            """ Checks whether a single term (involving only the operations
            * or / is zero. """
            for term in expresson.split('-'):
                for t in term.split('+'):
                    t = t.strip()
                    if t in ['ZERO','']:
                        continue
                    if not (times_zero.search(t) or zero_times.search(t)):
                        return False
            return True
        
        def find_parenthesis(expr):
            end = expr.find(')')
            if end == -1:
                return None
            start = expr.rfind('(',0,end+1)
            if start ==-1:
                raise InvalidModel('Parenthesis of expression %s are malformed'%expr)
            return [expr[:start],expr[start+1:end],expr[end+1:]]
        
        start_parenthesis = re.compile(r".*\s*[\+\-\*\/\)\(]\s*$")

        def is_value_zero(value):
            """Check whether an expression like ((A+B)*ZERO+C)*ZERO is zero.
            Only +,-,/,* operations are allowed and 'ZERO' is a tag for an
            analytically zero quantity."""

            curr_value = value
            parenthesis = find_parenthesis(curr_value)
            while parenthesis:
                # Allow the complexconjugate function
                if parenthesis[0].endswith('complexconjugate'):
                    # Then simply remove it
                    parenthesis[0] = parenthesis[0][:-16]
                if parenthesis[0]=='' or re.match(start_parenthesis,
                                                                parenthesis[0]):
                    if is_value_zero(parenthesis[1]):
                        new_parenthesis = 'ZERO'
                    else:
                        new_parenthesis = 'PARENTHESIS'
                else:
                    new_parenthesis = '_FUNCTIONARGS'
                curr_value = parenthesis[0]+new_parenthesis+parenthesis[2]
                parenthesis = find_parenthesis(curr_value)
            return is_expr_zero(curr_value)

        def CTCoupling_pole(CTCoupling, pole):
            """Compute the pole of the CTCoupling in two cases:
               a) Its value is a dictionary, then just return the corresponding
                  entry in the dictionary.
               b) It is expressed in terms of CTParameters which are themselves
                  dictionary so we want to substitute their expression to get
                  the value of the pole. In the current implementation, this is
                  just to see if the pole is zero or not.
            """
            
            if isinstance(CTCoupling.value,dict):
                if -pole in list(CTCoupling.value.keys()):
                    return CTCoupling.value[-pole], [], 0
                else:
                    return 'ZERO', [], 0              

            new_expression           = CTCoupling.value
            CTparamNames = []
            n_CTparams   = 0
            for paramname, value in CTparameter_patterns.items():
                pattern = value[0]
                # Keep track of which CT parameters enter in the definition of
                # which coupling.
                if not re.search(pattern,new_expression):
                    continue
                n_CTparams += 1
                # If the contribution of this CTparam to this pole is non
                # zero then the substituting function is not None:
                if not value[1][pole] is None:
                    CTparamNames.append('%s_%s_'%(paramname,pole_dict[-pole]))
  
                substitute_function = zero_substitution if \
                                      value[1][pole] is None else value[1][pole]
                new_expression = pattern.sub(substitute_function,new_expression)

            # If no CTParam was found and we ask for a pole, then it can only
            # be zero.
            if pole!=0 and n_CTparams==0:
                return 'ZERO', [], n_CTparams

            # Check if resulting expression is analytically zero or not.
            # Remember that when the value of a CT_coupling is not a dictionary
            # then the only operators allowed in the definition are +,-,*,/
            # and each term added or subtracted must contain *exactly one*
            # CTParameter and never at the denominator.   
            if n_CTparams > 0 and is_value_zero(new_expression):
                return 'ZERO', [], n_CTparams
            else:
                return new_expression, CTparamNames, n_CTparams

        # For each coupling we substitute its value if necessary
        for coupl in couplings:
            new_value = {}
            for pole in range(0,3):
                expression, CTparamNames, n_CTparams = CTCoupling_pole(coupl, pole)
                # Make sure it uses CT parameters, otherwise do nothing
                if n_CTparams == 0:
                    break
                elif expression!='ZERO':
                    new_value[-pole] = expression
                    couplname = coupl.name
                    if pole!=0:
                        couplname += "_%deps"%pole
                    # Add the parameter dependency found to the dependency map
                    # of the model being built. In principle, since we should
                    # be building a loop model now, it should always have this
                    # attribute defined, but it is better to make sure.
                    if hasattr(self.model, 'map_CTcoup_CTparam'):
                        self.model.map_CTcoup_CTparam[couplname] = CTparamNames
            

                    
            # Finally modify the value of this CTCoupling so that it is no
            # longer a string expression in terms of CTParameters but rather
            # a dictionary with the CTparameters replaced by their _FIN_ and
            # _EPS_ counterparts.
            # This is useful for the addCT_interaction() step. I will be reverted
            # right after the addCT_interaction() function so as to leave
            # the UFO intact, as it should. 
            if new_value:
                coupl.old_value = coupl.value
                coupl.value = new_value

        for CTparam in all_CTparameters:
            if CTparam.name not in self.model.map_CTcoup_CTparam:
                if not hasattr(self.model, "notused_ct_params"):
                    self.model.notused_ct_params = [CTparam.name.lower()]
                else:
                    self.model.notused_ct_params.append(CTparam.name.lower())

    def add_CTinteraction(self, interaction, color_info):
        """ Split this interaction in order to call add_interaction for
        interactions for each element of the loop_particles list. Also it
        is necessary to unfold here the contributions to the different laurent
        expansion orders of the couplings."""

        # Work on a local copy of the interaction provided
        interaction_info=copy.copy(interaction)
        
        intType=''
        if interaction_info.type not in ['UV','UVloop','UVtree','UVmass','R2']:
            raise MadGraph5Error('MG5 only supports the following types of'+\
              ' vertices, R2, UV and UVmass. %s is not in this list.'%interaction_info.type)
        else:
            intType=interaction_info.type
            # If not specified and simply set to UV, guess the appropriate type
            if interaction_info.type=='UV':
                if len(interaction_info.particles)==2 and interaction_info.\
                          particles[0].name==interaction_info.particles[1].name:
                    intType='UVmass'
                else:
                    intType='UVloop'
        
        # Make sure that if it is a UV mass renromalization counterterm it is
        # defined as such.
#        if len(intType)>2 and intType[:2]=='UV' and len(interaction_info.particles)==2 \
#           and interaction_info.particles[0].name==interaction_info.particles[1].name:
#            intType='UVmass'

        # Now we create a couplings dictionary for each element of the loop_particles list
        # and for each expansion order of the laurent serie in the coupling.
        # and for each coupling order
        # Format is new_couplings[loop_particles][laurent_order] and each element
        # is a couplings dictionary.
        order_to_interactions= {}
        # will contains the new coupling of form
        #new_couplings=[[{} for j in range(0,3)] for i in \
        #               range(0,max(1,len(interaction_info.loop_particles)))]
        # So sort all entries in the couplings dictionary to put them a the
        # correct place in new_couplings.
        for key, couplings in interaction_info.couplings.items():
            if not isinstance(couplings, list):
                couplings = [couplings]
            for coupling in couplings:
                order = tuple(coupling.order.items())
                if order not in order_to_interactions:
                    order_to_interactions[order] = [
                           [{} for j in range(0,3)] for i in \
                           range(0,max(1,len(interaction_info.loop_particles)))]
                    new_couplings = order_to_interactions[order]
                else:
                    new_couplings = order_to_interactions[order]
                    
                for poleOrder in range(0,3):
                    expression = coupling.pole(poleOrder)
                    if expression!='ZERO':
                        if poleOrder==2:
                            raise InvalidModel("""
    The CT coupling %s was found with a contribution to the double pole. 
    This is either an error in the model or a parsing error in the function 'is_value_zero'.
    The expression of the non-zero double pole coupling is:
    %s
    """%(coupling.name,str(coupling.value)))
                        # It is actually safer that the new coupling associated to
                        # the interaction added is not a reference to an original 
                        # coupling in the ufo model. So copy.copy is right here.   
                        newCoupling = copy.copy(coupling)
                        if poleOrder!=0:
                            newCoupling.name=newCoupling.name+"_"+str(poleOrder)+"eps"
                        newCoupling.value = expression
                        # assign the CT parameter dependences
                        #if hasattr(coupling,'CTparam_dependence') and \
                        #        (-poleOrder in coupling.CTparam_dependence) and \
                        #        coupling.CTparam_dependence[-poleOrder]:
                        #    newCoupling.CTparam_dependence = coupling.CTparam_dependence[-poleOrder]
                        #elif hasattr(newCoupling,'CTparam_dependence'):
                        #    delattr(newCoupling,"CTparam_dependence")
                        new_couplings[key[2]][poleOrder][(key[0],key[1])] = newCoupling  
            
        for new_couplings in order_to_interactions.values():
            # Now we can add an interaction for each.         
            for i, all_couplings in enumerate(new_couplings):
                loop_particles=[[]]
                if len(interaction_info.loop_particles)>0:
                    loop_particles=[[part.pdg_code for part in loop_parts] \
                        for loop_parts in interaction_info.loop_particles[i]]
                for poleOrder in range(0,3):
                    if all_couplings[poleOrder]!={}:
                        interaction_info.couplings=all_couplings[poleOrder]
                        self.add_interaction(interaction_info, color_info,\
                          (intType if poleOrder==0 else (intType+str(poleOrder)+\
                                                             'eps')),loop_particles)

    def find_color_anti_color_rep(self, output=None):
        """find which color are in the 3/3bar states"""
        # method look at the 3 3bar 8 configuration.
        # If the color is T(3,2,1) and the interaction F1 F2 V
        # Then set F1 to anticolor (and F2 to color)
        # if this is T(3,1,2) set the opposite
        if not output:
            output = {}
             
        for interaction_info in self.ufomodel.all_vertices:
            if len(interaction_info.particles) != 3:
                continue
            colors = [abs(p.color) for p in interaction_info.particles]
            if colors[:2] == [3,3]:
                if 'T(3,2,1)' in interaction_info.color:
                    color, anticolor, other = interaction_info.particles
                elif 'T(3,1,2)' in interaction_info.color:
                    anticolor, color, _ = interaction_info.particles
                elif 'Identity(1,2)' in interaction_info.color  or \
                     'Identity(2,1)' in interaction_info.color:
                    first, second, _ = interaction_info.particles
                    if first.pdg_code in output:
                        if output[first.pdg_code] == 3:
                            color, anticolor = first, second
                        else:
                            color, anticolor = second, first
                    elif second.pdg_code in output:
                        if output[second.pdg_code] == 3:
                            color, anticolor = second, first                        
                        else:
                            color, anticolor = first, second
                    else:
                        continue
                else:
                    continue
            elif colors[1:] == [3,3]:
                if 'T(1,2,3)' in interaction_info.color:
                    other, anticolor, color = interaction_info.particles
                elif 'T(1,3,2)' in interaction_info.color:
                    other, color, anticolor = interaction_info.particles
                elif 'Identity(2,3)' in interaction_info.color  or \
                     'Identity(3,2)' in interaction_info.color:
                    _, first, second = interaction_info.particles
                    if first.pdg_code in output:
                        if output[first.pdg_code] == 3:
                            color, anticolor = first, second
                        else:
                            color, anticolor = second, first
                    elif second.pdg_code in output:
                        if output[second.pdg_code] == 3:
                            color, anticolor = second, first                        
                        else:
                            color, anticolor = first, second
                    else:
                        continue
                else:
                    continue                  
               
            elif colors.count(3) == 2:
                if 'T(2,3,1)' in interaction_info.color:
                    color, other, anticolor = interaction_info.particles
                elif 'T(2,1,3)' in interaction_info.color:
                    anticolor, other, color = interaction_info.particles
                elif 'Identity(1,3)' in interaction_info.color  or \
                     'Identity(3,1)' in interaction_info.color:
                    first, _, second = interaction_info.particles
                    if first.pdg_code in output:
                        if output[first.pdg_code] == 3:
                            color, anticolor = first, second
                        else:
                            color, anticolor = second, first
                    elif second.pdg_code in output:
                        if output[second.pdg_code] == 3:
                            color, anticolor = second, first                        
                        else:
                            color, anticolor = first, second
                    else:
                        continue
                else:
                    continue                 
            else:
                continue    
            
            # Check/assign for the color particle
            if color.pdg_code in output: 
                if output[color.pdg_code] == -3:
                    raise InvalidModel('Particles %s is sometimes in the 3 and sometimes in the 3bar representations' \
                                    % color.name)
            else:
                output[color.pdg_code] = 3
            
            # Check/assign for the anticolor particle
            if anticolor.pdg_code in output: 
                if output[anticolor.pdg_code] == 3:
                    raise InvalidModel('Particles %s is sometimes set as in the 3 and sometimes in the 3bar representations' \
                                    % anticolor.name)
            else:
                output[anticolor.pdg_code] = -3
        
        return output
    
    def detect_incoming_fermion(self):
        """define which fermion should be incoming
           for that we look at F F~ X interactions
        """
        self.incoming = [] 
        self.outcoming = []       
        for interaction_info in self.ufomodel.all_vertices:
            # check if the interaction meet requirements:
            pdg = [p.pdg_code for p in interaction_info.particles if p.spin in [2,4]]
            if len(pdg) % 2:
                raise InvalidModel('Odd number of fermion in vertex: %s' % [p.pdg_code for p in interaction_info.particles])
            for i in range(0, len(pdg),2):
                if pdg[i] == - pdg[i+1]:
                    if pdg[i] in self.outcoming:
                        raise InvalidModel('%s has not coherent incoming/outcoming status between interactions' %\
                            [p for p in interaction_info.particles if p.spin in [2,4]][i].name)
                            
                    elif not pdg[i] in self.incoming:
                        self.incoming.append(pdg[i])
                        self.outcoming.append(pdg[i+1])
                     
    def add_interaction(self, interaction_info, color_info, type='base', loop_particles=None):            
        """add an interaction in the MG5 model. interaction_info is the 
        UFO vertices information."""
        # Import particles content:
        particles = [self.model.get_particle(particle.pdg_code) \
                                    for particle in interaction_info.particles]
        if None in particles:
            # Interaction with a ghost/goldstone
            return 
        particles = base_objects.ParticleList(particles)

        # Import Lorentz content:
        lorentz = [helas for helas in interaction_info.lorentz]            
        
        # Check the coherence of the Fermion Flow
        nb_fermion = sum([ 1 if p.is_fermion() else 0 for p in particles])
        try:
            if nb_fermion == 2:
                # Fermion Flow is suppose to be dealt by UFO
                [aloha_fct.check_flow_validity(helas.structure, nb_fermion) \
                                          for helas in interaction_info.lorentz
                                          if helas.name not in self.checked_lor]
                self.checked_lor.update(set([helas.name for helas in interaction_info.lorentz]))
            elif nb_fermion:
                if any(p.selfconjugate for p in interaction_info.particles if p.spin % 2 == 0):
                    text = "Majorana can not be dealt in 4/6/... fermion interactions"
                    raise InvalidModel(text)
        except aloha_fct.WrongFermionFlow as error:
            text = 'Fermion Flow error for interactions %s: %s: %s\n %s' % \
             (', '.join([p.name for p in interaction_info.particles]), 
                                             helas.name, helas.structure, error)
            raise InvalidModel(text)
        
     
        
        
        # Now consider the name only
        lorentz = [helas.name for helas in lorentz] 
        # Import color information:
        colors = [self.treat_color(color_obj, interaction_info, color_info) 
                                    for color_obj in interaction_info.color]
        
        
        order_to_int={}

        for key, couplings in interaction_info.couplings.items():
            if not isinstance(couplings, list):
                couplings = [couplings]
            if interaction_info.lorentz[key[1]].name not in lorentz:
                continue 
            # get the sign for the coupling (if we need to adapt the flow)
            if nb_fermion > 2:
                flow = aloha_fct.get_fermion_flow(interaction_info.lorentz[key[1]].structure, 
                                                                     nb_fermion)
                coupling_sign = self.get_sign_flow(flow, nb_fermion)
            else:                
                coupling_sign = ''            
            for coupling in couplings:
                order = tuple(coupling.order.items())
                if '1' in coupling.order:
                    raise InvalidModel('''Some couplings have \'1\' order. 
                    This is not allowed in MG. 
                    Please defines an additional coupling to your model''') 

                # check that gluon emission from quark are QCD tagged
                if 21 in [particle.pdg_code for particle in interaction_info.particles] and\
                    'QCD' not in  coupling.order:
                    col = [par.get('color') for par in particles]
                    if 1 not in col:
                        self.non_qcd_gluon_emission +=1
       
                if order in order_to_int:
                    order_to_int[order].get('couplings')[key] = '%s%s' % \
                                               (coupling_sign,coupling.name)
                else:
                    # Initialize a new interaction with a new id tag
                    interaction = base_objects.Interaction({'id':len(self.interactions)+1})                
                    interaction.set('particles', particles)              
                    interaction.set('lorentz', lorentz)
                    interaction.set('couplings', {key: 
                                     '%s%s' %(coupling_sign,coupling.name)})
                    interaction.set('orders', coupling.order)            
                    interaction.set('color', colors)
                    interaction.set('type', type)
                    interaction.set('loop_particles', loop_particles)                    
                    order_to_int[order] = interaction                        
                    # add to the interactions
                    self.interactions.append(interaction)

            
        # check if this interaction conserve the charge defined
 #       if type=='base':
        for charge in list(self.conservecharge): #duplicate to allow modification
            total = 0
            for part in interaction_info.particles:
                try:
                    total += getattr(part, charge)
                except AttributeError:
                    pass
            if abs(total) > 1e-12:
                logger.info('The model has interaction violating the charge: %s' % charge)
                self.conservecharge.discard(charge)

        
        
    def get_sign_flow(self, flow, nb_fermion):
        """ensure that the flow of particles/lorentz are coherent with flow 
           and return a correct version if needed"""
           
        if not flow or nb_fermion < 4:
            return ''
           
        expected = {}
        for i in range(nb_fermion//2):
            expected[i+1] = i+2
        
        if flow == expected:
            return ''

        switch = {}
        for i in range(1, nb_fermion+1):
            if not i in flow:
                continue
            switch[i] = len(switch)
            switch[flow[i]] = len(switch)

        # compute the sign of the permutation
        sign = 1
        done = []
   
        # make a list of consecutive number which correspond to the new
        # order of the particles in the new list.
        new_order = []
        for id in range(nb_fermion): # id is the position in the particles order (starts 0)
            nid = switch[id+1]-1 # nid is the position in the new_particles 
                                 #order (starts 0)
            new_order.append(nid)
             
        # compute the sign:
        sign =1
        for k in range(len(new_order)-1):
            for l in range(k+1,len(new_order)):
                if new_order[l] < new_order[k]:
                    sign *= -1     
                    
        return  '' if sign ==1 else '-'

    def add_lorentz(self, name, spins , expr, formfact=None):
        """ Add a Lorentz expression which is not present in the UFO """

        logger.debug('MG5 converter defines %s to %s', name, expr)
        assert name not in [l.name for l in self.model['lorentz']]
        with misc.TMP_variable(self.ufomodel.object_library, 'all_lorentz', 
                               self.model['lorentz']):
            new = self.model['lorentz'][0].__class__(name = name,
                    spins = spins,
                    structure = expr)
            if formfact:
                new.formfactors = formfact
            if self.model['lorentz'][-1].name != name:
                self.model['lorentz'].append(new)
            if name in [l.name for l in self.ufomodel.all_lorentz]:
                self.ufomodel.all_lorentz.remove(new)

        assert name in [l.name for l in self.model['lorentz']]
        assert name not in [l.name for l in self.ufomodel.all_lorentz]
        #self.model['lorentz'].append(new) # already done by above command
        self.model.create_lorentz_dict()
        return new
    
    _pat_T = re.compile(r'T\((?P<first>\d*),(?P<second>\d*)\)')
    _pat_id = re.compile(r'Identity\((?P<first>\d*),(?P<second>\d*)\)')
    
    def treat_color(self, data_string, interaction_info, color_info):
        """ convert the string to ColorString"""
        
        #original = copy.copy(data_string)
        #data_string = p.sub('color.T(\g<first>,\g<second>)', data_string)
        
        output = []
        factor = 1
        for term in data_string.split('*'):
            pattern = self._pat_id.search(term)
            if pattern:
                particle = interaction_info.particles[int(pattern.group('first'))-1]
                particle2 = interaction_info.particles[int(pattern.group('second'))-1]
                if particle.color == particle2.color and particle.color in [-6, 6]:
                    error_msg = 'UFO model have inconsistency in the format:\n'
                    error_msg += 'interactions for  particles %s has color information %s\n'
                    error_msg += ' but both fermion are in the same representation %s'
                    raise InvalidModel(error_msg % (', '.join([p.name for p in interaction_info.particles]),data_string, particle.color))
                if particle.color == particle2.color and particle.color in [-3, 3]:
                    if particle.pdg_code in color_info and particle2.pdg_code in color_info:
                      if color_info[particle.pdg_code] == color_info[particle2.pdg_code]:
                        error_msg = 'UFO model have inconsistency in the format:\n'
                        error_msg += 'interactions for  particles %s has color information %s\n'
                        error_msg += ' but both fermion are in the same representation %s'
                        raise InvalidModel(error_msg % (', '.join([p.name for p in interaction_info.particles]),data_string, particle.color))
                    elif particle.pdg_code in color_info:
                        color_info[particle2.pdg_code] = -particle.pdg_code
                    elif particle2.pdg_code in color_info:
                        color_info[particle.pdg_code] = -particle2.pdg_code
                    else:
                        error_msg = 'UFO model have inconsistency in the format:\n'
                        error_msg += 'interactions for  particles %s has color information %s\n'
                        error_msg += ' but both fermion are in the same representation %s'
                        raise InvalidModel(error_msg % (', '.join([p.name for p in interaction_info.particles]),data_string, particle.color))
                
                
                if particle.color == 6:
                    output.append(self._pat_id.sub(r'color.T6(\g<first>,\g<second>)', term))
                elif particle.color == -6 :
                    output.append(self._pat_id.sub(r'color.T6(\g<second>,\g<first>)', term))
                elif particle.color == 8:
                    output.append(self._pat_id.sub(r'color.Tr(\g<first>,\g<second>)', term))
                    factor *= 2
                elif particle.color in [-3,3]:
                    if particle.pdg_code not in color_info:
                        #try to find it one more time 3 -3 1 might help
                        logger.debug('fail to find 3/3bar representation: Retry to find it')
                        color_info = self.find_color_anti_color_rep(color_info)
                        if particle.pdg_code not in color_info:
                            logger.debug('Not able to find the 3/3bar rep from the interactions for particle %s' % particle.name)
                            color_info[particle.pdg_code] = particle.color
                        else:
                            logger.debug('succeed')
                    if particle2.pdg_code not in color_info:
                        #try to find it one more time 3 -3 1 might help
                        logger.debug('fail to find 3/3bar representation: Retry to find it')
                        color_info = self.find_color_anti_color_rep(color_info)
                        if particle2.pdg_code not in color_info:
                            logger.debug('Not able to find the 3/3bar rep from the interactions for particle %s' % particle2.name)
                            color_info[particle2.pdg_code] = particle2.color                    
                        else:
                            logger.debug('succeed')
                
                    if color_info[particle.pdg_code] == 3 :
                        output.append(self._pat_id.sub(r'color.T(\g<second>,\g<first>)', term))
                    elif color_info[particle.pdg_code] == -3:
                        output.append(self._pat_id.sub(r'color.T(\g<first>,\g<second>)', term))
                else:
                    raise MadGraph5Error("Unknown use of Identity for particle with color %d" \
                          % particle.color)
            else:
                output.append(term)
        data_string = '*'.join(output)

        # Change convention for summed indices
        p = re.compile(r'\'\w(?P<number>\d+)\'')
        data_string = p.sub(r'-\g<number>', data_string)
         
        # Shift indices by -1
        new_indices = {}
        new_indices = dict([(j,i) for (i,j) in \
                           enumerate(range(1,
                                    len(interaction_info.particles)+1))])

                        
        output = data_string.split('*')
        output = color.ColorString([eval(data) \
                                    for data in output if data !='1'])
        output.coeff = fractions.Fraction(factor)
        for col_obj in output:
            col_obj.replace_indices(new_indices)

        return output
      
class OrganizeModelExpression:
    """Organize the couplings/parameters of a model"""
    
    track_dependant = ['aS','aEWM1','MU_R'] # list of variable from which we track 
                                   #dependencies those variables should be define
                                   #as external parameters
    
    # regular expression to shorten the expressions
    complex_number = re.compile(r'''complex\((?P<real>[^,\(\)]+),(?P<imag>[^,\(\)]+)\)''')
    expo_expr = re.compile(r'''(?P<expr>[\w.]+)\s*\*\*\s*(?P<expo>[+-]?[\d.]+)''')
    cmath_expr = re.compile(r'''cmath.(?P<operation>\w+)\((?P<expr>\w+)\)''')
    #operation is usualy sqrt / sin / cos / tan
    conj_expr = re.compile(r'''complexconjugate\((?P<expr>\w+)\)''')
    
    #RE expression for is_event_dependent
    separator = re.compile(r'''[+,\-*/()\s]+''')
    
    
    def __init__(self, model):
    
        self.model = model  # UFOMODEL
        self.perturbation_couplings = {}
        try:
            for order in model.all_orders: # Check if it is a loop model or not
                if(order.perturbative_expansion>0):
                    self.perturbation_couplings[order.name]=order.perturbative_expansion
        except AttributeError:
            pass
        self.params = {}     # depend on -> ModelVariable
        self.couplings = {}  # depend on -> ModelVariable
        self.all_expr = {} # variable_name -> ModelVariable
        
        if hasattr(self.model, 'all_running_elements'):
            all_elements = set()
            for runs in self.model.all_running_elements:
                for line_run in runs.run_objects:
                    for one_element in line_run:
                        all_elements.add(one_element.name)
            all_elements.union(self.track_dependant)
            self.track_dependant = list(all_elements)
        
    
    def main(self, additional_couplings = []):
        """Launch the actual computation and return the associate 
        params/couplings. Possibly consider additional_couplings in addition
        to those defined in the UFO model attribute all_couplings """

        additional_params = []
        if hasattr(self.model,'all_CTparameters'):
            additional_params = self.get_additional_CTparameters()

        self.analyze_parameters(additional_params = additional_params)
        self.analyze_couplings(additional_couplings = additional_couplings)
        
        # Finally revert the possible modifications done by treat_couplings()
        if hasattr(self.model,'all_CTparameters'):
            self.revert_CTCoupling_modifications()

        return self.params, self.couplings

    def revert_CTCoupling_modifications(self):
        """ Finally revert the possible modifications done by treat_couplings()
        in UFOMG5Converter which were useful for the add_CTinteraction() in 
        particular. This modification consisted in expanding the value of a
        CTCoupling which consisted in an expression in terms of a CTParam to 
        its corresponding dictionary (e.g 
              CTCoupling.value = 2*CTParam           ->
              CTCoupling.value = {-1: 2*CTParam_1EPS_, 0: 2*CTParam_FIN_}
        for example if CTParam had a non-zero finite and single pole."""
        
        for coupl in self.model.all_couplings:
            if hasattr(coupl,'old_value'):
                coupl.value = coupl.old_value
                del(coupl.old_value)

    def get_additional_CTparameters(self):
        """ For each CTparameter split it into spimple parameter for each pole
        and the finite part if not zero."""

        additional_params = []
        for CTparam in self.model.all_CTparameters:
            for pole in range(3):
                if CTparam.pole(pole) != 'ZERO':
                  CTparam_piece = copy.copy(CTparam)
                  CTparam_piece.name = '%s_%s_'%(CTparam.name,pole_dict[-pole])
                  CTparam_piece.nature = 'internal'
                  CTparam_piece.type = CTparam.type
                  CTparam_piece.value = CTparam.pole(pole)
                  CTparam_piece.texname = '%s_{%s}'%\
                                              (CTparam.texname,pole_dict[-pole])
                  additional_params.append(CTparam_piece)
        return additional_params

    def analyze_parameters(self, additional_params=[]):
        """ separate the parameters needed to be recomputed events by events and
        the others"""
        # in order to match in Gmu scheme
        # test whether aEWM1 is the external or not
        # if not, take Gf as the track_dependant variable
        present_aEWM1 = any(param.name == 'aEWM1' for param in
                        self.model.all_parameters if param.nature == 'external')
   
        if not present_aEWM1:
            self.track_dependant += ['Gf']
            self.track_dependant = list(set(self.track_dependant))
        p = self.model.all_parameters[0]

        mu_eff = list(set([param.name for param in self.model.all_parameters 
                    if (param.nature == 'external' and
                        param.lhablock.lower() == 'loop' and
                        param.name != 'MU_R'
                        )]))
        self.track_dependant += mu_eff


        for param in self.model.all_parameters+additional_params:
            if param.nature == 'external':
                parameter = base_objects.ParamCardVariable(param.name, param.value, \
                                               param.lhablock, param.lhacode, 
                                               param.scale if hasattr(param,'scale') else None)
                
            else:
                expr = self.shorten_expr(param.value)
                depend_on = self.find_dependencies(expr)
                parameter = base_objects.ModelVariable(param.name, expr, param.type, depend_on)
            
            self.add_parameter(parameter)  
           
            
    def add_parameter(self, parameter):
        """ add consistently the parameter in params and all_expr.
        avoid duplication """
        
        assert isinstance(parameter, base_objects.ModelVariable)
        
        if parameter.name in self.all_expr:
            return
        
        self.all_expr[parameter.name] = parameter
        try:
            self.params[parameter.depend].append(parameter)
        except:
            self.params[parameter.depend] = [parameter]
            
    def add_coupling(self, coupling):
        """ add consistently the coupling in couplings and all_expr.
        avoid duplication """
        
        assert isinstance(coupling, base_objects.ModelVariable)
        
        if coupling.name in self.all_expr:
            return
        self.all_expr[coupling.value] = coupling
        try:
            self.coupling[coupling.depend].append(coupling)
        except:
            self.coupling[coupling.depend] = [coupling]

    def analyze_couplings(self,additional_couplings=[]):
        """creates the shortcut for all special function/parameter
        separate the couplings dependent of track variables of the others"""
        
        # For loop models, make sure that all couplings with dictionary values
        # are turned into set of couplings, one for each pole and finite part.
        if self.perturbation_couplings:
            couplings_list=[]
            for coupling in self.model.all_couplings + additional_couplings:
                if not isinstance(coupling.value,dict):
                    couplings_list.append(coupling)
                else:
                    for poleOrder in range(0,3):
                        if coupling.pole(poleOrder)!='ZERO':                    
                            newCoupling=copy.copy(coupling)
                            if poleOrder!=0:
                                newCoupling.name += "_%deps"%poleOrder
                            newCoupling.value=coupling.pole(poleOrder)
                            # assign the CT parameter dependences
#                             if hasattr(coupling,'CTparam_dependence') and \
#                                     (-poleOrder in coupling.CTparam_dependence) and \
#                                     coupling.CTparam_dependence[-poleOrder]:
#                                 newCoupling.CTparam_dependence = coupling.CTparam_dependence[-poleOrder]
#                             elif hasattr(newCoupling,'CTparam_dependence'):
#                                 delattr(newCoupling,"CTparam_dependence")
                            couplings_list.append(newCoupling)
        else:
            couplings_list = self.model.all_couplings + additional_couplings
            couplings_list = [c for c in couplings_list if not isinstance(c.value, dict)] 
            
        for coupling in couplings_list:
            # shorten expression, find dependencies, create short object
            expr = self.shorten_expr(coupling.value)
            depend_on = self.find_dependencies(expr)
            parameter = base_objects.ModelVariable(coupling.name, expr, 'complex', depend_on)
            # Add consistently in the couplings/all_expr
            if 'aS' in depend_on and 'QCD' not in coupling.order:
                logger.warning('coupling %s=%s has direct dependence in aS but has QCD order set to 0. Automatic computation of scale uncertainty can be wrong for such model.',
                               coupling.name, coupling.value)
            try:
                self.couplings[depend_on].append(parameter)
            except KeyError:
                self.couplings[depend_on] = [parameter]
            if coupling.value not in self.all_expr:
                # the if statement is only to prevent overwritting definition in all_expr
                # when a coupling is equal to a single parameter
                # note that coupling are always mapped to complex, while parameter can be real.
                self.all_expr[coupling.value] = parameter 
        

    def find_dependencies(self, expr):
        """check if an expression should be evaluated points by points or not
        """
        depend_on = set()

        # Treat predefined result
        #if name in self.track_dependant:  
        #    return tuple()
        
        # Split the different part of the expression in order to say if a 
        #subexpression is dependent of one of tracked variable
        sexpr = str(expr)
        expr = self.separator.split(expr)
        # look for each subexpression
        for subexpr in expr:
            if subexpr in self.track_dependant:
                depend_on.add(subexpr)
                
            elif subexpr in self.all_expr and self.all_expr[subexpr].depend:
                [depend_on.add(value) for value in self.all_expr[subexpr].depend 
                                if  self.all_expr[subexpr].depend != ('external',)]

        if depend_on:
            return tuple(depend_on)
        else:
            return tuple()


    def shorten_expr(self, expr):
        """ apply the rules of contraction and fullfill
        self.params with dependent part"""
        try:
            expr = self.complex_number.sub(self.shorten_complex, expr)
            expr = self.expo_expr.sub(self.shorten_expo, expr)
            expr = self.cmath_expr.sub(self.shorten_cmath, expr)
            expr = self.conj_expr.sub(self.shorten_conjugate, expr)
        except Exception:
            logger.critical("fail to handle expression: %s, type()=%s", expr,type(expr))
            raise
        return expr
    

    def shorten_complex(self, matchobj):
        """add the short expression, and return the nice string associate"""
        
        float_real = float(eval(matchobj.group('real')))
        float_imag = float(eval(matchobj.group('imag')))
        if float_real == 0 and float_imag ==1:
            new_param = base_objects.ModelVariable('complexi', 'complex(0,1)', 'complex')
            self.add_parameter(new_param)
            return 'complexi'
        else:
            return 'complex(%s, %s)' % (matchobj.group('real'), matchobj.group('imag'))
        
        
    def shorten_expo(self, matchobj):
        """add the short expression, and return the nice string associate"""
        
        expr = matchobj.group('expr')
        exponent = matchobj.group('expo')
        new_exponent = exponent.replace('.','_').replace('+','').replace('-','_m_')
        output = '%s__exp__%s' % (expr, new_exponent)
        old_expr = '%s**%s' % (expr,exponent)

        if expr.startswith('cmath'):
            return old_expr
        
        if expr.isdigit():
            output = 'nb__' + output #prevent to start with a number
            new_param = base_objects.ModelVariable(output, old_expr,'real')
        else:
            depend_on = self.find_dependencies(expr)
            type = self.search_type(expr)
            new_param = base_objects.ModelVariable(output, old_expr, type, depend_on)
        self.add_parameter(new_param)
        return output
        
    def shorten_cmath(self, matchobj):
        """add the short expression, and return the nice string associate"""
        
        expr = matchobj.group('expr')
        operation = matchobj.group('operation')
        output = '%s__%s' % (operation, expr)
        old_expr = ' cmath.%s(%s) ' %  (operation, expr)
        if expr.isdigit():
            new_param = base_objects.ModelVariable(output, old_expr , 'real')
        else:
            depend_on = self.find_dependencies(expr)
            type = self.search_type(expr)
            new_param = base_objects.ModelVariable(output, old_expr, type, depend_on)
        self.add_parameter(new_param)
        
        return output        
        
    def shorten_conjugate(self, matchobj):
        """add the short expression, and retrun the nice string associate"""
        
        expr = matchobj.group('expr')
        output = 'conjg__%s' % (expr)
        old_expr = ' complexconjugate(%s) ' % expr
        depend_on = self.find_dependencies(expr)
        type = 'complex'
        new_param = base_objects.ModelVariable(output, old_expr, type, depend_on)
        self.add_parameter(new_param)  
                    
        return output            
    

     
    def search_type(self, expr, dep=''):
        """return the type associate to the expression if define"""
        
        try:
            return self.all_expr[expr].type
        except:
            return 'complex'
            
class RestrictModel(model_reader.ModelReader):
    """ A class for restricting a model for a given param_card.
    rules applied:
     - Vertex with zero couplings are throw away
     - external parameter with zero/one input are changed into internal parameter.
     - identical coupling/mass/width are replace in the model by a unique one
     """
  
    log_level = 10
    if madgraph.ADMIN_DEBUG:
        log_level = 5    
  
    def default_setup(self):
        """define default value"""
        self.del_coup = []
        super(RestrictModel, self).default_setup()
        self.rule_card = check_param_card.ParamCardRule()
        self.restrict_card = None
        self.coupling_order_dict ={}
        self.autowidth =  []
     
    def modify_autowidth(self, cards, id):
        self.autowidth.append([int(id[0])])
        return math.log10(2*len(self.autowidth))
     
    def restrict_model(self, param_card, rm_parameter=True, keep_external=False,
                                                      complex_mass_scheme=None):
        """apply the model restriction following param_card.
        rm_parameter defines if the Zero/one parameter are removed or not from
        the model.
        keep_external if the param_card need to be kept intact
        """
        
        if self.get('name') == "mssm" and not keep_external:
            raise Exception

        self.restrict_card = param_card
        # Reset particle dict to ensure synchronized particles and interactions
        self.set('particles', self.get('particles'))

        # compute the value of all parameters
        # Get the list of definition of model functions, parameter values. 
        model_definitions = self.set_parameters_and_couplings(param_card, 
                                        complex_mass_scheme=complex_mass_scheme,
                                        auto_width=self.modify_autowidth)
        
        # Simplify conditional statements
        logger.log(self.log_level, 'Simplifying conditional expressions')
        modified_params, modified_couplings = \
            self.detect_conditional_statements_simplifications(model_definitions)
        
        # Apply simplifications
        self.apply_conditional_simplifications(modified_params, modified_couplings)
        
        # associate to each couplings the associated vertex: def self.coupling_pos
        self.locate_coupling()
        # deal with couplings
        zero_couplings, iden_couplings = self.detect_identical_couplings()

        # remove the out-dated interactions
        self.remove_interactions(zero_couplings)
        
        # replace in interactions identical couplings
        for iden_coups in iden_couplings:
            self.merge_iden_couplings(iden_coups)

        # remove zero couplings and other pointless couplings
        self.del_coup += zero_couplings
        self.remove_couplings(self.del_coup)
       
        # modify interaction to avoid to have identical coupling with different lorentz
        for interaction in list(self.get('interactions')):
            self.optimise_interaction(interaction)
                
        # deal with parameters
        parameters = self.detect_special_parameters()
        self.fix_parameter_values(*parameters, simplify=rm_parameter, 
                                                    keep_external=keep_external)

        # deal with identical parameters
        if not keep_external:
            iden_parameters = self.detect_identical_parameters()
            for iden_param in iden_parameters:
                self.merge_iden_parameters(iden_param)
    
        iden_parameters = self.detect_identical_parameters()
        for iden_param in iden_parameters:
            self.merge_iden_parameters(iden_param, keep_external)
              
        # change value of default parameter if they have special value:
        # 9.999999e-1 -> 1.0
        # 0.000001e-99 -> 0 Those value are used to avoid restriction
        for name, value in self['parameter_dict'].items():
            if value == 9.999999e-1:
                self['parameter_dict'][name] = 1
            elif value == 0.000001e-99:
                self['parameter_dict'][name] = 0
                
        #
        # restore auto-width value 
        #
        #for lhacode in self.autowidth:
        for parameter in self['parameters'][('external',)]:
            if parameter.lhablock.lower() == 'decay' and parameter.lhacode in self.autowidth:
                parameter.value = 'auto'
                if parameter.name in self['parameter_dict']:
                    self['parameter_dict'][parameter.name] = 'auto'
                elif parameter.name.startswith('mdl_'):
                    self['parameter_dict'][parameter.name[4:]] = 'auto'
                else:
                    raise Exception

        # delete cache for coupling_order if some coupling are not present in the model anymore
        old_order = self['coupling_orders']
        self['coupling_orders'] = None
        if old_order and old_order != self.get('coupling_orders'):
            removed = set(old_order).difference(set(self.get('coupling_orders')))
            logger.warning("Some coupling order do not have any coupling associated to them: %s", list(removed))
            logger.warning("Those coupling order will not be valid anymore for this model")

            self['order_hierarchy'] = {}
            self['expansion_order'] = None
            #and re-initialize it to avoid any potential side effect
            self.get('order_hierarchy')
            self.get('expansion_order')

        if os.path.exists(param_card.replace('restrict', 'param')):
            path = param_card.replace('restrict', 'param')
            logger.info('default value set as in file %s' % path)
            self.set_parameters_and_couplings(path,
                                              complex_mass_scheme=complex_mass_scheme,
                                              auto_width=self.modify_autowidth)
                          

        
    def locate_coupling(self):
        """ create a dict couplings_name -> vertex or (particle, counterterm_key) """
        
        self.coupling_pos = {}
        for vertex in self['interactions']:
            for key, coupling in vertex['couplings'].items():
                if coupling.startswith('-'):
                    coupling = coupling[1:]
                if coupling in self.coupling_pos:
                    if vertex not in self.coupling_pos[coupling]:
                        self.coupling_pos[coupling].append(vertex)
                else:
                    self.coupling_pos[coupling] = [vertex]
        
        for particle in self['particles']:
            for key, coupling_dict in particle['counterterm'].items():
                for LaurentOrder, coupling in coupling_dict.items():
                    if coupling in self.coupling_pos:
                        if (particle,key) not in self.coupling_pos[coupling]:
                            self.coupling_pos[coupling].append((particle,key))
                    else:
                        self.coupling_pos[coupling] = [(particle,key)]

        return self.coupling_pos
        
    def detect_identical_couplings(self, strict_zero=False):
        """return a list with the name of all vanishing couplings"""
        
        dict_value_coupling = {}
        iden_key = set()
        zero_coupling = []
        iden_coupling = []
        
        
        keys = list(self['coupling_dict'].keys())
        keys.sort()
        for name in keys:
            value = self['coupling_dict'][name]

            def limit_to_6_digit(a):
                x = a.real
                if x != 0:
                    x = round(x, int(abs(round(math.log(abs(x), 10),0))+10))
                y = a.imag
                if y !=0:
                    y = round(y, int(abs(round(math.log(abs(y), 10),0))+10))
                return complex(x,y)
            

            if value == 0:
                zero_coupling.append(name)
                continue
            elif not strict_zero and abs(value) < 1e-13:
                logger.log(self.log_level, 'coupling with small value %s: %s treated as zero' %
                             (name, value))
                zero_coupling.append(name)
                continue
            elif not strict_zero and abs(value) < 1e-10:
                return self.detect_identical_couplings(strict_zero=True)

            value = limit_to_6_digit(value)

            if value in dict_value_coupling or -1*value in dict_value_coupling:
                if value in dict_value_coupling:
                    iden_key.add(value)
                    dict_value_coupling[value].append((name,1))
                else:
                    iden_key.add(-1*value)
                    dict_value_coupling[-1*value].append((name,-1))
            else:
                dict_value_coupling[value] = [(name,1)]
        for key in iden_key:
            tmp = []
            if key in dict_value_coupling:
                tmp += dict_value_coupling[key]
            elif -1*key in dict_value_coupling:
                tmp += dict_value_coupling[-1*key]
            assert tmp

            #ensure that all coupling have the same coupling order.
            ords = [self.get_coupling_order(k) for k,c in tmp]
            coup_by_ord = collections.defaultdict(list)
            for o,t in zip(ords, tmp):
                coup_by_ord[str(o)].append(t)
            # add the remaining identical
            for tmp3 in coup_by_ord.values():
                if len(tmp3) > 1:
                    if tmp3[0][1] == -1: #ensure that the first coupling has positif value
                        tmp3 = [(t0,-t1) for t0, t1 in tmp3]
                    iden_coupling.append(tmp3)

            
            

        return zero_coupling, iden_coupling
    
    def get_coupling_order(self, cname):
        """return the coupling order associated to a coupling """
        
        if cname in self.coupling_order_dict:
            return self.coupling_order_dict[cname]

        for v in self['interactions']:
            for c in v['couplings'].values():
                self.coupling_order_dict[c] = v['orders']
        
        if cname not in self.coupling_order_dict:
            self.coupling_order_dict[cname] = None
            #can happen when some vertex are discarded due to ghost/...
            
        
        return self.coupling_order_dict[cname]


    
    def detect_special_parameters(self):
        """ return the list of (name of) parameter which are zero """
        
        null_parameters = []
        one_parameters = []
        for name, value in self['parameter_dict'].items():
            if value == 0 and name != 'ZERO':
                null_parameters.append(name)
            elif value == 1:
                one_parameters.append(name)

        # check if the model is a running model with running.py and 
        # check that the model is compatible with the restriction
        running_param = self.get_running() 
        if running_param:
            tocheck = null_parameters+one_parameters
            for p in  tocheck:
                for block in running_param:
                    block = ['mdl_%s' % c for c in block]
                    if p in block:
                        if any((p2 not in tocheck for p2 in block)):
                            not_restricted = [p2 for p2 in block if p2 not in tocheck]
                            raise Exception("Model restriction not compatible with the running of some parameters. \n %s is restricted to zero/one but mix with %s which is/are not."
                                            %(p, not_restricted))
                        else:
                            continue # go to the next block



        return null_parameters, one_parameters
    
    def apply_conditional_simplifications(self, modified_params,
                                                            modified_couplings):
        """ Apply the conditional statement simplifications for parameters and
        couplings detected by 'simplify_conditional_statements'.
        modified_params (modified_couplings) are list of tuples (a,b) with a
        parameter (resp. coupling) instance and b is the simplified expression."""
        
        if modified_params:
            logger.log(self.log_level, "Conditional expressions are simplified for parameters:")
            logger.log(self.log_level, ",".join("%s"%param[0].name for param in modified_params))
        for param, new_expr in modified_params:
            param.expr = new_expr
        
        if modified_couplings:
            logger.log(self.log_level, "Conditional expressions are simplified for couplings:")
            logger.log(self.log_level, ",".join("%s"%coupl[0].name for coupl in modified_couplings))
        for coupl, new_expr in modified_couplings:
            coupl.expr = new_expr
    
    def detect_conditional_statements_simplifications(self, model_definitions,
          objects=['couplings','parameters']):
        """ Simplifies the 'if' statements in the pythonic UFO expressions
        of parameters using the default variables specified in the restrict card.
        It returns a list of objects (parameters or couplings) and the new
        expression that they should take. Model definitions include all definitons
        of the model functions and parameters."""
        
        param_modifications = []
        coupl_modifications = []
        ifparser = parsers.UFOExpressionParserPythonIF(model_definitions)
        
        start_param = time.time()
        if 'parameters' in objects:
            for dependences, param_list in self['parameters'].items():
                if 'external' in dependences:
                    continue
                for param in param_list:
                    new_expr, n_changes = ifparser.parse(param.expr)
                    if n_changes > 0:
                        param_modifications.append((param, new_expr))
      
        end_param = time.time()
  
        if 'couplings' in objects:         
            for dependences, coupl_list in self['couplings'].items():
                for coupl in coupl_list:
                    new_expr, n_changes = ifparser.parse(coupl.expr)
                    if n_changes > 0:
                        coupl_modifications.append((coupl, new_expr))        

        end_coupl = time.time()
        
        tot_param_time = end_param-start_param
        tot_coupl_time = end_coupl-end_param
        if tot_param_time>5.0:
            logger.log(self.log_level, "Simplification of conditional statements"+\
              " in parameter expressions done in %s."%misc.format_time(tot_param_time))
        if tot_coupl_time>5.0:
            logger.log(self.log_level, "Simplification of conditional statements"+\
              " in couplings expressions done in %s."%misc.format_time(tot_coupl_time))

        return param_modifications, coupl_modifications
    
    def detect_identical_parameters(self):
        """ return the list of tuple of name of parameter with the same 
        input value """

        # Extract external parameters
        external_parameters = self['parameters'][('external',)]
        
        # define usefull variable to detect identical input
        block_value_to_var={} #(lhablok, value): list_of_var
        mult_param = set([])  # key of the previous dict with more than one
                              #parameter.
                              
        #detect identical parameter and remove the duplicate parameter
        for param in external_parameters[:]:
            value = self['parameter_dict'][param.name]
            if value in [0,1,0.000001e-99,9.999999e-1]:
                continue
            if param.lhablock.lower() == 'decay':
                continue
            key = (param.lhablock, value)
            mkey =  (param.lhablock, -value)

            if key in block_value_to_var:
                block_value_to_var[key].append((param,1))
                mult_param.add(key)
            elif mkey in block_value_to_var:
                block_value_to_var[mkey].append((param,-1))
                mult_param.add(mkey)
            else: 
                block_value_to_var[key] = [(param,1)]        
        
        output=[]  
        for key in mult_param:
            output.append(block_value_to_var[key])
            
        return output


    @staticmethod
    def get_new_coupling_name(main, coupling, value, coeff):
        """ We have main == coeff * coupling
            coeff is only +1 or -1
            main can be either GC_X or -GC_X
            coupling can be either GC_Y or -GC_Y
            value is either GC_Y or -GC_Y
            the return is either GC_X or -GC_X
            such that we have value == OUTPUT
        """
        assert coeff in [-1,1]
        assert value == coupling or value == '-%s' % coupling or coupling == '-%s' % value
        assert isinstance(main, str)
        assert isinstance(coupling, str)
        assert isinstance(value, str)
        if coeff ==1: 
            if value == coupling:
                return main # 4/4
            else:
                if main.startswith('-'):
                    return main[1:] # 2/2
                else:
                    return '-%s' % main # 2/2
        else:
            if value == coupling:
                if main.startswith('-'):
                    return main[1:] # 2/2
                else:
                    return '-%s' % main # 2/2
            else:
                return main # 4/4


    def merge_iden_couplings(self, couplings):
        """merge the identical couplings in the interactions and particle 
        counterterms"""

        
        logger_mod.log(self.log_level, ' Fuse the Following coupling (they have the same value): %s '% \
                        ', '.join([str(obj) for obj in couplings]))

        #names = [name for (name,ratio) in couplings if ratio ==1]
        main = couplings[0][0]
        assert couplings[0][1] == 1
        self.del_coup += [c[0] for c in couplings[1:]] # add the other coupl to the suppress list
        
        for coupling, coeff in couplings[1:]:
            # check if param is linked to an interaction
            if coupling not in self.coupling_pos:
                continue
            # replace the coupling, by checking all coupling of the interaction
            vertices = [ vert for vert in self.coupling_pos[coupling] if 
                         isinstance(vert, base_objects.Interaction)]
            for vertex in vertices:
                for key, value in vertex['couplings'].items():
                    if value == coupling or value == '-%s' % coupling or coupling == '-%s' % value:
                        vertex['couplings'][key] = self.get_new_coupling_name(\
                                                   main, coupling, value, coeff)
                    
                    
                            
                        
            # replace the coupling appearing in the particle counterterm
            particles_ct = [ pct for pct in self.coupling_pos[coupling] if 
                         isinstance(pct, tuple)]
            for pct in particles_ct:
                for key, value in pct[0]['counterterm'][pct[1]].items():
                    if value == coupling:
                        pct[0]['counterterm'][pct[1]][key] = main


                
    def get_param_block(self):
        """return the list of block defined in the param_card"""
        
        blocks = set([p.lhablock for p in self['parameters'][('external',)]])
        return blocks
         
    def merge_iden_parameters(self, parameters, keep_external=False):
        """ merge the identical parameters given in argument.
        keep external force to keep the param_card untouched (up to comment)"""
            
        logger_mod.log(self.log_level, 'Parameters set to identical values: %s '% \
                 ', '.join(['%s*%s' % (f, obj.name.replace('mdl_','')) for (obj,f) in parameters]))

        # Extract external parameters
        external_parameters = self['parameters'][('external',)]
        for i, (obj, factor) in enumerate(parameters):
            # Keeped intact the first one and store information
            if i == 0:
                obj.info = 'set of param :' + \
                                     ', '.join([str(f)+'*'+param.name.replace('mdl_','')
                                                 for (param, f) in parameters])
                expr = obj.name
                continue
            # Add a Rule linked to the param_card
            if factor ==1:
                self.rule_card.add_identical(obj.lhablock.lower(), obj.lhacode, 
                                                         parameters[0][0].lhacode )
            else:
                self.rule_card.add_opposite(obj.lhablock.lower(), obj.lhacode, 
                                                         parameters[0][0].lhacode )
            obj_name = obj.name
            # delete the old parameters
            if not keep_external:                
                external_parameters.remove(obj)
            elif obj.lhablock.upper() in ['MASS','DECAY']:
                external_parameters.remove(obj)
            else:
                obj.name = ''
                obj.info = 'MG5 will not use this value use instead %s*%s' %(factor,expr)    
            # replace by the new one pointing of the first obj of the class
            new_param = base_objects.ModelVariable(obj_name, '%s*%s' %(factor, expr), 'real')
            self['parameters'][()].insert(0, new_param)
        
        # For Mass-Width, we need also to replace the mass-width in the particles
        #This allows some optimization for multi-process.
        if parameters[0][0].lhablock in ['MASS','DECAY']:
            new_name = parameters[0][0].name
            if parameters[0][0].lhablock == 'MASS':
                arg = 'mass'
            else:
                arg = 'width'
            change_name = [p.name for (p,f) in parameters[1:]]
            factor_for_name = [f for (p,f)  in parameters[1:]]
            [p.set(arg, new_name) for p in self['particle_dict'].values() 
                                                       if p[arg] in change_name and 
                                                       factor_for_name[change_name.index(p[arg])]==1]
            
    def remove_interactions(self, zero_couplings):
        """ remove the interactions and particle counterterms 
        associated to couplings"""
        
        
        mod_vertex = []
        mod_particle_ct = []
        for coup in zero_couplings:
            # some coupling might be not related to any interactions
            if coup not in self.coupling_pos:
                continue
            
            # Remove the corresponding interactions.

            vertices = [ vert for vert in self.coupling_pos[coup] if 
                         isinstance(vert, base_objects.Interaction) ]
            for vertex in vertices:
                modify = False
                for key, coupling in list(vertex['couplings'].items()):
                    if coupling in zero_couplings:
                        modify=True
                        del vertex['couplings'][key]
                    elif coupling.startswith('-'):
                        coupling = coupling[1:]
                        if coupling in zero_couplings:
                            modify=True
                            del vertex['couplings'][key]                      
                        
                if modify:
                    mod_vertex.append(vertex)
            
            # Remove the corresponding particle counterterm
            particles_ct = [ pct for pct in self.coupling_pos[coup] if 
                         isinstance(pct, tuple)]
            for pct in particles_ct:
                modify = False
                for key, coupling in list(pct[0]['counterterm'][pct[1]].items()):
                    if coupling in zero_couplings:
                        modify=True
                        del pct[0]['counterterm'][pct[1]][key]
                if modify:
                    mod_particle_ct.append(pct)

        # print useful log and clean the empty interaction
        for vertex in mod_vertex:
            part_name = [part['name'] for part in vertex['particles']]
            orders = ['%s=%s' % (order,value) for order,value in vertex['orders'].items()]
                                        
            if not vertex['couplings']:
                logger_mod.log(self.log_level, 'remove interactions: %s at order: %s' % \
                                        (' '.join(part_name),', '.join(orders)))
                self['interactions'].remove(vertex)
            else:
                logger_mod.log(self.log_level, 'modify interactions: %s at order: %s' % \
                                (' '.join(part_name),', '.join(orders)))

        # print useful log and clean the empty counterterm values
        for pct in mod_particle_ct:
            part_name = pct[0]['name']
            order = pct[1][0]
            loop_parts = ','.join(['('+','.join([\
                         self.get_particle(p)['name'] for p in part])+')' \
                         for part in pct[1][1]])
                                        
            if not pct[0]['counterterm'][pct[1]]:
                logger_mod.log(self.log_level, 'remove counterterm of particle %s'%part_name+\
                                 ' with loop particles (%s)'%loop_parts+\
                                 ' perturbing order %s'%order)
                del pct[0]['counterterm'][pct[1]]
            else:
                logger_mod.log(self.log_level, 'Modify counterterm of particle %s'%part_name+\
                                 ' with loop particles (%s)'%loop_parts+\
                                 ' perturbing order %s'%order)  

        # looping over all vertex and remove all link to lorentz structure that are not used anymore
        for vertex in mod_vertex:
            lorentz_used = set()
            for key in vertex['couplings']:
                lorentz_used.add(key[1])
            if not lorentz_used:
                continue
            lorentz_used = list(lorentz_used)
            lorentz_used.sort()
            map = {j:i for i,j in enumerate(lorentz_used)}            
            new_lorentz = [l for i,l in enumerate(vertex['lorentz']) if i in lorentz_used]
            new_coup = {}
            for key in vertex['couplings']:
                new_key = list(key)
                new_key[1] = map[new_key[1]]
                new_coup[tuple(new_key)] = vertex['couplings'][key]
            vertex['lorentz'] = new_lorentz
            vertex['couplings'] = new_coup                    


        return
                
    def remove_couplings(self, couplings):               
        #clean the coupling list:
        for name, data in self['couplings'].items():
            for coupling in data[:]:
                if coupling.name in couplings:
                    data.remove(coupling)
                            
        
    def fix_parameter_values(self, zero_parameters, one_parameters, 
                                            simplify=True, keep_external=False):
        """ Remove all instance of the parameters in the model and replace it by 
        zero when needed."""


        # treat specific cases for masses and width
        for particle in self['particles']:
            if particle['mass'] in zero_parameters:
                particle['mass'] = 'ZERO'
            if particle['width'] in zero_parameters:
                particle['width'] = 'ZERO'
            if particle['width'] in one_parameters:
                one_parameters.remove(particle['width'])                
            if particle['mass'] in one_parameters:
                one_parameters.remove(particle['mass'])                

        for pdg, particle in self['particle_dict'].items():
            if particle['mass'] in zero_parameters:
                particle['mass'] = 'ZERO'
            if particle['width'] in zero_parameters:
                particle['width'] = 'ZERO'


        # Add a rule for zero/one parameter
        external_parameters = self['parameters'][('external',)]
        for param in external_parameters[:]:
            value = self['parameter_dict'][param.name]
            block = param.lhablock.lower()
            if value == 0:
                self.rule_card.add_zero(block, param.lhacode)
            elif value == 1:
                self.rule_card.add_one(block, param.lhacode)

        special_parameters = zero_parameters + one_parameters
        
            

        if simplify:
            # check if the parameters is still useful:
            re_str = '|'.join(special_parameters)
            if len(re_str) > 25000: # size limit on mac
                split = len(special_parameters) // 2
                re_str = ['|'.join(special_parameters[:split]),
                          '|'.join(special_parameters[split:])]
            else:
                re_str = [ re_str ]
            used = set()
            for expr in re_str:
                re_pat = re.compile(r'''\b(%s)\b''' % expr)
                # check in coupling
                for name, coupling_list in self['couplings'].items():
                    for coupling in coupling_list:
                        for use in  re_pat.findall(coupling.expr):
                            used.add(use)
                
                # check in form-factor
                for lor in self['lorentz']:
                    if hasattr(lor, 'formfactors') and lor.formfactors:
                        for ff in lor.formfactors:
                            for use in  re_pat.findall(ff.value):
                                used.add(use)
        else:
            used = set([i for i in special_parameters if i])
        
        # simplify the regular expression
        re_str = '|'.join([param for param in special_parameters if param not in used])
        if len(re_str) > 25000: # size limit on mac
            split = len(special_parameters) // 2
            re_str = ['|'.join(special_parameters[:split]),
                          '|'.join(special_parameters[split:])]
        else:
            re_str = [ re_str ]
        for expr in re_str:                                                      
            re_pat = re.compile(r'''\b(%s)\b''' % expr)
               
            param_info = {}
            # check in parameters
            for dep, param_list in self['parameters'].items():
                for tag, parameter in enumerate(param_list):
                    # update information concerning zero/one parameters
                    if parameter.name in special_parameters:
                        param_info[parameter.name]= {'dep': dep, 'tag': tag, 
                                                               'obj': parameter}
                        continue
                                        
                    # Bypass all external parameter
                    if isinstance(parameter, base_objects.ParamCardVariable):
                        continue
    
                    if simplify:
                        for use in  re_pat.findall(parameter.expr):
                            used.add(use)
                        
        if madgraph.ordering:
            used = sorted(used)
            
        # modify the object for those which are still used
        for param in used:
            if not param:
                continue
            data = self['parameters'][param_info[param]['dep']]
            data.remove(param_info[param]['obj'])
            tag = param_info[param]['tag']
            data = self['parameters'][()]
            if param in zero_parameters:
                data.insert(0, base_objects.ModelVariable(param, '0.0', 'real'))
            else:
                data.insert(0, base_objects.ModelVariable(param, '1.0', 'real'))
                
        # remove completely useless parameters
        for param in special_parameters:
            #by pass parameter still in use
            if param in used or \
                  (keep_external and param_info[param]['dep'] == ('external',)):
                logger_mod.log(self.log_level, 'fix parameter value: %s' % param)
                continue 
            logger_mod.log(self.log_level,'remove parameters: %s' % (param))
            data = self['parameters'][param_info[param]['dep']]
            data.remove(param_info[param]['obj'])
            

    def optimise_interaction(self, interaction):
        
        # we want to check if the same coupling (up to the sign) is used for two lorentz structure 
        # for the same color structure. 
        to_lor = {}
        for (color, lor), coup in interaction['couplings'].items():
            abscoup, coeff = (coup[1:],-1) if coup.startswith('-') else (coup, 1)
            key = (color, abscoup)
            if key in to_lor:
                to_lor[key].append((lor,coeff))
            else:
                to_lor[key] = [(lor,coeff)]

        nb_reduce = []
        optimize = False
        for key in to_lor:
            if len(to_lor[key]) >1:
                nb_reduce.append(len(to_lor[key])-1)
                optimize = True
           
        if not optimize:
            return
        
        if not hasattr(self, 'defined_lorentz_expr'):
            self.defined_lorentz_expr = {}
            self.lorentz_info = {}
            self.lorentz_combine = {}
            for lor in self.get('lorentz'):
                self.defined_lorentz_expr[lor.get('structure')] = lor.get('name')
                self.lorentz_info[lor.get('name')] = lor #(lor.get('structure'), lor.get('spins'))
            


        for key in to_lor:
            if len(to_lor[key]) == 1:
                continue

            def get_spin(l):
                return self.lorentz_info[interaction['lorentz'][l]].get('spins')

            if any(get_spin(l1[0]) != get_spin(to_lor[key][0][0]) for l1 in to_lor[key]):
                logger.warning('not all same spins for a given interactions')
                continue 

            names = ['u%s' % interaction['lorentz'][i[0]] if i[1] ==1 else \
                     'd%s' % interaction['lorentz'][i[0]] for i in to_lor[key]]

            names.sort()
            
            # get name of the new lorentz
            if tuple(names) in self.lorentz_combine:
                # already created new loretnz
                new_name = self.lorentz_combine[tuple(names)]
            else:
                new_name = self.add_merge_lorentz(names)
                
            # remove the old couplings 
            color, coup = key
            to_remove = [(color, lor[0]) for lor in to_lor[key]] 
            for rm in to_remove:
                del interaction['couplings'][rm]
                
            #add the lorentz structure to the interaction            
            if new_name not in [l for l in interaction.get('lorentz')]:
                interaction.get('lorentz').append(new_name)

            #find the associate index
            new_l = interaction.get('lorentz').index(new_name)
            # adding the new combination (color,lor) associate to this sum of structure
            interaction['couplings'][(color, new_l)] = coup     



    def add_merge_lorentz(self, names):
        """add a lorentz structure which is the sume of the list given above"""
        
        #create new_name
        ii = len(names[0])
        while ii>1:
            #do not count the initial "u/d letter whcih indicates the sign"
            if not all(n[1:].startswith(names[0][1:ii]) for n in names[1:]):
                ii -=1
            else:
                base_name = names[0][1:ii]
                break
        else:
            base_name = 'LMER'

        i = 1
        while '%s%s' %(base_name, i) in self.lorentz_info:
            i +=1
        new_name = '%s%s' %(base_name, i)
        self.lorentz_combine[tuple(names)] = new_name
        
        # load the associate lorentz expression
        new_struct = ' + '.join([self.lorentz_info[n[1:]].get('structure') for n in names if n.startswith('u')])
        if any( n.startswith('d') for n in names ):
            new_struct += '-' + ' - '.join(['1.*(%s)' %self.lorentz_info[n[1:]].get('structure') for n in names if n.startswith('d')])
        spins = self.lorentz_info[names[0][1:]].get('spins')
        formfact = sum([ self.lorentz_info[n[1:]].get('formfactors') for n in names \
                            if hasattr(self.lorentz_info[n[1:]], 'formfactors') \
                              and self.lorentz_info[n[1:]].get('formfactors') \
                       ],[])



 
        new_lor = self.add_lorentz(new_name, spins, new_struct, formfact)
        self.lorentz_info[new_name] = new_lor
        
        return new_name
    
    def add_lorentz(self, name, spin, struct, formfact=None):
        """adding lorentz structure to the current model"""
        new = self['lorentz'][0].__class__(name = name,
                                           spins = spin,
                                           structure = struct)
        if formfact:
            new.formfactors = formfact
        self['lorentz'].append(new)
        self.create_lorentz_dict()
        
        return None
                                
        
        
        
         
      
    
      
        
        
    
