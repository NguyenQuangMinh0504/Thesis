import pandas as pd
from torchvision.transforms import ToTensor
from utils.data import iData
from utils.helper import encode_text_dummy, encode_numeric_zscore, to_xy
from sklearn.model_selection import train_test_split
import numpy as np


class UNSW_NB15(iData):
    use_path = False
    train_trsf = []
    test_trsf = []
    common_trsf = [ToTensor()]

    def download_data(self):
        path = "../../../Dataset/UNSW-NB15/UNSW_NB15_training-set.csv"
        dataset = pd.read_csv(path)
        dataset.drop(columns=["id", "attack_cat"], inplace=True)
        for column in dataset.columns:
            if column in ["proto", "service", "state"]:
                encode_text_dummy(dataset, column)
            elif column == "label":
                pass
            else:
                encode_numeric_zscore(dataset, column)
        x, y = to_xy(dataset, 'label')

        dataset.drop(labels=" Label", axis=1)

        self.train_data, self.test_data, self.train_targets, self.test_targets = train_test_split(
            x, y, test_size=0.2, random_state=42)

        self.train_data = self.train_data.astype(np.float32)
        self.test_data = self.test_data.astype(np.float32)
        del dataset
