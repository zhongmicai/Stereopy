#!/usr/bin/env python3
# coding: utf-8
"""
@file: st_pipeline.py
@description: 
@author: Ping Qiu
@email: qiuping1@genomics.cn
@last modified by: Ping Qiu

change log:
    2021/07/20  create file.
"""
import copy
from functools import wraps
from typing import Optional, Union
from multiprocessing import cpu_count

from anndata import AnnData
from typing_extensions import Literal

import numpy as np
import pandas as pd
from scipy.sparse import issparse

from ..log_manager import logger
from ..utils.time_consume import TimeConsume
from ..algorithm.algorithm_base import AlgorithmBase

tc = TimeConsume()


def logit(func):
    @wraps(func)
    def wrapped(*args, **kwargs):
        logger.info('start to run {}...'.format(func.__name__))
        tk = tc.start()
        res = func(*args, **kwargs)
        logger.info('{} end, consume time {:.4f}s.'.format(func.__name__, tc.get_time_consumed(key=tk, restart=False)))
        return res

    return wrapped


class StPipeline(object):

    def __init__(self, data):
        """
        A analysis tool sets for StereoExpData. include preprocess, filter, cluster, plot and so on.

        :param data: StereoExpData object.
        """
        self.data = data
        self.result = dict()
        self._raw = None
        self.key_record = {'hvg': [], 'pca': [], 'neighbors': [], 'umap': [], 'cluster': [], 'marker_genes': []}

    def __getattr__(self, item):
        dict_attr = self.__dict__.get(item, None)
        if dict_attr:
            return dict_attr

        # start with __ may not be our algorithm function, and will cause import problem
        if item.startswith('__'):
            raise AttributeError

        new_attr = AlgorithmBase.get_attribute_helper(item, self.data, self.result)
        if new_attr:
            self.__setattr__(item, new_attr)
            logger.info(f'register algorithm {new_attr} to {self}')
            return new_attr

        raise AttributeError(
            f'{item} not existed, please check the function name you called!'
        )

    @property
    def raw(self):
        """
        get the StereoExpData whose exp_matrix is raw count.

        :return:
        """
        return self._raw

    @raw.setter
    def raw(self, value):
        """
        set the raw data.

        :param value: StereoExpData.
        :return:
        """
        self._raw = copy.deepcopy(value)

    def reset_raw_data(self):
        """
        Reset `self.data` to the raw data saved in `self.raw` when you want data 
        get raw expression matrix.

        :return:
        """
        self.data = self.raw

    def raw_checkpoint(self):
        """
        Save current data to `self.raw`. Running this function will be a convinent choice, 
        when your data have gone through several steps of basic preprocessing.

        Parameters
        -----------------------------
        None

        Returns
        -----------------------------
        None
        """
        self.raw = self.data

    def reset_key_record(self, key, res_key):
        """
        reset key and coordinated res_key in key_record.
        :param key:
        :param res_key:
        :return:
        """
        if key in self.key_record.keys():
            if res_key in self.key_record[key]:
                self.key_record[key].remove(res_key)
            self.key_record[key].append(res_key)
        else:
            self.key_record[key] = [res_key]

    @logit
    def cal_qc(self):
        """
        Calculate the key indicators of quality control.

        Observation level metrics include:
            total_counts: - total number of counts for a cell
            n_genes_by_count: - number of genes expressed of counts for a cell
            pct_counts_mt: - percentage of total counts in a cell which are mitochondrial

        Parameters
        ---------------------

        Returns
        ---------------------
        A StereoExpData object storing quality control indicators, including two levels of obs(cell) and var(gene).

        """
        from ..preprocess.qc import cal_qc
        cal_qc(self.data)

    @logit
    def filter_cells(self, 
                     min_gene: int=None, 
                     max_gene: int=None, 
                     min_n_genes_by_counts: int=None, 
                     max_n_genes_by_counts: int=None,
                     pct_counts_mt: float=None, 
                     cell_list: list=None, 
                     inplace: bool=True):
        """
        Filter cells based on counts or the numbers of genes expressed.

        Parameters
        ----------------------
        min_gene
            - minimum number of genes expressed required for a cell to pass fitlering.
        max_gene
            - maximum number of genes expressed required for a cell to pass fitlering.
        min_n_genes_by_counts
            - minimum number of counts required for a cell to pass filtering.
        max_n_genes_by_counts
            - maximum number of counts required for a cell to pass filtering.
        pct_counts_mt
            - maximum number of pct_counts_mt required for a cell to pass filtering.
        cell_list
            - the list of cells to be filtered.
        inplace
            - whether to inplace the previous data or return a new data.

        Returns
        ------------------------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those filtered.
        """
        from ..preprocess.filter import filter_cells
        data = filter_cells(self.data, min_gene, max_gene, min_n_genes_by_counts, max_n_genes_by_counts, pct_counts_mt,
                            cell_list, inplace)
        return data

    @logit
    def filter_genes(self, 
                     min_cell: int=None, 
                     max_cell: int=None, 
                     gene_list: list=None, 
                     inplace: bool=True):
        """
        Filter genes based on the numbers of cells or counts.

        Parameters
        ---------------------
        min_cell
            - minimum number of cells expressed required for a gene to pass filering.
        max_cell
            - maximum number of cells expressed required for a gene to pass filering.
        gene_list
            - the list of genes to be filtered.
        inplace
            - whether to inplace the previous data or return a new data.

        Returns
        --------------------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those filtered.
        """
        from ..preprocess.filter import filter_genes
        data = filter_genes(self.data, min_cell, max_cell, gene_list, inplace)
        return data

    @logit
    def filter_coordinates(self, 
                           min_x: int=None, 
                           max_x: int=None, 
                           min_y: int=None, 
                           max_y: int=None, 
                           inplace: bool=True):
        """
        Filter cells based on coordinate information.

        Parameters
        -----------------
        min_x
            - minimum of coordinate x for a cell to pass filtering.
        max_x
            - maximum of coordinate x for a cell to pass filtering.
        min_y
            - minimum of coordinate y for a cell to pass filtering.
        max_y
            - maximum of coordinate y for a cell to pass filtering.
        inplace
            - whether to inplace the previous data or return a new data.

        Returns
        --------------------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those filtered.
        """
        from ..preprocess.filter import filter_coordinates
        data = filter_coordinates(self.data, min_x, max_x, min_y, max_y, inplace)
        return data

    @logit
    def log1p(self, 
              inplace: bool=True, 
              res_key: str='log1p'):
        """
        Transform the express matrix logarithmically.

        Parameters
        -----------------
        inplace
            - whether to inplcae previous data or get a new express matrix after normalization of log1p.
        res_key
            - the key to get targeted result from `self.result`.

        Returns
        ----------------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those normalized.
        """
        if inplace:
            self.data.exp_matrix = np.log1p(self.data.exp_matrix)
        else:
            self.result[res_key] = np.log1p(self.data.exp_matrix)

    @logit
    def normalize_total(self, 
                        target_sum: int=10000, 
                        inplace: bool=True, 
                        res_key: str='normalize_total'):
        """
        Normalize total counts over all genes per cell such that each cell has the same
        total count after normalization.

        Parameters
        -----------------------
        target_sum
            - the number of total counts per cell after normalization, if `None`, each cell has a 
            total count equal to the median of total counts for all cells before normalization.
        inplace
            - whether to inplcae previous data or get a new express matrix after normalize_total.
        res_key
            - the key to get targeted result from `self.result`.

        Returns
        ----------------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those normalized
        """
        from ..algorithm.normalization import normalize_total
        if inplace:
            self.data.exp_matrix = normalize_total(self.data.exp_matrix, target_sum=target_sum)
        else:
            self.result[res_key] = normalize_total(self.data.exp_matrix, target_sum=target_sum)

    @logit
    def scale(self, 
              zero_center: bool=True, 
              max_value: float=None, 
              inplace: bool=True, 
              res_key: str='scale'):
        """
        Scale express matrix to unit variance and zero mean.

        Parameters
        --------------------
        zero_center
            - if `False`, ignore zero variables, which allows to deal with sparse input efficently.
        max_value
            - truncate to this value after scaling, if `None`, do not truncate.
        inplace
            - whether to inplcae the previous data or get a new express matrix after scaling.
        res_key
            - the key to get targeted result from `self.result`.

        Returns
        -----------------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those scaled.
        """
        from ..algorithm.scale import scale
        if inplace:
            self.data.exp_matrix = scale(self.data.exp_matrix, zero_center, max_value)
        else:
            self.result[res_key] = scale(self.data.exp_matrix, zero_center, max_value)

    @logit
    def quantile(self, inplace=True, res_key='quantile'):
        """
        Normalize the columns of X to each have the same distribution. Given an expression matrix  of M genes by N
        samples, quantile normalization ensures all samples have the same spread of data (by construction).

        :param inplace: whether inplace the original data or get a new express matrix after quantile.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        from ..algorithm.normalization import quantile_norm
        if issparse(self.data.exp_matrix):
            self.data.exp_matrix = self.data.exp_matrix.toarray()
        if inplace:
            self.data.exp_matrix = quantile_norm(self.data.exp_matrix)
        else:
            self.result[res_key] = quantile_norm(self.data.exp_matrix)

    @logit
    def disksmooth_zscore(self, r=20, inplace=True, res_key='disksmooth_zscore'):
        """
        for each position, given a radius, calculate the z-score within this circle as final normalized value.

        :param r: radius for normalization.
        :param inplace: whether inplace the original data or get a new express matrix after disksmooth_zscore.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        from ..algorithm.normalization import zscore_disksmooth
        if issparse(self.data.exp_matrix):
            self.data.exp_matrix = self.data.exp_matrix.toarray()
        if inplace:
            self.data.exp_matrix = zscore_disksmooth(self.data.exp_matrix, self.data.position, r)
        else:
            self.result[res_key] = zscore_disksmooth(self.data.exp_matrix, self.data.position, r)

    @logit
    def sctransform(
            self,
            n_cells: int=5000,
            n_genes: int=2000,
            filter_hvgs: bool=True,
            var_features_n: int=3000,
            inplace: bool=True,
            res_key: str='sctransform',
            exp_matrix_key: str="scale.data",
            seed_use: int=1448145,
            **kwargs
    ):
        """
        Normalization of scTransform, refering to Seurat[Hafemeister19] (**link**).

        Parameters
        ----------------------
        n_cells
            - number of cells to use for estimating parameters.
        n_genes
            - number of genes to use for estimating parameters. means all genes.
        filter_hvgs
            - whether to filter highly variable genes.
        var_features_n
            - the number of variable features to select, for calculating a subset of pearson residuals.
        inplace
            - whether to replace the previous expression data.
        res_key
            - the key to get targeted result from `self.result`.
        exp_matrix_key
            - which expression matrix to use for analysis.
        seed_use
            - random seed.
        res_clip_range[str,list]
            - 1) `'seurat'`: clips residuals to -sqrt(ncells/30), sqrt(ncells/30), 2) `'default'`: 
            clips residuals to -sqrt(ncells), sqrt(ncells), only used when `filter_hvgs` is `True`.
        method 
            – offset, theta_ml, theta_lbfgs, alpha_lbfgs.

        Returns
        -----------
        An object of StereoExpData.
        Depending on `inplace`, if `True`, the data will be replaced by those normalized.
        """
        from ..preprocess.sc_transform import sc_transform
        if inplace:
            self.result[res_key] = sc_transform(self.data, n_cells, n_genes, filter_hvgs, exp_matrix_key=exp_matrix_key,
                                                seed_use=seed_use, **kwargs)
        else:
            import copy
            data = copy.deepcopy(self.data)
            self.result[res_key] = sc_transform(data, n_cells, n_genes, filter_hvgs, var_features_n,
                                                exp_matrix_key=exp_matrix_key, seed_use=seed_use, **kwargs)
        key = 'sct'
        self.reset_key_record(key, res_key)

    @logit
    def highly_variable_genes(
            self,
            groups: Optional[str] = None,
            method: Optional[str] = 'seurat',
            n_top_genes: Optional[int] = 2000,
            min_disp: Optional[float] = 0.5,
            max_disp: Optional[float] = np.inf,
            min_mean: Optional[float] = 0.0125,
            max_mean: Optional[float] = 3,
            span: Optional[float] = 0.3,
            n_bins: int = 20,
            res_key='highly_variable_genes'
    ):
        """
        Annotate highly variable genes, refering to Scanpy. 
        Which method to implement depends on `flavor`,including Seurat[Satija15] (**link**), 
        Cell Ranger[Zheng17] (**link**) and Seurat v3[Stuart19] (**link**).

        Parameters
        ----------------------
        groups
            - if specified, highly variable genes are selected within each batch separately and merged, 
            which simply avoids the selection of batch-specific genes and acts as a lightweight batch 
            correction method. For all flavors, genes are first sorted by how many batches they are a HVG.
            For dispersion-based flavors ties are broken by normalized dispersion. If `flavor` 
            is `'seurat_v3'`, ties are broken by the median (across batches) rank based on within-
            batch normalized variance.
        method: `Literal`[`'seurat'`,`'cell_ranger'`,`'seurat_v3'`]
            - choose the flavor to identify highly variable genes. For the dispersion-based methods in 
            their default workflows, Seurat passes the cutoffs whereas Cell Ranger passes `n_top_genes`.
        n_top_genes
            - number of highly variable genes to keep. Mandatory if `flavor='seurat_v3'`.
        min_disp
            - if `n_top_genes` is not None, this and all other cutoffs for the means and the normalized 
            dispersions are ignored. Ignored if `flavor='seurat_v3'`.
        max_disp
            - if `n_top_genes` is not None, this and all other cutoffs for the means and the normalized 
            dispersions are ignored. Ignored if `flavor='seurat_v3'`.
        min_mean
            - if `n_top_genes` is not None, this and all other cutoffs for the means and the normalized 
            dispersions are ignored. Ignored if `flavor='seurat_v3'`.
        max_mean
            - if `n_top_genes` is not None, this and all other cutoffs for the means and the normalized 
            dispersions are ignored. Ignored if `flavor='seurat_v3'`.
        span
            - the fraction of data (cells) used when estimating the variance in the Loess model fit 
            if `flavor='seurat_v3'`.
        n_bins
            - number of bins for binning the mean gene expression. Normalization is done with respect to 
            each bin. If just a single gene falls into a bin, the normalized dispersion is artificially set to 1.
        res_key
            - the key for getting the result from the self.result.

        Returns
        -----------------
        An object of StereoExpData with the result of highly variable genes.
        
        """
        from ..tools.highly_variable_genes import HighlyVariableGenes
        hvg = HighlyVariableGenes(self.data, groups=groups, method=method, n_top_genes=n_top_genes, min_disp=min_disp,
                                  max_disp=max_disp, min_mean=min_mean, max_mean=max_mean, span=span, n_bins=n_bins)
        hvg.fit()
        self.result[res_key] = hvg.result
        key = 'hvg'
        self.reset_key_record(key, res_key)

    def subset_by_hvg(self, hvg_res_key, use_raw=False, inplace=True):
        """
        get the subset by the result of highly variable genes.

        :param hvg_res_key: the key of highly varialbe genes to getting the result.
        :param inplace: whether inplace the data or get a new data after highly variable genes, which only save the
                        data info of highly variable genes.
        :return: a StereoExpData object.
        """
        if not use_raw:
            data = self.data if inplace else copy.deepcopy(self.data)
        else:
            data = self.raw if inplace else copy.deepcopy(self.raw)
        if hvg_res_key not in self.result:
            raise Exception(f'{hvg_res_key} is not in the result, please check and run the normalization func.')
        df = self.result[hvg_res_key]
        genes_index = df['highly_variable'].values
        data.sub_by_index(gene_index=genes_index)
        return data

    @logit
    def pca(self, use_highly_genes, n_pcs, svd_solver='auto', hvg_res_key='highly_variable_genes', res_key='pca'):
        """
        Principal component analysis.

        :param use_highly_genes: Whether to use only the expression of hypervariable genes as input.
        :param n_pcs: the number of features for a return array after reducing.
        :param svd_solver: {'auto', 'full', 'arpack', 'randomized'}, default to 'auto'
                    If auto :
                        The solver is selected by a default policy based on `X.shape` and
                        `n_pcs`: if the input data is larger than 500x500 and the
                        number of components to extract is lower than 80% of the smallest
                        dimension of the data, then the more efficient 'randomized'
                        method is enabled. Otherwise the exact full SVD is computed and
                        optionally truncated afterwards.
                    If full :
                        run exact full SVD calling the standard LAPACK solver via
                        `scipy.linalg.svd` and select the components by postprocessing
                    If arpack :
                        run SVD truncated to n_pcs calling ARPACK solver via
                        `scipy.sparse.linalg.svds`. It requires strictly
                        0 < n_pcs < min(x.shape)
                    If randomized :
                        run randomized SVD by the method of Halko et al.
        :param hvg_res_key: the key of highly varialbe genes to getting the result.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        if use_highly_genes and hvg_res_key not in self.result:
            raise Exception(f'{hvg_res_key} is not in the result, please check and run the highly_var_genes func.')
        data = self.subset_by_hvg(hvg_res_key, inplace=False) if use_highly_genes else self.data
        from ..algorithm.dim_reduce import pca
        res = pca(data.exp_matrix, n_pcs, svd_solver=svd_solver)
        self.result[res_key] = pd.DataFrame(res['x_pca'])
        key = 'pca'
        self.reset_key_record(key, res_key)

    # def umap(self, pca_res_key, n_pcs=None, n_neighbors=5, min_dist=0.3, res_key='dim_reduce'):
    #     if pca_res_key not in self.result:
    #         raise Exception(f'{pca_res_key} is not in the result, please check and run the pca func.')
    #     x = self.result[pca_res_key][:, n_pcs] if n_pcs is not None else self.result[pca_res_key]
    #     res = u_map(x, 2, n_neighbors, min_dist)
    #     self.result[res_key] = pd.DataFrame(res)

    @logit
    def umap(
            self,
            pca_res_key,
            neighbors_res_key,
            res_key='umap',
            min_dist: float = 0.5,
            spread: float = 1.0,
            n_components: int = 2,
            maxiter: Optional[int] = None,
            alpha: float = 1.0,
            gamma: float = 1.0,
            negative_sample_rate: int = 5,
            init_pos: str = 'spectral',
            method: str = 'umap'
    ):
        """
        Embed the neighborhood graph using UMAP [McInnes18]_.

        :param pca_res_key: the key of pca to getting the result. Usually, in spatial omics analysis, the results
                            after using pca are used for umap.
        :param neighbors_res_key: the key of neighbors to getting the connectivities of neighbors result for umap.
        :param res_key: the key for getting the result from the self.result.
        :param min_dist: The effective minimum distance between embedded points. Smaller values
                         will result in a more clustered/clumped embedding where nearby points on
                         the manifold are drawn closer together, while larger values will result
                         on a more even dispersal of points. The value should be set relative to
                         the ``spread`` value, which determines the scale at which embedded
                         points will be spread out. The default of in the `umap-learn` package is
                         0.1.
        :param spread: The effective scale of embedded points. In combination with `min_dist`
                       this determines how clustered/clumped the embedded points are.
        :param n_components: The number of dimensions of the embedding.
        :param maxiter: The number of iterations (epochs) of the optimization. Called `n_epochs`
                        in the original UMAP.
        :param alpha: The initial learning rate for the embedding optimization.
        :param gamma: Weighting applied to negative samples in low dimensional embedding
                      optimization. Values higher than one will result in greater weight
                      being given to negative samples.
        :param negative_sample_rate: The number of negative edge/1-simplex samples to use per positive
                      edge/1-simplex sample in optimizing the low dimensional embedding.
        :param init_pos: How to initialize the low dimensional embedding.Called `init` in the original UMAP.Options are:
                        * 'spectral': use a spectral embedding of the graph.
                        * 'random': assign initial embedding positions at random.
        :return:
        """
        from ..algorithm.umap import umap
        if pca_res_key not in self.result:
            raise Exception(f'{pca_res_key} is not in the result, please check and run the pca func.')
        if neighbors_res_key not in self.result:
            raise Exception(f'{neighbors_res_key} is not in the result, please check and run the neighbors func.')
        _, connectivities, _ = self.get_neighbors_res(neighbors_res_key)
        x_umap = umap(x=self.result[pca_res_key], neighbors_connectivities=connectivities,
                      min_dist=min_dist, spread=spread, n_components=n_components, maxiter=maxiter, alpha=alpha,
                      gamma=gamma, negative_sample_rate=negative_sample_rate, init_pos=init_pos, method=method)
        self.result[res_key] = pd.DataFrame(x_umap)
        key = 'umap'
        self.reset_key_record(key, res_key)

    @logit
    def neighbors(self, pca_res_key, method='umap', metric='euclidean', n_pcs=None, n_neighbors=10, knn=True, n_jobs=10,
                  res_key='neighbors'):
        """
        run the neighbors.

        :param pca_res_key: the key of pca to getting the result.
        :param method: Use 'umap' or 'gauss'. for computing connectivities.
        :param metric: A known metric's name or a callable that returns a distance.
                        include:
                            * euclidean
                            * manhattan
                            * chebyshev
                            * minkowski
                            * canberra
                            * braycurtis
                            * mahalanobis
                            * wminkowski
                            * seuclidean
                            * cosine
                            * correlation
                            * haversine
                            * hamming
                            * jaccard
                            * dice
                            * russelrao
                            * kulsinski
                            * rogerstanimoto
                            * sokalmichener
                            * sokalsneath
                            * yule
        :param n_pcs: the number of pcs used to runing neighbor.
        :param n_neighbors: Use this number of nearest neighbors.
        :param knn: If `True`, use a hard threshold to restrict the number of neighbors to
                    `n_neighbors`, that is, consider a knn graph. Otherwise, use a Gaussian
                    Kernel to assign low weights to neighbors more distant than the
                    `n_neighbors` nearest neighbor.
        :param n_jobs: The number of parallel jobs to run for neighbors search, defaults to 10.
                    if set to -1, means the all CPUs will be used, too high value may cause segment fault.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        if pca_res_key not in self.result:
            raise Exception(f'{pca_res_key} is not in the result, please check and run the pca func.')
        if n_jobs > cpu_count():
            n_jobs = -1
        from ..algorithm.neighbors import find_neighbors
        neighbor, dists, connectivities = find_neighbors(x=self.result[pca_res_key].values, method=method, n_pcs=n_pcs,
                                                         n_neighbors=n_neighbors, metric=metric, knn=knn, n_jobs=n_jobs)
        res = {'neighbor': neighbor, 'connectivities': connectivities, 'nn_dist': dists}
        self.result[res_key] = res
        key = 'neighbors'
        self.reset_key_record(key, res_key)

    def get_neighbors_res(self, neighbors_res_key, ):
        """
        get the neighbor result by the key.

        :param neighbors_res_key: the key of neighbors to getting the result.
        :return: neighbor, connectivities, nn_dist.
        """
        if neighbors_res_key not in self.result:
            raise Exception(f'{neighbors_res_key} is not in the result, please check and run the neighbors func.')
        neighbors_res = self.result[neighbors_res_key]
        neighbor = neighbors_res['neighbor']
        connectivities = neighbors_res['connectivities']
        nn_dist = neighbors_res['nn_dist']
        return neighbor, connectivities, nn_dist

    @logit
    def spatial_neighbors(self, neighbors_res_key, n_neighbors=6, res_key='spatial_neighbors'):
        """
        Create a graph from spatial coordinates using squidpy.

        :param neighbors_res_key: the key of neighbors to getting the result.
        :param n_neighbors: Use this number of nearest neighbors.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        from ..io.reader import stereo_to_anndata
        import squidpy as sq
        neighbor, connectivities, dists = copy.deepcopy(self.get_neighbors_res(neighbors_res_key))
        adata = stereo_to_anndata(self.data, split_batches=False)
        sq.gr.spatial_neighbors(adata, n_neighs=n_neighbors)
        connectivities.data[connectivities.data > 0] = 1
        adj = connectivities + adata.obsp['spatial_connectivities']
        adj.data[adj.data > 0] = 1
        res = {'neighbor': neighbor, 'connectivities': adj, 'nn_dist': dists}
        self.result[res_key] = res
        key = 'neighbors'
        self.reset_key_record(key, res_key)

    @logit
    def leiden(self,
               neighbors_res_key,
               res_key='cluster',
               directed: bool = True,
               resolution: float = 1,
               use_weights: bool = True,
               random_state: int = 0,
               n_iterations: int = -1,
               method='normal'
               ):
        """
        leiden of cluster.

        :param neighbors_res_key: the key of neighbors to getting the result.
        :param res_key: the key for getting the result from the self.result.
        :param directed: If True, treat the graph as directed. If False, undirected.
        :param resolution: A parameter value controlling the coarseness of the clustering.
                            Higher values lead to more clusters.
                            Set to `None` if overriding `partition_type`
                            to one that doesn’t accept a `resolution_parameter`.
        :param use_weights: If `True`, edge weights from the graph are used in the computation(placing more emphasis
                            on stronger edges).
        :param random_state: Change the initialization of the optimization.
        :param n_iterations: How many iterations of the Leiden clustering algorithm to perform.
                             Positive values above 2 define the total number of iterations to perform,
                             -1 has the algorithm run until it reaches its optimal clustering.
        :return:
        """
        neighbor, connectivities, _ = self.get_neighbors_res(neighbors_res_key)
        if method == 'rapids':
            from ..algorithm.leiden import leiden_rapids
            clusters = leiden_rapids(adjacency=connectivities, resolution=resolution)
        else:
            from ..algorithm.leiden import leiden as le
            clusters = le(neighbor=neighbor, adjacency=connectivities, directed=directed, resolution=resolution,
                          use_weights=use_weights, random_state=random_state, n_iterations=n_iterations)
        df = pd.DataFrame({'bins': self.data.cell_names, 'group': clusters})
        self.result[res_key] = df
        key = 'cluster'
        self.reset_key_record(key, res_key)
        gene_cluster_res_key = f'gene_exp_{res_key}'
        from ..utils.pipeline_utils import cell_cluster_to_gene_exp_cluster
        gene_exp_cluster_res = cell_cluster_to_gene_exp_cluster(self, res_key)
        if gene_exp_cluster_res is not False:
            self.result[gene_cluster_res_key] = gene_exp_cluster_res
            self.reset_key_record('gene_exp_cluster', gene_cluster_res_key)

    @logit
    def louvain(self,
                neighbors_res_key,
                res_key='cluster',
                resolution: float = None,
                random_state: int = 0,
                flavor: Literal['vtraag', 'igraph', 'rapids'] = 'vtraag',
                directed: bool = True,
                use_weights: bool = False
                ):
        """
        louvain of cluster.

        :param neighbors_res_key: the key of neighbors to getting the result.
        :param res_key: the key for getting the result from the self.result.
        :param resolution: A parameter value controlling the coarseness of the clustering.
                            Higher values lead to more clusters.
                            Set to `None` if overriding `partition_type`
                            to one that doesn't accept a `resolution_parameter`.
        :param random_state: Change the initialization of the optimization.
        :param flavor: Choose between to packages for computing the clustering.
                        Including: ``'vtraag'``, ``'igraph'``, ``'taynaud'``.
                        ``'vtraag'`` is much more powerful, and the default.
        :param directed: If True, treat the graph as directed. If False, undirected.
        :param use_weights: Use weights from knn graph.
        :return:
        """
        neighbor, connectivities, _ = self.get_neighbors_res(neighbors_res_key)
        from ..algorithm._louvain import louvain as lo
        from ..utils.pipeline_utils import cell_cluster_to_gene_exp_cluster
        clusters = lo(neighbor=neighbor, resolution=resolution, random_state=random_state,
                      adjacency=connectivities, flavor=flavor, directed=directed, use_weights=use_weights)
        df = pd.DataFrame({'bins': self.data.cell_names, 'group': clusters})
        self.result[res_key] = df
        key = 'cluster'
        self.reset_key_record(key, res_key)
        gene_cluster_res_key = f'gene_exp_{res_key}'
        gene_exp_cluster_res = cell_cluster_to_gene_exp_cluster(self, res_key)
        if gene_exp_cluster_res is not False:
            self.result[gene_cluster_res_key] = gene_exp_cluster_res
            self.reset_key_record('gene_exp_cluster', gene_cluster_res_key)


    @logit
    def phenograph(self, phenograph_k, pca_res_key, n_jobs=10, res_key='cluster'):
        """
        phenograph of cluster.

        :param phenograph_k: the k value of phenograph.
        :param pca_res_key: the key of pca to getting the result for running the phenograph.
        :param n_jobs: The number of parallel jobs to run for neighbors search, defaults to 10.
                    if set to -1, means the all CPUs will be used, too high value may cause segment fault.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        if pca_res_key not in self.result:
            raise Exception(f'{pca_res_key} is not in the result, please check and run the pca func.')
        import phenograph as phe
        from natsort import natsorted
        from ..utils.pipeline_utils import cell_cluster_to_gene_exp_cluster
        communities, _, _ = phe.cluster(self.result[pca_res_key], k=phenograph_k, clustering_algo='leiden',
                                        n_jobs=n_jobs)
        communities = communities + 1
        clusters = pd.Categorical(
            values=communities.astype('U'),
            categories=natsorted(map(str, np.unique(communities))),
        )
        # clusters = communities.astype(str)
        df = pd.DataFrame({'bins': self.data.cell_names, 'group': clusters})
        self.result[res_key] = df
        key = 'cluster'
        self.reset_key_record(key, res_key)
        gene_cluster_res_key = f'gene_exp_{res_key}'
        gene_exp_cluster_res = cell_cluster_to_gene_exp_cluster(self, res_key)
        if gene_exp_cluster_res is not False:
            self.result[gene_cluster_res_key] = gene_exp_cluster_res
            self.reset_key_record('gene_exp_cluster', gene_cluster_res_key)

    @logit
    def find_marker_genes(self,
                          cluster_res_key,
                          method: str = 't_test',
                          case_groups: Union[str, np.ndarray, list] = 'all',
                          control_groups: Union[str, np.ndarray, list] = 'rest',
                          corr_method: str = 'bonferroni',
                          use_raw: bool = True,
                          use_highly_genes: bool = True,
                          hvg_res_key: Optional[str] = 'highly_variable_genes',
                          res_key: str = 'marker_genes',
                          output: Optional[str] = None,
                          ):
        """
        a tool of finding maker gene. for each group, find statistical test different genes between one group and
        the rest groups using t_test or wilcoxon_test.

        :param cluster_res_key: the key of cluster to getting the result for group info.
        :param method: t_test or wilcoxon_test.
        :param case_groups: case group info, default all clusters.
        :param control_groups: control group info, default the rest of groups.
        :param corr_method: correlation method.
        :param use_raw: whether use the raw count express matrix for the analysis, default True.
        :param use_highly_genes: Whether to use only the expression of hypervariable genes as input, default True.
        :param hvg_res_key: the key of highly varialbe genes to getting the result.
        :param res_key: the key for getting the result from the self.result.
        :param output: path of output_file(.csv). If None, do not generate the output file.
        :return:
        """
        from ..tools.find_markers import FindMarker

        if use_highly_genes and hvg_res_key not in self.result:
            raise Exception(f'{hvg_res_key} is not in the result, please check and run the highly_var_genes func.')
        if use_raw and not self.raw:
            raise Exception(f'self.raw must be set if use_raw is True.')
        if cluster_res_key not in self.result:
            raise Exception(f'{cluster_res_key} is not in the result, please check and run the func of cluster.')
        data = self.raw if use_raw else self.data
        data = self.subset_by_hvg(hvg_res_key, use_raw=use_raw, inplace=False) if use_highly_genes else data
        tool = FindMarker(data=data, groups=self.result[cluster_res_key], method=method, case_groups=case_groups,
                          control_groups=control_groups, corr_method=corr_method, raw_data=self.raw)
        self.result[res_key] = tool.result
        if output is not None:
            import natsort
            result = self.result[res_key]
            show_cols = ['scores', 'pvalues', 'pvalues_adj', 'log2fc', 'genes']
            groups = natsort.natsorted([key for key in result.keys() if '.vs.' in key])
            dat = pd.DataFrame(
                {group.split(".")[0] + "_" + key: result[group][key] for group in groups for key in show_cols})
            dat.to_csv(output)
        key = 'marker_genes'
        self.reset_key_record(key, res_key)

    @logit
    def spatial_lag(self,
                    cluster_res_key,
                    genes=None,
                    random_drop=True,
                    drop_dummy=None,
                    n_neighbors=8,
                    res_key='spatial_lag'):
        """
        spatial lag model, calculate cell-bin's lag coefficient, lag z-stat and p-value.

        :param cluster_res_key: the key of cluster to getting the result for group info.
        :param genes: specify genes, default using all genes.
        :param random_drop: randomly drop bin-cells if True.
        :param drop_dummy: drop specify clusters.
        :param n_neighbors: number of neighbors.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        from ..tools.spatial_lag import SpatialLag
        if cluster_res_key not in self.result:
            raise Exception(f'{cluster_res_key} is not in the result, please check and run the func of cluster.')
        tool = SpatialLag(data=self.data, groups=self.result[cluster_res_key], genes=genes, random_drop=random_drop,
                          drop_dummy=drop_dummy, n_neighbors=n_neighbors)
        tool.fit()
        self.result[res_key] = tool.result

    @logit
    def spatial_pattern_score(self, use_raw=True, res_key='spatial_pattern'):
        """
        calculate the spatial pattern score.

        :param use_raw: whether use the raw count express matrix for the analysis, default True.
        :param res_key: the key for getting the result from the self.result.
        :return:
        """
        from ..algorithm.spatial_pattern_score import spatial_pattern_score

        if use_raw and not self.raw:
            raise Exception(f'self.raw must be set if use_raw is True.')
        data = self.raw if use_raw else self.data
        x = data.exp_matrix.toarray() if issparse(data.exp_matrix) else data.exp_matrix
        df = pd.DataFrame(x, columns=data.gene_names, index=data.cell_names)
        res = spatial_pattern_score(df)
        self.result[res_key] = res

    @logit
    def spatial_hotspot(self, use_highly_genes=True, hvg_res_key: Optional[str] = None, model='normal', n_neighbors=30,
                        n_jobs=20, fdr_threshold=0.05, min_gene_threshold=10, outdir=None, res_key='spatial_hotspot',
                        use_raw=True, ):
        """
        identifying informative genes (and gene modules)

        :param use_highly_genes: Whether to use only the expression of hypervariable genes as input, default True.
        :param hvg_res_key: the key of highly varialbe genes to getting the result.
        :param model: Specifies the null model to use for gene expression.
            Valid choices are:
                - 'danb': Depth-Adjusted Negative Binomial
                - 'bernoulli': Models probability of detection
                - 'normal': Depth-Adjusted Normal
                - 'none': Assumes data has been pre-standardized
        :param n_neighbors: Neighborhood size.
        :param n_jobs: Number of parallel jobs to run.
        :param fdr_threshold: Correlation threshold at which to stop assigning genes to modules
        :param min_gene_threshold: Controls how small modules can be.
            Increase if there are too many modules being formed.
            Decrease if substructre is not being captured
        :param outdir: directory containing output file(hotspot.pkl). Hotspot object will be totally output here.
            If None, results will not be output to a file.
        :param res_key: the key for getting the result from the self.result.
        :param use_raw: whether use the raw count express matrix for the analysis, default True.

        :return:
        """
        from ..algorithm.spatial_hotspot import spatial_hotspot
        if use_highly_genes and hvg_res_key not in self.result:
            raise Exception(f'{hvg_res_key} is not in the result, please check and run the highly_var_genes func.')
        # data = self.subset_by_hvg(hvg_res_key, inplace=False) if use_highly_genes else self.data
        if use_raw and not self.raw:
            raise Exception(f'self.raw must be set if use_raw is True.')
        data = copy.deepcopy(self.raw) if use_raw else copy.deepcopy(self.data)
        if use_highly_genes:
            df = self.result[hvg_res_key]
            genes_index = df['highly_variable'].values
            gene_name = np.array(df.index)[genes_index]
            data = data.sub_by_name(gene_name=gene_name)
        hs = spatial_hotspot(data, model=model, n_neighbors=n_neighbors, n_jobs=n_jobs, fdr_threshold=fdr_threshold,
                             min_gene_threshold=min_gene_threshold, outdir=outdir)
        # res = {"results":hs.results, "local_cor_z": hs.local_correlation_z, "modules": hs.modules,
        #        "module_scores": hs.module_scores}
        self.result[res_key] = hs

    @logit
    def gaussian_smooth(self, n_neighbors=10, smooth_threshold=90, pca_res_key='pca', res_key='gaussian_smooth',
                        n_jobs=-1, inplace=True):
        """smooth the expression matrix

        :param n_neighbors: number of the nearest points to serach, Too high value may cause overfitting, Too low value may cause poor smoothing effect.
        :param smooth_threshold: indicates Gaussian variance with a value between 20 and 100, Too high value may cause overfitting, Too low value may cause poor smoothing effect。
        :param pca_res_key: the key of pca to get from self.result, defaults to 'pca'.
        :param res_key: the key for getting the result from the self.result, defaults to 'gaussian_smooth'.
        :param n_jobs: The number of parallel jobs to run for neighbors search, defaults to -1, means the all CPUs will be used.
        :param inplace: whether inplace the express matrix or get a new express matrix, defaults to True.
        """
        assert pca_res_key in self.result, f'{pca_res_key} is not in the result, please check and run the pca func.'
        assert self.raw is not None, 'no raw exp_matrix to be saved, please check and run the raw_checkpoint.'
        assert n_neighbors > 0, 'n_neighbors must be greater than 0'
        assert smooth_threshold >= 20 and smooth_threshold <= 100, 'smooth_threshold must be between 20 and 100'

        pca_exp_matrix = self.result[pca_res_key].values
        raw_exp_matrix = self.raw.exp_matrix.toarray() if issparse(self.raw.exp_matrix) else self.raw.exp_matrix

        if pca_exp_matrix.shape[0] != raw_exp_matrix.shape[0]:
            raise Exception(
                f"The first dimension of pca_exp_matrix not equals to raw_exp_matrix's, may be because of running raw_checkpoint before filter cells and/or genes.")

        # logger.info(f"raw exp matrix size: {raw_exp_matrix.shape}")
        from ..algorithm.gaussian_smooth import gaussian_smooth
        result = gaussian_smooth(pca_exp_matrix, raw_exp_matrix, self.data.position, n_neighbors=n_neighbors,
                                 smooth_threshold=smooth_threshold, n_jobs=n_jobs)
        # logger.info(f"smoothed exp matrix size: {result.shape}")
        if inplace:
            self.data.exp_matrix = result
            from ..preprocess.qc import cal_qc
            cal_qc(self.data)
        else:
            self.result[res_key] = result

    def lr_score(
            self,
            lr_pairs: Union[list, np.array],
            distance: Union[int, float] = 5,
            spot_comp: pd.DataFrame = None,
            verbose: bool = True,
            key_add: str = 'cci_score',
            min_exp: Union[int, float] = 0,
            use_raw: bool = False,
            min_spots: int = 20,
            n_pairs: int = 1000,
            adj_method: str = "fdr_bh",
            bin_scale: int = 1,
            n_jobs=4,
            res_key='lr_score'
    ):
        """calculate cci score for each LR pair and do permutation test

        Parameters
        ----------
        lr_pairs : Union[list, np.array]
            LR pairs
        distance : Union[int, float], optional
            the distance between spots which are considered as neighbors , by default 5
        spot_comp : `pd.DataFrame`, optional
            spot component of different cells, by default None
        key_add : str, optional
            key added in `result`, by default 'cci_score'
        min_exp : Union[int, float], optional
            the min expression of ligand or receptor gene when caculate reaction strength, by default 0
        use_raw : bool, optional
            whether to use counts in `adata.raw.X`, by default False
        min_spots : int, optional
            the min number of spots that score > 0, by default 20
        n_pairs : int, optional
            number of pairs to random sample, by default 1000
        adj_method : str, optional
            adjust method of p value, by default "fdr_bh"
        n_wokers : int, optional
            num of worker when calculate_score, by default 4

        Raises
        ------
        ValueError
            _description_
        """
        from ..tools.LR_interaction import LrInteraction
        interaction = LrInteraction(self,
                                    verbose=verbose,
                                    bin_scale=bin_scale,
                                    distance=distance,
                                    spot_comp=spot_comp,
                                    n_jobs=n_jobs,
                                    min_exp=min_exp,
                                    min_spots=min_spots,
                                    n_pairs=n_pairs,
                                    )

        result = interaction.fit(lr_pairs=lr_pairs,
                                 adj_method=adj_method,
                                 use_raw=use_raw,
                                 key_add=key_add)

        self.result[res_key] = result

    @logit
    def batches_integrate(self, pca_res_key='pca', res_key='pca_integrated', **kwargs):
        """integrate different experiments base on the pca result

        :param pca_res_key: the key of original pca to get from self.result, defaults to 'pca'
        :param res_key: the key for getting the result after integrating from the self.result, defaults to 'pca_integrated'
        """
        import harmonypy as hm
        assert pca_res_key in self.result, f'{pca_res_key} is not in the result, please check and run the pca method.'
        assert self.data.cells.batch is not None, f'this is not a data were merged from diffrent experiments'

        out = hm.run_harmony(self.result[pca_res_key], self.data.cells.to_df(), 'batch', **kwargs)
        self.result[res_key] = pd.DataFrame(out.Z_corr.T)
        key = 'pca'
        self.reset_key_record(key, res_key)

    @logit
    def annotation(
        self,
        annotation_information: Union[list, dict],
        cluster_res_key = 'cluster',
        res_key='annotation'
    ):
        """
        annotation of cluster.

        :param annotation_information: Union[list, dict]
            Annotation information for clustering results.
        :param cluster_res_key: The key of cluster result in the self.result.
        :param res_key: The key for getting the result from the self.result.
        :return:
        """

        assert cluster_res_key in self.result, f'{cluster_res_key} is not in the result, please check and run the cluster func.'

        df = copy.deepcopy(self.result[cluster_res_key])
        if isinstance(annotation_information,list):
            df.group.cat.categories = annotation_information
        elif isinstance(annotation_information,dict):
            new_annotation_list = []
            for i in df.group.cat.categories:
                new_annotation_list.append(annotation_information[i])
            df.group.cat.categories = new_annotation_list

        self.result[res_key] = df

        key = 'cluster'
        self.reset_key_record(key, res_key)
    
    @logit
    def filter_marker_genes(
        self,
        marker_genes_res_key='marker_genes',
        min_fold_change=1,
        min_in_group_fraction=0.25,
        max_out_group_fraction=0.5,
        compare_abs=False,
        remove_mismatch=True,
        res_key='marker_genes_filtered'
    ):
        """Filters out genes based on log fold change and fraction of genes expressing the gene within and outside each group.

        :param marker_genes_res_key: The key of the result of find_marker_genes to get from self.result, defaults to 'marker_genes'
        :param min_fold_change: Minimum threshold of log fold change, defaults to None
        :param min_in_group_fraction:  Minimum fraction of cells expressing the genes for each group, defaults to None
        :param max_out_group_fraction: Maximum fraction of cells from the union of the rest of each group expressing the genes, defaults to None
        :param compare_abs: If `True`, compare absolute values of log fold change with `min_fold_change`, defaults to False
        :param remove_mismatch: If `True`, remove the records which are mismatch conditions from the find_marker_genes result, 
                                if `False`, these records will be set to np.nan,
                                defaults to True
        :param res_key: the key of the result of this function to be set to self.result, defaults to 'marker_genes_filtered'
        """
        if marker_genes_res_key not in self.result:
            raise Exception(f'{marker_genes_res_key} is not in the result, please check and run the find_marker_genes func.') 

        self.result[res_key] = {}
        self.result[res_key]['marker_genes_res_key'] = marker_genes_res_key
        pct= self.result[marker_genes_res_key]['pct']
        pct_rest = self.result[marker_genes_res_key]['pct_rest']
        for key, res in self.result[marker_genes_res_key].items():
            if '.vs.' not in key:
                continue
            new_res = res.copy()
            group_name = key.split('.')[0]
            if not compare_abs:
                gene_set_1 = res[res['log2fc'] < min_fold_change]['genes'].values if min_fold_change is not None else []
            else:
                gene_set_1 = res[res['log2fc'].abs() < min_fold_change]['genes'].values if min_fold_change is not None else []
            gene_set_2 = pct[pct[group_name] < min_in_group_fraction]['genes'].values if min_in_group_fraction is not None else []
            gene_set_3 = pct_rest[pct_rest[group_name] > max_out_group_fraction]['genes'].values if max_out_group_fraction is not None else []
            flag = res['genes'].isin(np.union1d(gene_set_1, np.union1d(gene_set_2, gene_set_3)))
            if remove_mismatch:
                new_res = new_res[flag == False]
            else:
                new_res[flag == True] = np.nan
            self.result[res_key][key] = new_res
    

    # def scenic(self, tfs, motif, database_dir, res_key='scenic', use_raw=True, outdir=None,):
    #     """
    #
    #     :param tfs: tfs file in txt format
    #     :param motif: motif file in tbl format
    #     :param database_dir: directory containing reference database(*.feather files) from cisTarget.
    #     :param res_key: the key for getting the result from the self.result.
    #     :param use_raw: whether use the raw count express matrix for the analysis, default True.
    #     :param outdir: directory containing output files(including modules.pkl, regulons.csv, adjacencies.tsv,
    #         motifs.csv). If None, results will not be output to files.
    #
    #     :return:
    #     """
    #     from ..algorithm.scenic import scenic as cal_sce
    #     if use_raw and not self.raw:
    #         raise Exception(f'self.raw must be set if use_raw is True.')
    #     data = self.raw if use_raw else self.data
    #     modules, regulons, adjacencies, motifs, auc_mtx, regulons_df = cal_sce(data, tfs, motif, database_dir, outdir)
    #     res = {"modules": modules, "regulons": regulons, "adjacencies": adjacencies, "motifs": motifs,
    #            "auc_mtx":auc_mtx, "regulons_df": regulons_df}
    #     self.result[res_key] = res


class AnnBasedResult(dict):
    CLUSTER_NAMES = {'leiden', 'louvain', 'phenograph'}
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

    def __init__(self, based_ann_data: AnnData):
        super(dict, self).__init__()
        self.__based_ann_data = based_ann_data

    def __contains__(self, item):
        if item in self.keys():
            return True
        elif item in AnnBasedResult.CLUSTER_NAMES:
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
            return pd.DataFrame(self.__based_ann_data.obs[name].values, columns=['group'], index=self.__based_ann_data.obs_names)
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
            return pd.DataFrame(self.__based_ann_data.obs[name].values, columns=['group'], index=self.__based_ann_data.obs_names)
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


class AnnBasedStPipeline(StPipeline):

    def __init__(self, based_ann_data: AnnData, data):
        super(AnnBasedStPipeline, self).__init__(data)
        self.__based_ann_data = based_ann_data
        self.result = AnnBasedResult(based_ann_data)

    def subset_by_hvg(self, hvg_res_key, use_raw=False, inplace=True):
        data = self.data if inplace else copy.deepcopy(self.data)
        if hvg_res_key not in self.result:
            raise Exception(f'{hvg_res_key} is not in the result, please check and run the normalization func.')
        df = self.result[hvg_res_key]
        data._ann_data._inplace_subset_var(df['highly_variable'].values)
        return data

    def raw_checkpoint(self):
        from .stereo_exp_data import AnnBasedStereoExpData
        if self.__based_ann_data.raw:
            data = AnnBasedStereoExpData("", based_ann_data=self.__based_ann_data.raw.to_adata())
        else:
            data = AnnBasedStereoExpData("", based_ann_data=copy.deepcopy(self.__based_ann_data))
        self.raw = data
