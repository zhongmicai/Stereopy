#!/usr/bin/env python3
# coding: utf-8
"""
@author: Ping Qiu  qiuping1@genomics.cn
@last modified by: Ping Qiu
@file:spatial_lag.py
@time:2021/04/19
"""
from ..core.tool_base import ToolBase
from ..utils.data_helper import get_cluster_res, get_position_array
from anndata import AnnData
from pysal.model import spreg
from pysal.lib import weights
import numpy as np
import pandas as pd
from tqdm import tqdm
from random import sample
from ..core.stereo_result import SpatialLagResult


class SpatialLag(ToolBase):
    def __init__(self, andata: AnnData, method='gm_lag', name='spatial_lag', cluster=None, genes=None,
                 random_drop=True, drop_dummy=None, n_neighbors=8):
        super(SpatialLag, self).__init__(data=andata, method=method, name=name)
        self.param = self.get_params(locals())
        self.cluster = get_cluster_res(self.data, data_key=cluster)
        self.genes = genes
        self.random_drop = random_drop
        self.drop_dummy = drop_dummy
        self.n_neighbors = n_neighbors
        self.position = get_position_array(self.data, obs_key='spatial')

    def fit(self):
        x, uniq_group = self.get_data()
        res = self.gm_model(x, uniq_group)
        result = SpatialLagResult(name=self.name, param=self.param, score=res)
        self.add_result(result=result, key_added=self.name)

    def get_data(self):
        group_num = self.cluster['cluster'].value_counts()
        max_group, min_group, min_group_ncells = group_num.index[0], group_num.index[-1], group_num[-1]
        df = pd.DataFrame({'group': self.cluster['cluster']})
        drop_columns = None
        if self.random_drop:
            df.iloc[sample(np.arange(self.data.n_obs).tolist(), min_group_ncells), :] = 'others'
            drop_columns = ['group_others']
        if self.drop_dummy:
            group_inds = np.where(df['group'] == self.drop_dummy)[0]
            df.iloc[group_inds, :] = 'others'
            drop_columns = ['group_others', 'group_' + str(self.drop_dummy)]
        x = pd.get_dummies(data=df, drop_first=False)
        if drop_columns is not None:
            x.drop(columns=drop_columns, inplace=True)
        uniq_group = set(self.cluster['cluster']).difference([self.drop_dummy]) if self.drop_dummy is not None \
            else set(self.cluster['cluster'])
        return x, list(uniq_group)

    def get_genes(self):
        if self.genes is None:
            genes = self.data.var.index
        else:
            genes = self.data.var.index.intersection(self.genes)
        return genes

    def gm_model(self, x, uniq_group):
        knn = weights.distance.KNN.from_array(self.position, k=self.n_neighbors)
        knn.transform = 'R'
        genes = self.get_genes()
        result = pd.DataFrame(index=genes)
        for i in ['const'] + uniq_group + ['W_log_exp']:
            result[str(i) + '_lag_coeff'] = None
            result[str(i) + '_lag_zstat'] = None
            result[str(i) + '_lag_pval'] = None
        for i, cur_g in tqdm(enumerate(genes),
                             desc="performing GM_lag_model and assign coefficient and p-val to cell type"):
            x['log_exp'] = self.data[:, cur_g].X
            try:
                model = spreg.GM_Lag(x[['log_exp']].values, x.values,
                                     w=knn, name_y='log_exp', name_x=x.columns)
                a = pd.DataFrame(model.betas, model.name_x + ['W_log_exp'], columns=['coef'])
                b = pd.DataFrame(model.z_stat, model.name_x + ['W_log_exp'], columns=['z_stat', 'p_val'])
                df = a.merge(b, left_index=True, right_index=True)
                print(df.head())
                for ind, g in enumerate(['const'] + uniq_group + ['W_log_exp']):
                    result.loc[cur_g, str(g) + '_GM_lag_coeff'] = df.iloc[ind, 0]
                    result.loc[cur_g, str(g) + '_GM_lag_zstat'] = df.iloc[ind, 1]
                    result.loc[cur_g, str(g) + '_GM_lag_pval'] = df.iloc[ind, 2]
            except Exception as e:
                print(e)
                for ind, g in enumerate(['const'] + uniq_group + ['W_log_exp']):
                    result.loc[cur_g, str(g) + '_GM_lag_coeff'] = np.nan
                    result.loc[cur_g, str(g) + '_GM_lag_zstat'] = np.nan
                    result.loc[cur_g, str(g) + '_GM_lag_pval'] = np.nan
        return result
