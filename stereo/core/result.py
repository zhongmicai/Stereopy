from warnings import warn

import pandas as pd
from anndata import AnnData


class _BaseResult(object):
    CLUSTER_NAMES = {'leiden', 'louvain', 'phenograph', 'annotation', 'leiden_from_bins', 'louvain_from_bins', 'phenograph_from_bins', 'annotation_from_bins'}
    CONNECTIVITY_NAMES = {'neighbors'}
    REDUCE_NAMES = {'umap', 'pca', 'tsne'}
    HVG_NAMES = {'highly_variable_genes', 'hvg'}
    MARKER_GENES_NAMES = {'marker_genes', 'rank_genes_groups'}

    RENAME_DICT = {'highly_variable_genes': 'hvg', 'marker_genes': 'rank_genes_groups'}

    CLUSTER, CONNECTIVITY, REDUCE, HVG, MARKER_GENES = 0, 1, 2, 3, 4
    TYPE_NAMES_DICT = {
        CLUSTER: CLUSTER_NAMES,
        CONNECTIVITY: CONNECTIVITY_NAMES,
        REDUCE: REDUCE_NAMES,
        HVG: HVG_NAMES,
        MARKER_GENES: MARKER_GENES_NAMES
    }


class Result(_BaseResult, dict):

    def __init__(self, stereo_exp_data):
        super().__init__()
        self.__stereo_exp_data = stereo_exp_data

    def __contains__(self, item):
        if item in self.__stereo_exp_data.genes:
            return True
        elif item in self.__stereo_exp_data.cells:
            return True
        return dict.__contains__(self, item)

    def __getitem__(self, name):
        genes = self.__stereo_exp_data.genes
        cells = self.__stereo_exp_data.cells
        if name in genes:
            if name in genes._var:
                warn(
                    f'{name} will be moved from `StereoExpData.tl.result` to `StereoExpData.genes` in the '
                    f'future, make sure your code access the property correctly. See more details at: https://www.baidu.com',
                    category=FutureWarning
                )
                return genes._var[name]
            elif name in genes._matrix:
                warn(
                    f'FutureWarning: {name} will be moved from `StereoExpData.tl.result` to `StereoExpData.genes_matrix` in the '
                    f'future, make sure your code access the property correctly. See more details at: https://www.baidu.com',
                    category=FutureWarning
                )
                return genes._matrix[name]
        elif name in cells:
            if name in cells._obs.columns:
                warn(
                    f'FutureWarning: {name} will be moved from `StereoExpData.tl.result` to `StereoExpData.cells` in the '
                    f'future, make sure your code access the property correctly. See more details at: https://www.baidu.com',
                    category=FutureWarning
                )
                if name in Result.CLUSTER_NAMES:
                    return pd.DataFrame(
                        {
                            'bins': cells.cell_name,
                            'group': cells._obs[name].values
                        }
                    )
                return cells._obs[name]
            elif name in cells._matrix:
                warn(
                    f'FutureWarning: {name} will be moved from `StereoExpData.tl.result` to `StereoExpData.cells_matrix` in the '
                    f'future, make sure your code access the property correctly. See more details at: https://www.baidu.com',
                    category=FutureWarning
                )
                return cells._matrix[name]
            elif name in cells._pairwise:
                warn(
                    f'FutureWarning: {name} will be moved from `StereoExpData.tl.result` to `StereoExpData.cells_pairwise` in the '
                    f'future, make sure your code access the property correctly. See more details at: https://www.baidu.com',
                    category=FutureWarning
                )
                return cells._pairwise[name]
        return dict.__getitem__(self, name)

    def _real_set_item(self, type, key, value):
        if type == Result.CLUSTER:
            self._set_cluster_res(key, value)
        elif type == Result.CONNECTIVITY:
            self._set_connectivities_res(key, value)
        elif type == Result.REDUCE:
            self._set_reduce_res(key, value)
        elif type == Result.HVG_NAMES:
            self._set_hvg_res(key, value)
        elif type == Result.MARKER_GENES:
            self._set_marker_genes_res(key, value)
        else:
            return False
        return True

    def __setitem__(self, key, value):
        for name_type, name_dict in Result.TYPE_NAMES_DICT.items():
            if key in name_dict and self._real_set_item(name_type, key, value):
                return
        for name_type, name_dict in Result.TYPE_NAMES_DICT.items():
            for like_name in name_dict:
                if not key.startswith('gene_exp_') and like_name in key and self._real_set_item(name_type, key, value):
                    return
        if type(value) is pd.DataFrame:
            if 'bins' in value.columns.values and 'group' in value.columns.values:
                self._set_cluster_res(key, value)
                return
            elif not {"means", "dispersions", "dispersions_norm", "highly_variable"} - set(value.columns.values):
                self._set_hvg_res(key, value)
                return
            elif len(value.shape) == 2 and value.shape[0] > 399 and value.shape[1] > 399:
                # TODO this is hard-code method to guess it's a reduce ndarray
                self._set_reduce_res(key, value)
                return
            elif key.startswith('gene_exp_'):
                dict.__setitem__(self, key, value)
                return
        elif type(value) is dict:
            if not {'connectivities', 'nn_dist'} - set(value.keys()):
                self._set_connectivities_res(key, value)
                return
        dict.__setitem__(self, key, value)

    def _set_cluster_res(self, key, value):
        assert type(value) is pd.DataFrame and 'group' in value.columns.values, f"this is not cluster res"
        warn(
            f'FutureWarning: {key} will be moved from `StereoExpData.tl.result` to `StereoExpData.cells` in the '
            f'future, make sure your code set the property correctly. See more details at: https://www.baidu.com',
            category=FutureWarning
        )
        self.__stereo_exp_data.cells._obs[key] = value['group'].values

    def _set_connectivities_res(self, key, value):
        assert type(value) is dict and not {'connectivities', 'nn_dist'} - set(value.keys()), \
            f'not enough key to set connectivities'
        warn(
            f'FutureWarning: {key} will be moved from `StereoExpData.tl.result` to `StereoExpData.cells_pairwise` in the '
            f'future, make sure your code set the property correctly. See more details at: https://www.baidu.com',
            category=FutureWarning
        )
        self.__stereo_exp_data.cells._pairwise[key] = value

    def _set_reduce_res(self, key, value):
        assert type(value) is pd.DataFrame, f'reduce result must be pandas.DataFrame'
        warn(
            f'FutureWarning: {key} will be moved from `StereoExpData.tl.result` to `StereoExpData.cells_matrix` in the '
            f'future, make sure your code set the property correctly. See more details at: https://www.baidu.com',
            category=FutureWarning
        )
        self.__stereo_exp_data.cells._matrix[key] = value

    def _set_hvg_res(self, key, value):
        dict.__setitem__(self, key, value)

    def _set_marker_genes_res(self, key, value):
        dict.__setitem__(self, key, value)


class AnnBasedResult(_BaseResult, object):

    def __init__(self, based_ann_data: AnnData):
        super().__init__()
        self.__based_ann_data = based_ann_data

    def __contains__(self, item):
        if item in AnnBasedResult.CLUSTER_NAMES:
            return item in self.__based_ann_data.obs
        elif item in AnnBasedResult.CONNECTIVITY_NAMES:
            return item in self.__based_ann_data.uns
        elif item in AnnBasedResult.REDUCE_NAMES:
            return f'X_{item}' in self.__based_ann_data.obsm
        elif item in AnnBasedResult.HVG_NAMES:
            if item in self.__based_ann_data.uns:
                return True
            elif AnnBasedResult.RENAME_DICT.get(item, None) in self.__based_ann_data.uns:
                return True
        elif item in AnnBasedResult.MARKER_GENES_NAMES:
            if item in self.__based_ann_data.uns:
                return True
            elif AnnBasedResult.RENAME_DICT.get(item, None) in self.__based_ann_data.uns:
                return True
        elif item.startswith('gene_exp_'):
            if item in self.__based_ann_data.uns:
                return True

        obsm_obj = self.__based_ann_data.obsm.get(f'X_{item}', None)
        if obsm_obj is not None:
            return True
        obsm_obj = self.__based_ann_data.obsm.get(f'{item}', None)
        if obsm_obj is not None:
            return True
        obs_obj = self.__based_ann_data.obs.get(item, None)
        if obs_obj is not None:
            return True
        uns_obj = self.__based_ann_data.uns.get(item, None)
        if uns_obj and 'params' in uns_obj and 'connectivities_key' in uns_obj['params'] and 'distances_key' in uns_obj[
            'params']:
            return True
        return False

    def __getitem__(self, name):
        if name in AnnBasedResult.CLUSTER_NAMES:
            return pd.DataFrame(self.__based_ann_data.obs[name].values, columns=['group'],
                                index=self.__based_ann_data.obs_names)
        elif name in AnnBasedResult.CONNECTIVITY_NAMES:
            return {
                'neighbor': None,  # TODO really needed?
                'connectivities': self.__based_ann_data.obsp['connectivities'],
                'nn_dist': self.__based_ann_data.obsp['distances'],
            }
        elif name in AnnBasedResult.REDUCE_NAMES:
            return pd.DataFrame(self.__based_ann_data.obsm[f'X_{name}'], copy=False)
        elif name in AnnBasedResult.HVG_NAMES:
            # TODO ignore `mean_bin`, really need?
            return self.__based_ann_data.var.loc[:, ["means", "dispersions", "dispersions_norm", "highly_variable"]]
        elif name in AnnBasedResult.MARKER_GENES_NAMES:
            return self.__based_ann_data.uns[name]
        elif name.startswith('gene_exp_'):
            return self.__based_ann_data.uns[name]

        obsm_obj = self.__based_ann_data.obsm.get(f'X_{name}', None)
        if obsm_obj is not None:
            return pd.DataFrame(obsm_obj)
        obsm_obj = self.__based_ann_data.obsm.get(f'{name}', None)
        if obsm_obj is not None:
            return pd.DataFrame(obsm_obj)
        obs_obj = self.__based_ann_data.obs.get(name, None)
        if obs_obj is not None:
            return pd.DataFrame(self.__based_ann_data.obs[name].values, columns=['group'],
                                index=self.__based_ann_data.obs_names)
        uns_obj = self.__based_ann_data.uns.get(name, None)
        if uns_obj and 'params' in uns_obj and 'connectivities_key' in uns_obj['params'] and 'distances_key' in uns_obj[
            'params']:
            return {
                'neighbor': None,  # TODO really needed?
                'connectivities': self.__based_ann_data.obsp[uns_obj['params']['connectivities_key']],
                'nn_dist': self.__based_ann_data.obsp[uns_obj['params']['distances_key']],
            }
        raise Exception

    def _real_set_item(self, type, key, value):
        if type == AnnBasedResult.CLUSTER:
            self._set_cluster_res(key, value)
        elif type == AnnBasedResult.CONNECTIVITY:
            self._set_connectivities_res(key, value)
        elif type == AnnBasedResult.REDUCE:
            self._set_reduce_res(key, value)
        elif type == AnnBasedResult.HVG_NAMES:
            self._set_hvg_res(key, value)
        elif type == AnnBasedResult.MARKER_GENES:
            self._set_marker_genes_res(key, value)
        else:
            return False
        return True

    def __setitem__(self, key, value):
        for name_type, name_dict in AnnBasedResult.TYPE_NAMES_DICT.items():
            if key in name_dict and self._real_set_item(name_type, key, value):
                return

        for name_type, name_dict in AnnBasedResult.TYPE_NAMES_DICT.items():
            for like_name in name_dict:
                if not key.startswith('gene_exp_') and like_name in key and self._real_set_item(name_type, key, value):
                    return

        if type(value) is pd.DataFrame:
            if 'bins' in value.columns.values and 'group' in value.columns.values:
                self._set_cluster_res(key, value)
                return
            elif not {"means", "dispersions", "dispersions_norm", "highly_variable"} - set(value.columns.values):
                self._set_hvg_res(key, value)
                return
            elif len(value.shape) == 2 and value.shape[0] > 399 and value.shape[1] > 399:
                # TODO this is hard-code method to guess it's a reduce ndarray
                self._set_reduce_res(key, value)
                return
            elif key.startswith('gene_exp_'):
                self.__based_ann_data.uns[key] = value
                return
        elif type(value) is dict:
            if not {'connectivities', 'nn_dist'} - set(value.keys()):
                self._set_connectivities_res(key, value)
                return

        raise KeyError

    def _set_cluster_res(self, key, value):
        assert type(value) is pd.DataFrame and 'group' in value.columns.values, f"this is not cluster res"
        # FIXME ignore set params to uns, this may cause dirty data in uns, if it exist at the first time
        self.__based_ann_data.uns[key] = {'params': {}, 'source': 'stereopy', 'method': key}
        self.__based_ann_data.obs[key] = value['group'].values

    def _set_connectivities_res(self, key, value):
        assert type(value) is dict and not {'connectivities', 'nn_dist'} - set(value.keys()), \
            f'not enough key to set connectivities'
        self.__based_ann_data.uns[key] = {
            'params': {'method': 'umap'},
            'source': 'stereopy',
            'method': 'neighbors'
        }
        if key == 'neighbors':
            self.__based_ann_data.uns[key]['params']['connectivities_key'] = 'connectivities'
            self.__based_ann_data.uns[key]['params']['distances_key'] = 'distances'
            self.__based_ann_data.obsp['connectivities'] = value['connectivities']
            self.__based_ann_data.obsp['distances'] = value['nn_dist']
        else:
            self.__based_ann_data.uns[key]['params']['connectivities_key'] = f'{key}_connectivities'
            self.__based_ann_data.uns[key]['params']['distances_key'] = f'{key}_distances'
            self.__based_ann_data.obsp[f'{key}_connectivities'] = value['connectivities']
            self.__based_ann_data.obsp[f'{key}_distances'] = value['nn_dist']

    def _set_reduce_res(self, key, value):
        assert type(value) is pd.DataFrame, f'reduce result must be pandas.DataFrame'
        self.__based_ann_data.uns[key] = {'params': {}, 'source': 'stereopy', 'method': key}
        self.__based_ann_data.obsm[f'X_{key}'] = value.values

    def _set_hvg_res(self, key, value):
        self.__based_ann_data.uns[key] = {'params': {}, 'source': 'stereopy', 'method': key}
        self.__based_ann_data.var.loc[:, ["means", "dispersions", "dispersions_norm", "highly_variable"]] = \
            value.loc[:, ["means", "dispersions", "dispersions_norm", "highly_variable"]].values

    def _set_marker_genes_res(self, key, value):
        self.__based_ann_data.uns[key] = value
