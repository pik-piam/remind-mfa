from ODYM.odym.modules.ODYM_Classes import MFAsystem

class SimsonMFASystem(MFAsystem):

    def slice_id(self, all_dims_str, **kwargs):
        all_dims = tuple(all_dims_str)
        ids_out = [slice(None) for _ in all_dims]
        for dim_letter, item_name in kwargs.items():
            aspect_name = self.aspect_name_from_index_letter(dim_letter)
            item_list = self.item_list_from_aspect_name(aspect_name)
            ids_out[all_dims.index(dim_letter)] = item_list.index(item_name)
        return tuple(ids_out)


    def aspect_name_from_index_letter(self, dim_letter: str):
        return self.IndexTable.index[self.IndexTable.IndexLetter==dim_letter].values[0]


    def item_list_from_aspect_name(self, aspect_name: str):
        return self.IndexTable.loc[aspect_name, 'Classification'].Items
