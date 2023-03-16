#!/usr/bin/env python
# coding: utf-8

import os
from .seg_utils import cell_seg_pipeline as pipeline


def cell_seg_deepcell(
        model_path,
        img_path,
        out_path,
        depp_cro_size=20000,
        overlap=100,
        gpu=-1,
        tissue_seg_model_path=None,
        tissue_seg_method=None,
        post_processing_workers=10
    ):
    """
    cell segmentation.

    :param model_path: the dir path of model.
    :param img_path: image path
    :param out_path: the ouput path of mask result
    :param depp_cro_size: deep crop size
    :param overlap: the size of overlap
    :param gpu: the id of gpu, if -1,use the cpu to predict.
    :param tissue_seg_model_path: the path of deep learning model of tissue segmentation, if set it to None, it would use OpenCV to process.
    :param tissue_seg_method: the method of tissue segmentation, 1 is based on deep learning and 0 is based on OpenCV.
    :param post_processing_workers: the number of processes for post-processing
    :return:
    """
    try:
        import tensorflow as tf
    except Exception:
        raise Exception('please install tensorflow via `pip install tensorflow==2.4.1`.')
    os.environ["CUDA_VISIBLE_DEVICES"] = str(gpu)
    flag = 0
    cell_seg_pipeline = pipeline.CellSegPipe(
        img_path,
        out_path,
        flag,
        depp_cro_size,
        overlap,
        model_path,
        tissue_seg_model_path=tissue_seg_model_path,
        tissue_seg_method=tissue_seg_method,
        post_processing_workers=post_processing_workers
    )
    cell_seg_pipeline.run()
