# python core module
from typing import Union
from collections import defaultdict
import time
from natsort import natsorted
from copy import deepcopy

# third part module
import numba as nb
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import sparse
import networkx as nx
from sklearn.metrics import pairwise_distances
from tqdm import tqdm

# module in self project
import stereo as st # only used in test function to read data
from stereo.core.stereo_exp_data import StereoExpData, AnnBasedStereoExpData
from stereo.log_manager import logger
from stereo.algorithm.algorithm_base  import AlgorithmBase, ErrorCode


##----------------------------------------------##
## please try the notebook demo in pull requese ##
##----------------------------------------------##

@nb.njit(cache=True, nogil=True)
def _cal_distance(point: np.ndarray, points: np.ndarray):
    return np.sqrt(np.sum((points - point)**2, axis=1))

@nb.njit(cache=True, nogil=True, parallel=True)
def _cal_pairwise_distances(points_a: np.ndarray, points_b: np.ndarray):
    points_count_a = points_a.shape[0]
    points_count_b = points_b.shape[0]
    distance = np.zeros((points_count_a, points_count_b), dtype=np.float64)
    for i in nb.prange(points_count_a):
        distance[i] = _cal_distance(points_a[i], points_b)
    return distance


# @nb.njit(cache=True, nogil=True)
def _coo_stereopy_calculator(position, groups, group_codes_count, thresh_l, thresh_r, group_codes_id_map):
    count = np.zeros(group_codes_count, dtype=np.uint64)
    ret = np.zeros((group_codes_count, group_codes_count), dtype=np.uint64)
    for i, g1 in enumerate(groups):
        dist = _cal_distance(position[i], position)
        groups_selected = np.unique(groups[(dist >= thresh_l) & (dist <= thresh_r)])
        g1_id = group_codes_id_map[g1]
        for g2 in groups_selected:
            g2_id = group_codes_id_map[g2]
            ret[g1_id][g2_id] += 1
        count[g1_id] += 1
    return ret, count
    # return ret.T / count

@nb.njit(cache=True, nogil=True, parallel=True)
def _coo_squidpy_calculator(
    data_position: np.ndarray,
    group_codes: np.ndarray,
    groups_idx: np.ndarray,
    thresh: np.ndarray,
):
    num = group_codes.size
    out = np.zeros((num, num, thresh.shape[0] - 1))
    for ep in nb.prange(thresh.shape[0] - 1):
        co_occur = np.zeros((num, num))
        thresh_l, thresh_r = thresh[ep], thresh[ep+1]
        for x in range(data_position.shape[0]):
            dist = _cal_distance(data_position[x], data_position)
            i = groups_idx[x]
            y = groups_idx[(dist > thresh_l) & (dist <= thresh_r)]
            for j in y:
                co_occur[i, j] += 1

        probs_matrix = co_occur / np.sum(co_occur)
        probs = np.sum(probs_matrix, axis=1)

        probs_con = (co_occur.T / np.sum(co_occur, axis=1) / probs).T

        out[:, :, ep] = probs_con
    return out

class CoOccurrence(AlgorithmBase):
    """
    docstring for CoOccurence
    :param 
    :return: 
    """

    def main(
        self,
        cluster_res_key,
        method='stereopy',
        dist_thres=300,
        steps=10,
        genelist=None,
        gene_thresh=0,
        res_key='co_occurrence'
    ):
        """
        Co-occurence calculate the score or probability of a particular celltype or cluster of cells is co-occurence with another in spatial.  
        We provided two method for co-occurence, 'squidpy' for method in squidpy, 'stereopy' for method in stereopy


        :param data: An instance of StereoExpData, data.position & data.tl.result[use_col] will be used.
        :param cluster_res_key: The key of the cluster or annotation result of cells stored in data.tl.result which ought to be equal to cells in length.
        :param method: The metrics to calculate co-occurence choose from ['stereopy', 'squidpy'], 'squidpy' by default.
        :param dist_thres: The max distance to measure co-occurence. Only used when method=='stereopy'
        :param steps: The steps to generate threshold to measure co-occurence, use along with dist_thres, i.e. default params 
                        will generate [30,60,90......,270,300] as threshold. Only used when method=='stereopy'
        :param genelist: Calculate co-occurence between use_col & genelist if provided, otherwise calculate between clusters 
                        in use_col. Only used when method=='stereopy'
        :param gene_thresh: Threshold to determine whether a cell express the gene. Only used when method=='stereopy'


        :return: the input data with co_occurrence result in data.tl.result['co-occur']
        """
        if method == 'stereopy':
            res = self.co_occurrence(self.stereo_exp_data, cluster_res_key, dist_thres = dist_thres, steps = steps, genelist = genelist, gene_thresh = gene_thresh)
            # return self.co_occurrence(self.stereo_exp_data, cluster_res_key, dist_thres = dist_thres, steps = steps, genelist = genelist, gene_thresh = gene_thresh)
        elif method == 'squidpy':
            res = self.co_occurrence_squidpy(self.stereo_exp_data, cluster_res_key)
        else:
            raise ValueError("unavailable value for method, it only can be choosed from ['stereopy', 'squidpy'].")
        self.pipeline_res[res_key] = res
        return self.stereo_exp_data


    def co_occurrence_squidpy(
        self,
        data: Union[StereoExpData, AnnBasedStereoExpData],
        use_col: str
    ):
        """
        Squidpy mode to calculate co-occurence, result same as squidpy
        :param data: An instance of StereoExpData, data.position & data.tl.result[use_col] will be used.
        :param use_col: The key of the cluster or annotation result of cells stored in data.tl.result which ought to be equal 
                        to cells in length.
        :return: co_occurrence result, also written in data.tl.result['co-occur']
        """

        thresh_min, thresh_max = self._find_min_max(data.position)
        thresh = np.linspace(thresh_min, thresh_max, num=50)
        if use_col in data.cells:
            groups:pd.Series = data.cells[use_col].astype('category')
        else:
            groups:pd.Series = self.pipeline_res[use_col]['group'].astype('category')
        group_codes = groups.cat.categories.to_numpy().astype('U')
        out = _coo_squidpy_calculator(
            data.position,
            group_codes,
            groups.cat.codes.to_numpy(),
            thresh,
        )
        ret = {}
        for i, j in enumerate(group_codes):
            tmp = pd.DataFrame(out[i]).T
            tmp.columns = group_codes
            tmp.index = thresh[1:]
            ret[j] = tmp
        return ret

    def _find_min_max(self, spatial):
        '''
        Helper to calculate distance threshold in squidpy mode
        param: spatial: the cell position of data
        return: thres_min, thres_max for minimum & maximum of threshold
        '''
        coord_sum = np.sum(spatial, axis=1)
        min_idx, min_idx2 = np.argpartition(coord_sum, 2)[:2]
        max_idx = np.argmax(coord_sum)
        # fmt: off
        thres_max = _cal_pairwise_distances(spatial[min_idx, :].reshape(1, -1), spatial[max_idx, :].reshape(1, -1))[0, 0] / 2.0
        thres_min = _cal_pairwise_distances(spatial[min_idx, :].reshape(1, -1), spatial[min_idx2, :].reshape(1, -1))[0, 0]
        # fmt: on
        return thres_min, thres_max

    def co_occurrence(
        self,
        data: Union[StereoExpData, AnnBasedStereoExpData],
        use_col,
        dist_thres = 300,
        steps = 10,
        genelist = None,
        gene_thresh = 0
    ):
        '''
        Stereopy mode to calculate co-occurence, the score of result['A']['B'] represent the probablity of 'B' occurence around 
          'A' in distance of threshold
        :param data: An instance of StereoExpData, data.position & data.tl.result[use_col] will be used.
        :param use_col: The key of the cluster or annotation result of cells stored in data.tl.result which ought to be equal 
                        to cells in length.
        :param method: The metrics to calculate co-occurence choose from ['stereopy', 'squidpy'], 'squidpy' by default.
        :param dist_thres: The max distance to measure co-occurence. 
        :param steps: The steps to generate threshold to measure co-occurence, use along with dist_thres, i.e. default params 
                      will generate [30,60,90......,270,300] as threshold. 
        :param genelist: Calculate co-occurence between use_col & genelist if provided, otherwise calculate between clusters 
                         in use_col. 
        :param gene_thresh: Threshold to determine whether a cell express the gene. 
        :return: co_occurrence result, also written in data.tl.result['co-occur']
        '''
        #from collections import defaultdict
        #from scipy import sparse
        # dist_ori = pairwise_distances(data.position, data.position, metric='euclidean')
        distance = _cal_pairwise_distances(data.position, data.position)
        if isinstance(genelist, np.ndarray):
            genelist = list(genelist)
        elif isinstance(genelist, list):
            genelist = genelist
        elif isinstance(genelist, str):
            genelist = [genelist]
        elif isinstance(genelist, int):
            genelist = [genelist]

        thresh = np.linspace(0, dist_thres, num=steps+1)
        out = {}
        if use_col in data.cells:
            groups:np.ndarray = data.cells[use_col].to_numpy()
        else:
            groups:np.ndarray = self.pipeline_res[use_col]['group'].to_numpy()
        group_codes = natsorted(np.unique(groups))
        for ep in range(thresh.shape[0] - 1):
            thresh_l, thresh_r = thresh[ep], thresh[ep+1]
            if genelist is None:
                #df = data.obs[['Centroid_X', 'Centroid_Y', use_col]]
                count = {x: 0 for x in group_codes}
                ret = defaultdict(dict)
                for x in group_codes:
                    for y in group_codes:
                        ret[x][y] = 0
                for x, y in enumerate(groups):
                    for z in np.unique(groups[(distance[x] >= thresh_l) & (distance[x] < thresh_r)]):
                        ret[y][z] += 1
                    count[y] += 1
                ret = pd.DataFrame(ret)
                ret = ret / count
                out[thresh_r] = ret
            else:
                ret = defaultdict(dict)
                for x in group_codes:
                    for y in genelist:
                        ret[x][y] = 0
                count = {x: 0 for x in group_codes}
                gene_exp_dic = {}
                for z in genelist:
                    if data.issparse():
                        gene_exp=data.exp_matrix[:, np.isin(data.genes.gene_name, z)].toarray().flatten()
                    else:
                        gene_exp=data.exp_matrix[:, np.isin(data.genes.gene_name, z)].flatten()
                    gene_exp[gene_exp<gene_thresh] = 0
                    gene_exp_dic[z] = gene_exp
                for x, y in enumerate(groups):
                    flag = np.where((distance[x] >= thresh_l) & (distance[x] < thresh_r), 1, 0)
                    for z in genelist:
                        if (gene_exp_dic[z] * flag).sum() > 0:
                            ret[y][z] += 1
                    count[y] += 1
                ret=pd.DataFrame(ret)
                ret=ret/count
                out[thresh_r] = ret
        ret = {}
        for x in out[thresh_r].index:
            tmp = {}
            for ep in out:
                tmp[ep] = out[ep].T[x]
            ret[x] = pd.DataFrame(tmp).T
        # data.tl.result['co-occur'] = ret
        return ret

    def test_co_occurrence(self):
        '''
        test fuction to chech codes 
        '''
        #mouse_data_path = 'data/SS200000135TL_D1.cellbin.gef'
        #data = st.io.read_gef(file_path=mouse_data_path, bin_type='cell_bins')
        mouse_data_path = '/jdfssz2/ST_BIOINTEL/P20Z10200N0039/06.groups/04.Algorithm_tools/caolei2/Stereopy/data/SS200000135TL_D1.cellbin.h5ad'
        data = st.io.read_stereo_h5ad(file_path=mouse_data_path, use_raw=False, use_result=True)
        self.co_occurrence(data, use_col='leiden')
        self.co_occurrence_plot(data, use_col='leiden',groups=['1','2','3','4', '5'], savefig = './co_occurrence_plot.png')
        self.co_occurrence_heatmap(data, use_col='leiden', dist_max=80, savefig = './co_occurrence_plot.png')
        return data

    def ms_co_occur_integrate(self, ms_data, scope, use_col, use_key = 'co-occur'):
        from collections import Counter, defaultdict
        if use_col not in ms_data.obs:
            tmp_list = []
            for data in ms_data:
                tmp_list.extend(list(data.cells[use_col]))
            ms_data.obs[use_col]=tmp_list
        ms_data.obs[use_col] =  ms_data.obs[use_col].astype('category')

        slice_groups = scope.split('|')
        if len(slice_groups) == 1:
            slices = slice_groups[0].split(",")
            ct_count = {}
            for x in slices:
                ct_count[x] = dict(Counter(ms_data[x].cells[use_col]))

            ct_count = pd.DataFrame(ct_count)
            ct_ratio = ct_count.div(ct_count.sum(axis=1), axis=0)
            ct_ratio = ct_ratio.loc[ms_data.obs[use_col].cat.categories]
            merge_co_occur_ret = ms_data[slices[0]].tl.result[use_key].copy()
            merge_co_occur_ret = {x:y[ms_data.obs[use_col].cat.categories] *0 for x, y  in merge_co_occur_ret.items()}
            for ct in merge_co_occur_ret:
                for x in slices:
                    merge_co_occur_ret[ct] += ms_data[x].tl.result[use_key][ct] * ct_ratio[x]

        elif len(slice_groups) == 2:
            ret = []
            for tmp_slice_groups in slice_groups:
                slices = tmp_slice_groups.split(",")
                ct_count = {}
                for x in slices:
                    ct_count[x] = dict(Counter(ms_data[x].cells[use_col]))

                ct_count = pd.DataFrame(ct_count)
                ct_ratio = ct_count.div(ct_count.sum(axis=1), axis=0)
                ct_ratio = ct_ratio.loc[ms_data.obs[use_col].cat.categories]
                merge_co_occur_ret = ms_data[slices[0]].tl.result[use_key].copy()
                merge_co_occur_ret = {x:y[ms_data.obs[use_col].cat.categories] *0 for x, y  in merge_co_occur_ret.items()}
                for ct in merge_co_occur_ret:
                    for x in slices:
                        merge_co_occur_ret[ct] += ms_data[x].tl.result[use_key][ct] * ct_ratio[x]
                ret.append(merge_co_occur_ret)

            merge_co_occur_ret = {ct:ret[0][ct]-ret[1][ct] for ct in merge_co_occur_ret}

        else:
            print('co-occurrence only compare case and control on two groups')
            merge_co_occur_ret = None

        return merge_co_occur_ret

if __name__ == '__main__':
    test = CoOccurrence()
    data = test.test_co_occurrence()
