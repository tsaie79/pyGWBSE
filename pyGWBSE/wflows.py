# coding: utf-8


"""
Defines standardized Fireworks that can be chained easily to perform various
sequences of VASP calculations.
"""
import numpy as np
from atomate.common.firetasks.glue_tasks import PassCalcLocs
from atomate.vasp.firetasks.write_inputs import WriteVaspFromIOSet
from fireworks import Firework, Tracker


from pyGWBSE.inputset import CreateInputs
from pyGWBSE.out2db import gw2db, bse2db, emc2db, eps2db, Wannier2DB, rpa2db
from pyGWBSE.run_calc import Run_Vasp, Run_Sumo, Run_Wannier
from pyGWBSE.tasks import CopyOutputFiles, CheckBeConv, StopIfConverged, PasscalClocsCond, WriteBSEInput, \
                            WriteGWInput, MakeWFilesList, SaveNbandsov, SaveConvParams
from pyGWBSE.wannier_tasks import WriteWannierInputForDFT, WriteWannierInputForGW, CopyKptsWan2vasp


class ScfFW(Firework):
    def __init__(self, mat_name=None, structure=None, nbands=None, kpar=None, reciprocal_density=None,
                 vasp_input_set=None, vasp_input_params=None, two_dim=False,
                 vasp_cmd="vasp", prev_calc_loc=True, prev_calc_dir=None, db_file=None, wannier_fw=None,
                 vasptodb_kwargs={}, **kwargs):
        """
        Your Comments Here
        """
        t = []
        vasp_input_set = CreateInputs(structure, kpar=kpar, reciprocal_density=reciprocal_density, nbands=nbands,
                                      wannier_fw=wannier_fw, two_dim=two_dim)
        name = 'SCF'
        fw_name = "{}-{}".format(mat_name, name)
        t.append(WriteVaspFromIOSet(structure=structure,
                                    vasp_input_set=vasp_input_set,
                                    vasp_input_params=vasp_input_params))
        t.append(Run_Vasp(vasp_cmd=vasp_cmd))
        t.append(eps2db(structure=structure, mat_name=mat_name, db_file=db_file, defuse_unsuccessful=False))
        t.append(rpa2db(structure=structure, mat_name=mat_name, task_label=name, db_file=db_file, defuse_unsuccessful=False))
        t.append(PassCalcLocs(name=name))
        super(ScfFW, self).__init__(t, name=fw_name, **kwargs)


class convFW(Firework):

    def __init__(self, mat_name=None, structure=None, tolerence=None, no_conv=None, nbands=None,
                 nbgwfactor=None, encutgw=None, nomegagw=None, convsteps=None, conviter=None, two_dim=False,
                 kpar=None, nbandsgw=None, reciprocal_density=None, vasp_input_set=None, vasp_input_params=None,
                 vasp_cmd="vasp", prev_calc_loc=True, prev_calc_dir=None, db_file=None, vasptodb_kwargs={}, parents=None, **kwargs):
        t = []
        name = "CONV"
        fw_name = "{}-{}".format(mat_name, name)
        niter = 0
        nocc=nbands
        convsteps=np.array(convsteps)*0.01
        for niter in range(conviter):
            niter = niter + 1
            files2copy = ['WAVECAR']
            task_label = 'Convergence_Iteration: ' + str(niter)

            hviter=np.heaviside((niter-1),0) 

            nbgwfactor = nbgwfactor + nbgwfactor*hviter*convsteps[0]
            encutgw = encutgw + encutgw*hviter*convsteps[1]
            nomegagw = nomegagw + nomegagw*hviter*convsteps[2] 
            
            nbands=round(nocc*nbgwfactor)
            encutgw=round(encutgw)
            nomegagw=round(nomegagw)

            if no_conv==False:
                if hviter==0:
                    print('Convergence test will be performed using following values')
                    print('Iteration, NBANDS, ENCUTGW, NOMEGA')
                print('%10i' %niter, '%7i' %nbands, '%8i' %encutgw, '%6i' %nomegagw)
            else:
                if hviter==0:
                    print('values of follwing parameters will be used')
                    print('NBANDS, ENCUTGW, NOMEGA')
                    print('%7i' %nbands, '%8i' %encutgw, '%6i' %nomegagw)
            
            if prev_calc_dir:
                t.append(CopyOutputFiles(additional_files=files2copy, calc_dir=prev_calc_dir, contcar_to_poscar=True))
            elif parents:
                if prev_calc_loc:
                    t.append(
                        CopyOutputFiles(additional_files=files2copy, calc_loc=prev_calc_loc, contcar_to_poscar=True))
            vasp_input_set = CreateInputs(structure, mode='DIAG', nbands=nbands, kpar=kpar,
                                          reciprocal_density=reciprocal_density, two_dim=two_dim)
            t.append(WriteVaspFromIOSet(structure=structure,
                                        vasp_input_set=vasp_input_set,
                                        vasp_input_params=vasp_input_params))
            t.append(Run_Vasp(vasp_cmd=vasp_cmd))
            vasp_input_set = CreateInputs(structure,mode='CONV',nbands=nbands,encutgw=encutgw,nomegagw=nomegagw,
                                          kpar=kpar,reciprocal_density=reciprocal_density,nbandsgw=nbandsgw,
                                          two_dim=two_dim)
            t.append(WriteVaspFromIOSet(structure=structure,
                                        vasp_input_set=vasp_input_set,
                                        vasp_input_params=vasp_input_params))
            if no_conv==False:
                t.append(Run_Vasp(vasp_cmd=vasp_cmd))
            t.append(SaveConvParams(nbands=nbands, encutgw=encutgw, nomegagw=nomegagw))
            t.append(CheckBeConv(niter=niter, tolerence=tolerence, no_conv=no_conv))
            t.append(PasscalClocsCond(name=name))
            if no_conv==False:
                t.append(gw2db(structure=structure, mat_name=mat_name, task_label=task_label, db_file=db_file, defuse_unsuccessful=False))
            t.append(StopIfConverged())
        tracker = Tracker('vasp.log', nlines=100)
        super(convFW, self).__init__(t, parents=parents, name=fw_name, spec={"_trackers": [tracker]}, **kwargs)


class GwFW(Firework):
    def __init__(self, mat_name=None, structure=None, tolerence=None, no_conv=None, reciprocal_density=None,
                 vasp_input_set=None, vasp_input_params=None, nbandso=None, nbandsv=None, nbandsgw=None,
                 vasp_cmd="vasp", prev_calc_loc=True, prev_calc_dir=None, db_file=None, wannier_fw=None, two_dim=False,
                 vasptodb_kwargs={}, job_tag=None, parents=None, **kwargs):
        """
        Your Comments Here
        """
        t = []
        name = "GW"
        fw_name = "{}-{}".format(mat_name, name)
        files2copy = ['WAVECAR', 'WAVEDER']
        if prev_calc_dir:
            t.append(CopyOutputFiles(additional_files=files2copy, calc_dir=prev_calc_dir, contcar_to_poscar=True))
        elif parents:
            if prev_calc_loc:
                t.append(CopyOutputFiles(additional_files=files2copy, calc_loc=prev_calc_loc, contcar_to_poscar=True))
        t.append(WriteGWInput(structure=structure, reciprocal_density=reciprocal_density, nbandsgw=nbandsgw,
                                wannier_fw=wannier_fw, two_dim=two_dim))
        for niter in range(1, 10):
            task_label = 'scGW_Iteration: ' + str(niter)
            if wannier_fw:
                t.append(WriteWannierInputForGW(structure=structure, reciprocal_density=reciprocal_density,nbandsgw=nbandsgw))
            t.append(Run_Vasp(vasp_cmd=vasp_cmd))
            t.append(CheckBeConv(niter=niter, tolerence=tolerence, no_conv=no_conv))
            t.append(PasscalClocsCond(name=name))
            t.append(MakeWFilesList())
            t.append(
                gw2db(structure=structure, mat_name=mat_name, task_label=task_label, job_tag=job_tag, db_file=db_file,
                      defuse_unsuccessful=False))
            t.append(StopIfConverged())
        tracker = Tracker('vasp.log', nlines=100)

        super(GwFW, self).__init__(t, parents=parents, name=fw_name, spec={"_trackers": [tracker]}, **kwargs)


class BseFW(Firework):
    def __init__(self, mat_name=None, structure=None, reciprocal_density=None, vasp_input_set=None,
                 vasp_input_params=None, enwinbse=None, two_dim=False,
                 vasp_cmd="vasp", prev_calc_loc=True, prev_calc_dir=None, db_file=None, vasptodb_kwargs={},
                 job_tag=None, parents=None, **kwargs):
        """
        Your Comments Here
        """
        t = []
        name = "BSE"
        fw_name = "{}-{}".format(mat_name, name)
        files2copy = ['WAVECAR', 'WAVEDER']
        if prev_calc_dir:
            t.append(CopyOutputFiles(additional_files=files2copy, calc_dir=prev_calc_dir, contcar_to_poscar=True))
        elif parents:
            if prev_calc_loc:
                t.append(CopyOutputFiles(additional_files=files2copy, calc_loc=prev_calc_loc, contcar_to_poscar=True))
        t.append(SaveNbandsov(enwinbse=enwinbse))
        t.append(WriteBSEInput(structure=structure, reciprocal_density=reciprocal_density, two_dim=two_dim))
        t.append(Run_Vasp(vasp_cmd=vasp_cmd))
        t.append(bse2db(structure=structure, mat_name=mat_name, task_label=name, job_tag=job_tag, db_file=db_file,
                        defuse_unsuccessful=False))
        tracker = Tracker('vasp.log', nlines=100)

        super(BseFW, self).__init__(t, parents=parents, name=fw_name, state='PAUSED', spec={"_trackers": [tracker]},
                                    **kwargs)


class EmcFW(Firework):
    def __init__(self, mat_name=None, structure=None, nbands=None, kpar=None, reciprocal_density=None, steps=None,
                 vasp_input_set=None, vasp_input_params=None, two_dim=False,
                 vasp_cmd="vasp", sumo_cmd='sumo', prev_calc_loc=True, prev_calc_dir=None, db_file=None,
                 vasptodb_kwargs={}, parents=None, **kwargs):
        """
        Your Comments Here
        """
        t = []

        vasp_input_set = CreateInputs(structure, mode='EMC', kpar=kpar, reciprocal_density=reciprocal_density,
                                      nbands=nbands, two_dim=two_dim)
        name = 'EMC'
        fw_name = "{}-{}".format(mat_name, name)
        if prev_calc_dir:
            t.append(CopyOutputFiles(calc_dir=prev_calc_dir, additional_files=["CHGCAR"]))
        elif parents:
            t.append(CopyOutputFiles(calc_loc=True, additional_files=["CHGCAR"]))
        else:
            raise ValueError("Must specify previous calculation for NonScfFW")
        t.append(WriteVaspFromIOSet(structure=structure,
                                    vasp_input_set=vasp_input_set,
                                    vasp_input_params=vasp_input_params))
        t.append(Run_Vasp(vasp_cmd=vasp_cmd))
        t.append(Run_Sumo(sumo_cmd=sumo_cmd))
        t.append(emc2db(structure=structure, mat_name=mat_name, db_file=db_file, defuse_unsuccessful=False))
        super(EmcFW, self).__init__(t, parents=parents, name=fw_name, **kwargs)


class WannierCheckFW(Firework):
    def __init__(self, ppn=None, kpar=None, mat_name=None, structure=None, reciprocal_density=None, vasp_input_set=None,
                 vasp_input_params=None, two_dim=False,
                 vasp_cmd="vasp", wannier_cmd=None, prev_calc_loc=True, prev_calc_dir=None, db_file=None,
                 vasptodb_kwargs={}, parents=None, **kwargs):
        """
        Your Comments Here
        """
        t = []
        name = "WANNIER_CHECK"
        fw_name = "{}-{}".format(mat_name, name)
        t.append(CopyOutputFiles(calc_loc=prev_calc_loc, contcar_to_poscar=True))
        t.append(WriteWannierInputForDFT(structure=structure, reciprocal_density=reciprocal_density, ppn=ppn, write_hr=False))
        t.append(Run_Vasp(vasp_cmd=vasp_cmd))
        t.append(WriteWannierInputForDFT(structure=structure, reciprocal_density=reciprocal_density, ppn=ppn, write_hr=True))
        t.append(Run_Wannier(wannier_cmd=wannier_cmd))
        vasp_input_set = CreateInputs(structure, mode='EMC', kpar=kpar, reciprocal_density=reciprocal_density,
                                      two_dim=two_dim)
        t.append(WriteVaspFromIOSet(structure=structure,
                                    vasp_input_set=vasp_input_set,
                                    vasp_input_params=vasp_input_params))
        t.append(CopyKptsWan2vasp())
        t.append(Run_Vasp(vasp_cmd=vasp_cmd))
        t.append(Wannier2DB(structure=structure, mat_name=mat_name, task_label='CHECK_WANNIER_INTERPOLATION',
                            db_file=db_file, compare_vasp=True, defuse_unsuccessful=False))
        tracker = Tracker('vasp.log', nlines=100)

        super(WannierCheckFW, self).__init__(t, parents=parents, name=fw_name, spec={"_trackers": [tracker]}, **kwargs)


class WannierFW(Firework):
    def __init__(self, structure=None, mat_name=None, wannier_cmd=None, prev_calc_loc=True, prev_calc_dir=None,
                 db_file=None, parents=None, **kwargs):
        """
        Your Comments Here
        """
        t = []
        name = "WANNIER"
        fw_name = "{}-{}".format(mat_name, name)
        files2copy = ['wannier90.win', 'wannier90.mmn', 'wannier90.amn', 'wannier90.eig']
        t.append(CopyOutputFiles(additional_files=files2copy, calc_loc=prev_calc_loc, contcar_to_poscar=True))
        t.append(Run_Wannier(wannier_cmd=wannier_cmd))
        t.append(Wannier2DB(structure=structure, mat_name=mat_name, task_label='GW_BANDSTRUCTURE', db_file=db_file,
                            compare_vasp=False, defuse_unsuccessful=False))
        tracker = Tracker('wannier90.wout', nlines=100)

        super(WannierFW, self).__init__(t, parents=parents, name=fw_name, spec={"_trackers": [tracker]}, **kwargs)
