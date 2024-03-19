from ODYM.odym.modules.ODYM_Classes import MFAsystem

class SimsonMFASystem(MFAsystem):

    def slice_id(self, all_dims_str, **kwargs):
        all_dims = tuple(all_dims_str)
        ids_out = [slice(None) for _ in all_dims]
        for dim_name, item_name in kwargs.items():
            aspect_name = self.IndexTable.index[self.IndexTable.IndexLetter==dim_name].values[0]
            item_list = self.IndexTable.loc[aspect_name, 'Classification'].Items
            ids_out[all_dims.index(dim_name)] = item_list.index(item_name)
        return tuple(ids_out)

