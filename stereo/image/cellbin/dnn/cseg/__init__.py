from abc import ABC
from abc import abstractmethod


class CellSegmentation(ABC):
    @abstractmethod
    def f_predict(self, img):
        """
        input img output cell mask
        :param img:CHANGE
        :return: 掩模大图
        """
        return
