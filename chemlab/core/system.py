import numpy as np
from .base import ChemicalEntity, Field, Attribute, Relation, InstanceRelation
 
class Atom(ChemicalEntity):
    __dimension__ = 'atom'
    __fields__ = {
        'r_array' : Field(alias='r', shape=(3,), dtype='float'),
        'type_array' : Field(dtype='S4'),
        'charge_array' : Field(dtype='float')
    }

    def __init__(self, type, r_array):
        super(Atom, self).__init__()
        self.r_array = r_array
        self.type_array = type

class Molecule(ChemicalEntity):
    __dimension__ = 'molecule'
    
    __attributes__ = {
        'r_array' : Attribute(shape=(3,), dtype='float', dim='atom'),
        'type_array' : Attribute(dtype='str', dim='atom'),
        'charge_array' : Attribute(dim='atom')
    }
    __relations__ = {
        'bonds' : Relation(map='atom', shape=(2,), dim='bond')
    }
    __fields__ = {
        'molecule_name' : Field(dtype='str'),
        'export': Field(dtype=object)
    }
    
    def __init__(self, atoms, export=None, bonds=None):
        super(Molecule, self).__init__()
        self._from_entities(atoms, 'atom')
        
        self.export = export
        self.bonds = bonds
        if bonds:
            self.dimensions['bond'] = len(bonds)
        

class System(ChemicalEntity):
    __dimension__ = 'system'
    __attributes__ = {
        'r_array' : Attribute(shape=(3,), dtype='float', dim='atom'),
        'type_array' : Attribute(dtype='str', dim='atom'),
        'charge_array' : Attribute(dim='atom'),
        'molecule_name' : Attribute(dtype='str', dim='molecule')
    }
    
    __relations__ = {
        'bonds' : Relation(map='atom', shape=(2,), dim='bond'),
    }
    
    __fields__ = {
        'cell_lengths' : Field(dtype='float', shape=(3,))
    }
    
    def __init__(self, molecules=None):
        super(System, self).__init__()
        
        if molecules is None:
            molecules = []
        self.dimensions = {'molecule' : len(molecules),
                           'atom': sum(m.dimensions['atom'] for m in molecules),
                           'bond': sum(m.dimensions['bond'] for m in molecules)}
        
        if molecules:
            self._from_entities(molecules, 'molecule')

    
    @classmethod
    def empty(cls, molecule, atom):
        inst = super(System, cls).empty(atom=atom, molecule=molecule)
        return inst

    @property
    def n_mol(self):
        return self.dimensions['molecule']
    
    @property
    def n_atoms(self):
        return self.dimensions['atom']

    # Old API
    @property
    def mol_indices(self):
        steps = np.ediff1d(self.maps['atom', 'molecule'].value)
        steps = np.insert(steps, 0, 1)
        return np.nonzero(steps)[0]
    
    @property
    def mol_n_atoms(self):
        idx = self.mol_indices
        idx = np.append(idx, len(self.maps['atom', 'molecule'].value))
        return np.ediff1d(idx)

    @property
    def molecules(self):
        return MoleculeGenerator(self)

    @property
    def atoms(self):
        return AtomGenerator(self)

    @classmethod
    def from_arrays(cls, **kwargs):
        '''Initialize a System from its constituent arrays. It is the
        fastest way to initialize a System, well suited for 
        reading one or more big System from data files.

        **Parameters**
        
        The following parameters are required:
        
        - type_array
        - mol_indices

        To further speed up the initialization process you optionally      
        pass the other derived arrays:

        - r_array
        - m_array
        - mol_n_atoms
        - atom_export_array
        - mol_export

        **Example**
        
        Our classic example of 3 water molecules::

                r_array = np.random.random((3, 9))
                type_array = ['O', 'H', 'H', 'O', 'H', 'H', 'O', 'H', 'H']
                mol_indices = [0, 3, 6]
                System.from_arrays(r_array=r_array, type_array=type_array,
                                   mol_indices=mol_indices)

        '''
        
        if 'mol_indices' not in kwargs:
            raise Exception('mol_indices is a required argument.')
        
        if 'type_array' not in kwargs:
            raise Exception('type_array is a required argument.')
        
        inst = cls.empty(len(kwargs['mol_indices']), len(kwargs['type_array']))
        # We need to setup the proper maps
        inst.maps['atom', 'molecule'] = InstanceRelation('map', dim='atom', map='molecule', index=range(inst.n_atoms))
        mol_sizes = np.ediff1d(np.concatenate([kwargs['mol_indices'], [inst.n_atoms]]))
        inst.maps['atom', 'molecule'].value = sum([[i] * m for i, m in enumerate(mol_sizes)], [])
        
        inst.maps['bond', 'molecule'] = InstanceRelation('map', dim='bond', map='molecule', index=[0])
        kwargs.pop('mol_indices')
        
        for arg, val in kwargs.items():
            setattr(inst, arg, val)
        
        return inst

    def get_molecule(self, index):
        return self.subentity(Molecule, index)
    
    def add(self, molecule):
        self.add_entity(molecule, Molecule)
        
    def where(self, **kwargs):
        """Return a subsystem where the conditions are met"""
        
        for stmt, arg in kwargs.items():
            if stmt is 'molecule_index':
                return self.sub_dimension(arg, 'molecule')

# TODO: deprecated

class MoleculeGenerator(object):
    def __init__(self, system):
        self.system = system

    def __getitem__(self, key):
        if isinstance(key, slice):
            ind = range(*key.indices(self.system.n_mol))
            ret = []
            for i in ind:
                ret.append(self.system.get_molecule(i))

            return ret

        if isinstance(key, int):
            return self.system.get_molecule(key)


class AtomGenerator(object):
    def __init__(self, system):
        self.system = system

    def __getitem__(self, key):
        if isinstance(key, slice):
            ind = range(*key.indices(self.system.n_mol))
            ret = []
            for i in ind:
                ret.append(self.system.get_atom(i))

            return ret

        if isinstance(key, int):
            return self.system.get_atom(key)


def subsystem_from_molecules(orig, selection):
    '''Create a system from the *orig* system by picking the molecules
    specified in *selection*.

    **Parameters**

    orig: System
        The system from where to extract the subsystem
    selection: np.ndarray of int or np.ndarray(N) of bool
        *selection* can be either a list of molecular indices to
        select or a boolean array whose elements are True in correspondence
        of the molecules to select (it is usually the result of a numpy
        comparison operation).
    
    **Example**

    In this example we can see how to select the molecules whose
    center of mass that is in the region of space x > 0.1::
    
        s = System(...) # It is a set of 10 water molecules
    
        select = []
        for i range(s.n_mol):
           if s.get_molecule(i).center_of_mass[0] > 0.1:
               select.append(i)
        
        subs = subsystem_from_molecules(s, np.ndarray(select)) 
    
    
    .. note:: The API for operating on molecules is not yet fully 
              developed. In the future there will be smarter
              ways to *filter* molecule attributes instead of
              looping and using System.get_molecule.
    
    '''
    return orig.where(molecule_index=selection)


def subsystem_from_atoms(orig, selection):
    '''Generate a subsystem containing the atoms specified by
    *selection*. If an atom belongs to a molecule, the whole molecule is
    selected.

    **Example**
    
    This function can be useful when selecting a part of a system
    based on positions. For example, in this snippet you can see
    how to select the part of the system (a set of molecules) whose
    x coordinates is bigger than 1.0 nm::
    
        s = System(...)
        subs = subsystem_from_atoms(s.r_array[0,:] > 1.0)
    
    **Parameters**

    orig: System
       Original system.
    selection: np.ndarray of int or np.ndarray(NA) of bool
       A boolean array that is True when the ith atom has to be selected or
       a set of atomic indices to be included.

    Returns:

    A new System instance.

    '''
    return orig.where(atom_index=selection)

def merge_systems(sysa, sysb, bounding=0.2):
    '''Generate a system by merging *sysa* and *sysb*.

    Overlapping molecules are removed by cutting the molecules of
    *sysa* that have atoms near the atoms of *sysb*. The cutoff distance
    is defined by the *bounding* parameter.

    **Parameters**

    sysa: System
       First system
    sysb: System
       Second system
    bounding: float or False
       Extra space used when cutting molecules in *sysa* to make space
       for *sysb*. If it is False, no overlap handling will be performed.

    '''

    if bounding is not False:
        # Delete overlaps.
        if sysa.box_vectors is not None:
            periodicity = sysa.box_vectors.diagonal()
        else:
            periodicity = False

        p = overlapping_points(sysb.r_array, sysa.r_array,
                               cutoff=bounding, periodic=periodicity)

        sel = np.ones(len(sysa.r_array), dtype=np.bool)
        sel[p] = False

        # Rebuild sysa without water molecules
        sysa = subsystem_from_atoms(sysa, sel)
    
    sysres = System.empty(sysa.n_mol + sysb.n_mol, sysa.n_atoms + sysb.n_atoms)
    
    # Assign the attributes
    for attr in type(sysa).attributes:
        attr.assign(sysres,
                    attr.concatenate(sysa, sysb))
    
    # edit the mol_indices and n_mol
    offset = sysa.mol_indices[-1] + sysa.mol_n_atoms[-1]
    sysres.mol_indices[0:sysa.n_mol] = sysa.mol_indices.copy()
    sysres.mol_indices[sysa.n_mol:] = sysb.mol_indices.copy() + offset
    sysres.mol_n_atoms = np.concatenate([sysa.mol_n_atoms, sysb.mol_n_atoms])
    
    sysres.box_vectors = sysa.box_vectors
    
    return sysres


if __name__ == '__main__':
    test_empty() 
