import time
from collections import defaultdict

import scipy
import numba
import numpy as np
import pandas as pd
from tqdm import tqdm
from joblib import Parallel, delayed, cpu_count

from ...log_manager import logger
from ..algorithm_base import AlgorithmBase
from .utils import corr_spearman, apply_along_axis
from ...core.stereo_exp_data import StereoExpData, AnnBasedStereoExpData


class _TestData(object):

    def __init__(self, exp_matrix, cell_names, gene_names):
        self.exp_matrix = exp_matrix
        self.cell_names = cell_names
        self.gene_names = gene_names

    def to_df(self):
        return pd.DataFrame(self.exp_matrix.toarray(), index=self.cell_names, columns=self.gene_names)


def _spearman_parallel(label, ranked_mat_ref, y, quantile):
    ranked_mat_qry = apply_along_axis(y)
    sim = corr_spearman(ranked_mat_ref, ranked_mat_qry)
    return label, np.percentile(sim, quantile, axis=1)


def _get_label_genes_set(top_labels, trained_data, de_n_len=0):
    de_n = np.round(500 * (2 / 3) ** np.log2(de_n_len if de_n_len else len(top_labels)))
    res_set = set()
    for i in top_labels:
        for j in top_labels:
            if i != j:
                res_set = res_set.union(trained_data[i][j][:int(de_n)])
    return res_set


class SingleR(AlgorithmBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n_jobs = None
        self.quantile = None
        self.ref_exp_data = None
        self.fine_tune_times = None
        self.group_data_frame = None
        self.fine_tune_threshold = None

    def main(
            self,
            ref_exp_data: StereoExpData,
            ref_use_col="celltype",
            test_cluster_col=None,
            quantile=80,
            fine_tune_threshold=0.05,
            fine_tune_times=0,
            n_jobs=int(cpu_count() / 2)
    ):
        assert ref_use_col in ref_exp_data.tl.result
        self.ref_exp_data = ref_exp_data

        self.group_data_frame = ref_exp_data.tl.result[ref_use_col]
        self._group_data_frame_checker()
        self.fine_tune_times = fine_tune_times
        self.fine_tune_threshold = fine_tune_threshold
        self.quantile = quantile
        self.n_jobs = n_jobs

        logger.info(f'start single-r with n_jobs={n_jobs} fine_tune_times={fine_tune_times}')
        the_very_start_time = time.time()

        logger.debug('start training ref...')
        start_time = time.time()
        trained_data, common_gene = self._train_ref()
        logger.debug(f'training ref finished, cost {time.time() - start_time} seconds')

        test_exp_data = self.stereo_exp_data
        if test_cluster_col:
            tmp_exp_matrix = pd.DataFrame(
                test_exp_data.exp_matrix.todense(),
                index=test_exp_data.cell_names,
                columns=test_exp_data.gene_names
            )
            tmp_exp_matrix = tmp_exp_matrix.groupby(test_exp_data.tl.result[test_cluster_col]['group']).sum()
            test_data = _TestData(scipy.sparse.csr_matrix(tmp_exp_matrix.values), tmp_exp_matrix.index,
                                  test_exp_data.gene_names)
        else:
            test_data = _TestData(test_exp_data.exp_matrix, test_exp_data.cell_names, test_exp_data.gene_names)

        logger.debug('start scoring test_data...')
        start_time = time.time()

        output, labels_array = self._score_test_data(test_data, common_gene)
        logger.info(f'scoring test_data finished, cost {time.time() - start_time} seconds')

        logger.debug('start fine-tuning...')
        start_time = time.time()
        ret_labels = self._fine_tune(test_data, output, trained_data)
        logger.debug(f'fine-tuning finished, cost {time.time() - start_time} seconds')

        res = pd.DataFrame(columns=['bins', 'group', 'first_labels'])
        res['bins'] = output.index
        res['group'] = ret_labels
        res['first_labels'] = labels_array
        logger.info(f'single-r finished, cost {time.time() - the_very_start_time} seconds')
        if not test_cluster_col and not isinstance(test_exp_data, AnnBasedStereoExpData):
            self.pipeline_res[ref_use_col] = res
        return res

    def _train_ref(self):
        median_exp = pd.DataFrame(index=self.ref_exp_data.gene_names)
        for label, y in self.group_data_frame.groupby('group'):
            cells_bool_list = np.isin(self.ref_exp_data.cell_names, y['bins'].values)
            median_exp[label] = np.median(self.ref_exp_data.exp_matrix[cells_bool_list].toarray(), axis=0)

        ret_all = defaultdict(dict)
        ret_gene = defaultdict(dict)

        ct = self.group_data_frame['group'].astype('category').cat.categories
        de_n = np.round(500 * (2 / 3) ** np.log2(len(ct)))
        common_gene = set()
        res_common_gene = list()
        for i in ct:
            for j in ct:
                if i == j:
                    continue
                tmp_all = median_exp[i] - median_exp[j]
                ret_tmp = pd.DataFrame(tmp_all).round(6)
                ret_tmp['arg'] = list(range(ret_tmp.shape[0] - 1, -1, -1))
                tmp_all = ret_tmp.sort_values([0, 'arg'], ascending=False)
                ret_gene[i][j] = tmp_all.index[:int(de_n)]
                for gene in ret_gene[i][j]:
                    if gene in common_gene:
                        continue
                    common_gene.add(gene)
                    res_common_gene.append(gene)
                tmp_all = tmp_all.loc[tmp_all[0] > 0]
                ret_all[i][j] = tmp_all.index.values

        return ret_all, list(common_gene)

    def _score_test_data(self, test_data, common_gene):
        original_exp = {}
        ref_common_gene_bool_list = np.isin(self.ref_exp_data.gene_names, common_gene)
        for x, y in self.group_data_frame.groupby('group'):
            y_cell_bool_list = np.isin(self.ref_exp_data.cell_names, y['bins'].values)
            original_exp[x] = self.ref_exp_data.exp_matrix[y_cell_bool_list][:, ref_common_gene_bool_list].toarray()

        test_mat = test_data.exp_matrix[:, np.isin(test_data.gene_names, common_gene)].toarray()
        ranked_mat_ref = apply_along_axis(test_mat.T)

        res_dict = dict(Parallel(n_jobs=self.n_jobs, backend="threading")(
            delayed(_spearman_parallel)(label, ranked_mat_ref, y.T, self.quantile)
            for label, y in tqdm(original_exp.items())
        ))

        ret = pd.DataFrame(res_dict, index=test_data.cell_names)
        return ret, ret.columns[np.argmax(ret.values, axis=1)]

    def _fine_tune(self, test_data, output, trained_data):
        tmp = output.values.copy()
        tmp[tmp < np.array(np.nanmax(output.values, axis=1) - self.fine_tune_threshold).reshape([-1, 1])] = 0
        tmp[tmp > 0] = 1

        ref = pd.DataFrame(
            self.ref_exp_data.exp_matrix.toarray(),
            index=self.ref_exp_data.cell_names,
            columns=self.ref_exp_data.gene_names
        )

        logger.info(f'fine-tuning with test_data(shape={test_data.exp_matrix.shape})')

        ret_labels = Parallel(n_jobs=self.n_jobs, backend="threading")(
            delayed(self._fine_tune_parallel)(
                ref,
                output.columns[tmp[x].astype(bool)].values,
                y[1].to_frame().T,
                trained_data
            )
            for x, y in tqdm(enumerate(test_data.to_df().iterrows()))
        )
        return ret_labels

    def _fine_tune_parallel(self, ref, labels, y, trained_data):
        label_genes = _get_label_genes_set(labels, trained_data, 2)
        ref = ref.loc[:, list(label_genes)]
        if self.fine_tune_times:
            try_num = 0
            while try_num < self.fine_tune_threshold and len(labels) > 1:
                labels = self._fine_tune_one_time(labels, ref, y, trained_data)
                try_num += 1
        else:
            while len(labels) > 1:
                labels = self._fine_tune_one_time(labels, ref, y, trained_data)
        return labels[0]

    @numba.jit(forceobj=True, nogil=True, parallel=True)
    def _fine_tune_one_time(self, top_labels, ref, test, trained_data):
        label_genes = _get_label_genes_set(top_labels, trained_data)
        if len(label_genes) < 20:
            return [top_labels[0]]

        genes_filtered = list(label_genes)
        test_filtered = test.loc[:, genes_filtered].values
        if np.std(test_filtered) <= 0:
            return [top_labels[0]]

        bool_list = np.isin(self.group_data_frame['group'].values, top_labels)
        ref_filtered = ref.loc[bool_list, genes_filtered]
        group_data_frame_filtered = self.group_data_frame.loc[bool_list].reset_index()

        ranked_mat_ref = apply_along_axis(test_filtered.T)
        res_labels = {}
        for p, q in group_data_frame_filtered.groupby('group'):
            ref_filtered_by_group = ref_filtered.iloc[q.index].values.T
            ranked_mat_qry = apply_along_axis(ref_filtered_by_group)
            sim = corr_spearman(ranked_mat_ref, ranked_mat_qry)
            if not (sim.shape and sim.shape[0] and sim.shape[1]):
                continue
            res_labels[p] = np.percentile(sim, self.quantile, axis=1)[0]
        if not res_labels:
            return [top_labels[0]]

        # remove the labels lower than median
        mid_value = np.median(list(res_labels.values()))
        res_labels = {p: value for p, value in res_labels.items() if value > mid_value}
        if not res_labels:
            return [top_labels[0]]

        # remove the label lower than fine_tune_threshold
        max_value = max(res_labels.values())
        res_labels = {p: value for p, value in res_labels.items() if value >= max_value - self.fine_tune_threshold}
        if not res_labels:
            return [top_labels[0]]
        return list(res_labels.keys())

    @staticmethod
    def test_rank():
        mat = np.random.sample((5, 5)).astype(np.float32)
        res_self = apply_along_axis(mat)

        from scipy.stats import rankdata
        res_sci = rankdata(mat, axis=0).astype(np.float32)

        assert np.all(res_self == res_sci), 'self define rank is different with the SciPy\'s verions'
        logger.info('test_rank success')

    def _group_data_frame_checker(self):
        assert 'group' in self.group_data_frame.columns
        if 'bins' not in self.group_data_frame.columns:
            self.group_data_frame = self.group_data_frame.reset_index().rename(
                columns={'index': 'bins', 'CellID': 'bins'}
            )
        assert 'bins' in self.group_data_frame.columns

    @staticmethod
    def test_group_data_frame():
        s1 = SingleR(None)
        # cluster result data like
        s1.group_data_frame = pd.DataFrame(index=['cell1', 'cell2'], columns=['bins', 'group'])
        s1._group_data_frame_checker()

        s2 = SingleR(None)
        # h5ad with cell_type data like
        s2.group_data_frame = pd.DataFrame(index=['cell1', 'cell2'], columns=['CellID', 'group'])
        s2._group_data_frame_checker()

        s3 = SingleR(None)
        # h5ad with cell_type data like
        s3.group_data_frame = pd.DataFrame(index=['cell1', 'cell2'], columns=['group'])
        s3._group_data_frame_checker()
        logger.info('test_group_data_frame success')
