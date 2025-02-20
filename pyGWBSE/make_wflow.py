#This code is to create the workflow based on inputs from input.yaml file 

from fireworks import Firework, Workflow
from pyGWBSE.wflows import ScfFW, convFW, BseFW, GwFW, EmcFW, WannierCheckFW, WannierFW
from pyGWBSE.inputset import CreateInputs 
from pymatgen.core import Structure
from fireworks import LaunchPad
from pyGWBSE.config import VASP_CMD, DB_FILE, SUMO_CMD, WANNIER_CMD
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.io.vasp.inputs import Kpoints
from pymatgen.ext.matproj import MPRester
import numpy as np
from pymongo import MongoClient
import yaml
import sys


#Function to find the kgrid and number of symmtery reduced kpoints based on symmetry of the structure and the reciprocal density
def num_ir_kpts(struct,reciprocal_density, two_dim=False):
    _fake_structure = struct.copy()
    if two_dim:
        _fake_structure.make_supercell([1,1,4])
    spg=SpacegroupAnalyzer(_fake_structure, symprec=0.01, angle_tolerance=5)
    Kpts=Kpoints.automatic_density_by_vol(_fake_structure,reciprocal_density,force_gamma=True)
    kpts=spg.get_ir_reciprocal_mesh(mesh=Kpts.kpts, is_shift=(0, 0, 0))
    return Kpts.kpts,len(kpts)


#Function to find the number of occupied bands from the input structure
def num_occ_bands(struct):
    vasp_input_set = CreateInputs(struct)
    nel=vasp_input_set.nelect
    nocc=int(nel/2)
    return nocc


#Function to read the input.yaml file
def read_input(mp_key):

    yaml_file = open("input.yaml")
    input_dict = yaml.load(yaml_file, Loader=yaml.FullLoader)
    struc_src=input_dict["STRUCTURE"]["source"]

    if struc_src=='POSCAR':
        struct=Structure.from_file('POSCAR')
        mat_name=input_dict["STRUCTURE"]["mat_name"]
    elif struc_src=='MID':
        material_id=input_dict["STRUCTURE"]["material_id"]
        mat_name=material_id
        with MPRester(mp_key) as m:
            struct = m.get_structure_by_material_id(material_id,conventional_unit_cell=False)
    else:
        sys.exit('Error: use MID/POSCAR as structure source .... Exiting NOW') 
    input_dict["PARAMS"]["mat_name"]=mat_name
    return struct, input_dict

#Function to create the workflow
def create_wfs(struct, params_dict, vasp_cmd=None, sumo_cmd=None, wannier_cmd=None, db_file=None, c=None):

    c = c or {}
    vasp_cmd = c.get("VASP_CMD", VASP_CMD)                                      
    sumo_cmd = c.get("SUMO_CMD", SUMO_CMD)                                      
    wannier_cmd = c.get("WANNIER_CMD", WANNIER_CMD)                                      
    db_file = c.get("DB_FILE", DB_FILE)    

    params=params_dict["PARAMS"]
    mat_name=params["mat_name"]
    nocc=num_occ_bands(struct)
    kpar=params["kpar"] 
    ppn=params["ppn"]
    two_dim = params["two_dim"]
    rd=params["reciprocal_density"]
    nbgwfactor=params["nbgwfactor"]
    encutgw=params["encutgw"]
    nomegagw=params["nomegagw"]
    convsteps=params["convsteps"]
    conviter=params["conviter"]
    enwinbse=params["enwinbse"]
    skip_emc=params_dict["WFLOW_DESIGN"]["skip_emc"]
    skip_wannier=params_dict["WFLOW_DESIGN"]["skip_wannier"]
    skip_conv=params_dict["WFLOW_DESIGN"]["skip_conv"]
    skip_gw=params_dict["WFLOW_DESIGN"]["skip_gw"]
    scgw=params_dict["WFLOW_DESIGN"]["scgw"]
    skip_bse=params_dict["WFLOW_DESIGN"]["skip_bse"]

    mesh,nkpt=num_ir_kpts(struct,rd, two_dim=two_dim)
    nbands=(int(nocc/ppn)+1)*ppn
    nbandsgw=nocc+10

    print("-------------------------------------------")
    print("material: ",mat_name)
    print("Information for efficient parallelization")
    print("You have ",nocc,"occupied bands")
    print("You have ",nkpt,"kpoints")
    print("You have ",mesh,"k-grid")
    print("KPAR=",kpar)
    print("reciprocal_density=",rd)
    if not(skip_bse):
        print("BSE calculation will include bands in the energy window (eV)=", enwinbse)
    print("-------------------------------------------")

    if scgw==True:
        gw_tag='GW0'
    else:
        gw_tag='G0W0'

    ifw=0 

    fws = [ScfFW(structure=struct, mat_name=mat_name, nbands=nbands, vasp_cmd=vasp_cmd,db_file=db_file,kpar=kpar,
                 reciprocal_density=rd,wannier_fw=not(skip_wannier), two_dim=two_dim)]

    if skip_emc==False:  
        ifw=ifw+1 
        parents = fws[0]
        fw = EmcFW(structure=struct, mat_name=mat_name, vasp_cmd=vasp_cmd, sumo_cmd=sumo_cmd, db_file=db_file,
                   kpar=kpar,reciprocal_density=rd, steps=0.001,parents=parents, two_dim=two_dim)
        fws.append(fw)

    if skip_wannier==False:
        ifw=ifw+1 
        parents = fws[0]
        fw = WannierCheckFW(structure=struct, mat_name=mat_name, kpar=kpar, ppn=ppn,vasp_cmd=vasp_cmd, two_dim=two_dim,
                            wannier_cmd=wannier_cmd,db_file=db_file,parents=parents,reciprocal_density=rd)
        fws.append(fw)

    ifw=ifw+1
    parents = fws[0]
    fw = convFW(structure=struct, mat_name=mat_name, nbands=nbands, nbgwfactor=nbgwfactor, encutgw=encutgw, nomegagw=nomegagw, convsteps=convsteps, conviter=conviter, 
                    tolerence=0.1, no_conv=skip_conv, vasp_cmd=vasp_cmd,db_file=db_file,parents=parents,kpar=kpar,
                nbandsgw=nbandsgw,reciprocal_density=rd, two_dim=two_dim)
    fws.append(fw)

    if skip_gw==False:
        ifw=ifw+1
        parents = fws[ifw-1]
        fw = GwFW(structure=struct, mat_name=mat_name, tolerence=0.1, no_conv=not(scgw),
                vasp_cmd=vasp_cmd,db_file=db_file,parents=parents,reciprocal_density=rd, nbandsgw=nbandsgw,
                  wannier_fw=not(skip_wannier), job_tag=gw_tag, two_dim=two_dim)
        fws.append(fw)

    if skip_wannier==False and skip_gw==False:
        ifw=ifw+1 
        parents = fws[ifw-1]
        fw = WannierFW(structure=struct,mat_name=mat_name, wannier_cmd=wannier_cmd,db_file=db_file,parents=parents,
                       two_dim=two_dim)
        fws.append(fw)
    
    if skip_bse==False and skip_gw==True:
        sys.exit('Error: Need QP energies from GW calculation to perform BSE .... Exiting NOW') 

    if skip_bse==False and skip_gw==False:
        ifw=ifw+1
        if skip_wannier==False:
            parents = fws[ifw-2]
        else:
            parents = fws[ifw-1]
        fw = BseFW(structure=struct, mat_name=mat_name,
                    vasp_cmd=vasp_cmd,db_file=db_file,parents=parents,reciprocal_density=rd,enwinbse=enwinbse,
                   job_tag=gw_tag+'-BSE', two_dim=two_dim)
        fws.append(fw)


    wf_gwbse = Workflow(fws)

    return wf_gwbse



