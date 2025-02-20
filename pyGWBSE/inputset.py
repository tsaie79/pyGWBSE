# coding: utf-8
# Copyright (c) Pymatgen Development Team.
# Distributed under the terms of the MIT License.

import os

from monty.serialization import loadfn
from pymatgen.io.vasp.inputs import Incar, Kpoints
from pymatgen.io.vasp.sets import DictSet
from pymatgen.symmetry.bandstructure import HighSymmKpath

MODULE_DIR = os.path.dirname(os.path.abspath(__file__))

class CreateInputs(DictSet):
    """
    Your Comments Here
    """
    CONFIG = loadfn(os.path.join(MODULE_DIR, "inputset.yaml"))

    SUPPORTED_MODES = ("DIAG", "GW", "STATIC", "BSE", "CONV", "EMC")

    def __init__(self, structure, prev_incar=None, nbands=None, nomegagw=None, encutgw=None,
                 potcar_functional="PBE_54", reciprocal_density=100, kpoints_line_density = 100, kpar=None, nbandsgw=None,
                 mode="STATIC", copy_wavecar=True, nbands_factor=5, ncores=16,nbandso=None, nbandsv=None,
                 wannier_fw=None, two_dim=False,
                 **kwargs):
        super().__init__(structure, CreateInputs.CONFIG, **kwargs)
        self.prev_incar = prev_incar
        self.nbands = nbands
        self.encutgw = encutgw
        self.nomegagw = nomegagw
        self.potcar_functional = potcar_functional
        self.reciprocal_density = reciprocal_density
        self.kpoints_line_density = kpoints_line_density
        self.mode = mode.upper()
        if self.mode not in CreateInputs.SUPPORTED_MODES:
            raise ValueError("%s not one of the support modes : %s" %
                             (self.mode, CreateInputs.SUPPORTED_MODES))
        self.kwargs = kwargs
        self.copy_wavecar = copy_wavecar
        self.nbands_factor = nbands_factor
        self.ncores = ncores
        self.kpar = kpar
        self.nbandsgw = nbandsgw
        self.nbandso = nbandso
        self.nbandsv = nbandsv
        self.wannier_fw = wannier_fw
        self.two_dim = two_dim

    @property
    def kpoints(self):
        """
        Generate gamma center k-points mesh grid for GW calc,
        which is requested by GW calculation.
        """
        _fake_stucture = self.structure.copy()
        if self.two_dim:
            _fake_stucture.make_supercell([1, 1, 4])

        if self.mode == "EMC":
            kpath = HighSymmKpath(_fake_stucture)
            frac_k_points, k_points_labels = kpath.get_kpoints(
                line_density=self.kpoints_line_density,
                coords_are_cartesian=False)
            kpoints = Kpoints(
                comment="Non SCF run along symmetry lines",
                style=Kpoints.supported_modes.Reciprocal,
                num_kpts=len(frac_k_points),
                kpts=frac_k_points, labels=k_points_labels,
                kpts_weights=[1] * len(frac_k_points))

            return kpoints

        else:

            kpoints=Kpoints.automatic_density_by_vol(_fake_stucture,
                                        self.reciprocal_density, force_gamma=True)
            
            return kpoints

    @property
    def incar(self):
        """
        Your Comments Here
        """
        parent_incar = super().incar
        incar = Incar(self.prev_incar) if self.prev_incar is not None else \
            Incar(parent_incar)
        if self.wannier_fw == True:
            incar.update({
                "LWANNIER90": True
            })
        if self.mode == "EMC":
            incar.update({
                "IBRION": -1,
                "ISMEAR": 0,
                "SIGMA": 0.001,
                "LCHARG": False,
                "LORBIT": 11,
                "LWAVE": False,
                "NSW": 0,
                "ISYM": 0,
                "ICHARG": 11
            })
            incar.pop("LWANNIER90", None)
            incar.pop("LEPSILON", None)
        if self.mode == "DIAG":
            # Default parameters for diagonalization calculation.
            incar.update({
                "ALGO": "Exact",
                "NELM": 1,
                "LOPTICS": True,
                "LPEAD": True
            })
            incar.pop("LEPSILON", None)
            incar.pop("LWANNIER90", None)
        elif self.mode == "GW":
            # Default parameters for GW calculation.
            incar.update({
                "ALGO": "GW",
                "NELM": 1,
                "NOMEGA": self.nomegagw,
                "ENCUTGW": self.encutgw,
                "NBANDSGW": self.nbandsgw,
                "LWAVE": True 
            })
            if self.wannier_fw == True:
                incar.update({
                    "LWANNIER90": True
                })
            incar.pop("EDIFF", None)
            incar.pop("LOPTICS", None)
            incar.pop("LPEAD", None)
            incar.pop("LEPSILON", None)
        elif self.mode == "CONV":
            # Default parameters for GW calculation.
            incar.update({
                "ALGO": "GW0",
                "NELM": 1,
                "NOMEGA": self.nomegagw,
                "ENCUTGW": self.encutgw,
                "NBANDSGW": self.nbandsgw,
                "LWAVE": False
            })
            incar.pop("EDIFF", None)
            incar.pop("LOPTICS", None)
            incar.pop("LEPSILON", None)
            incar.pop("LPEAD", None)
            incar.pop("LWANNIER90", None)
        elif self.mode == "BSE":
            # Default parameters for BSE calculation.
            incar.update({
                "ALGO": "BSE",
                "ANTIRES": 0,
                "NBANDSO": self.nbandso,
                "NBANDSV": self.nbandsv,
                "KPAR": 1,
                "CSHIFT": 0.2
            })
            incar.pop("LEPSILON", None)
            incar.pop("LWANNIER90", None)
        if self.nbands:
            incar["NBANDS"] = self.nbands

        if self.kpar:
            incar["KPAR"] = self.kpar

        rd=self.reciprocal_density    

        incar["SYSTEM"] = 'reciprocal density: '+str(rd)

        # Respect user set INCAR.
        incar.update(self.kwargs.get("user_incar_settings", {}))

        return incar

