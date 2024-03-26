import logging
import numpy as np
from PIL import Image
from torch.utils.data import Dataset
from torchvision import transforms
from utils.data import iData, iCIFAR10, iCIFAR100, KDD99
from utils.cic_ids_2017_data import CIC_IDS_2017
from utils.ton_iot_network_data import TON_IoT_Network
from utils.unsw_nb15_data import UNSW_NB15
from utils.image_net_100_data import iImageNet100


class DataManager(object):
    """
    This class return train and test dataset
    """
    dataset_name: str
    """Name of the dataset"""
    _increments: list
    """_increments[i]: Number of classes at training iterator i"""

    def __init__(self, dataset_name: str, shuffle: bool, seed: int, init_cls: int, increment: int, **kwargs):
        logging.info("Initialize Data Manager ...")
        self.dataset_name = dataset_name

        if self.dataset_name in ["kdd99", "cic-ids-2017", "ton-iot-network", "unsw-nb15"]:
            self.is_image = False
        else:
            self.is_image = True

        self._setup_data(dataset_name, shuffle, seed, **kwargs)

        assert init_cls <= len(self._class_order), "Not enough classes."
        self._increments = [init_cls]
        while sum(self._increments) + increment < len(self._class_order):
            self._increments.append(increment)
        offset = len(self._class_order) - sum(self._increments)
        if offset > 0:
            self._increments.append(offset)

    @property
    def nb_tasks(self):
        return len(self._increments)

    def get_task_size(self, task):
        """Return number of total classes at training iterator task"""
        return self._increments[task]

    def get_dataset(self, indices, source, mode, appendent=None, ret_data: bool = False, m_rate=None):
        """indices: list of training classes

        Args:
            appendent: Data adding to the dataset \n
            mode: ["train", "test"]. If mode is test, dont use train transform like crop, flip, zitter, ....
        """
        logging.info("Calling function get dateset from data manager ...")
        if source == "train":
            logging.info("Source: Train")
            x, y = self._train_data, self._train_targets
        elif source == "test":
            x, y = self._test_data, self._test_targets
            logging.info("Source: Test")
        else:
            raise ValueError("Unkown data source {}".format(source))
        if mode == "train":
            trsf = transforms.Compose([*self._train_trsf, *self._common_trsf])
        elif mode == "flip":
            trsf = transforms.Compose([
                *self._test_trsf,
                transforms.RandomHorizontalFlip(p=1.0),
                *self._common_trsf
            ])
        elif mode == "test":
            trsf = transforms.Compose([*self._test_trsf, *self._common_trsf])
        else:
            raise ValueError("Unknown mode{}".format(mode))
        data, targets = [], []
        for idx in indices:
            if m_rate is None:
                class_data, class_targets = self._select(x, y, low_range=idx, high_range=idx+1)
            else:
                class_data, class_targets = self._select_rmm(x, y, low_range=idx, high_range=idx + 1, m_rate=m_rate)
            data.append(class_data)
            targets.append(class_targets)

        if appendent is not None and len(appendent) != 0:
            appendent_data, appendent_targets = appendent
            data.append(appendent_data)
            targets.append(appendent_targets)
        data, targets = np.concatenate(data), np.concatenate(targets)

        # Get statistic of data
        uniques, counts = np.unique(targets, return_counts=True)

        for target, count in zip(uniques, counts):
            logging.info("Target: {}, Count: {}".format(target, count))

        if ret_data:
            return data, targets, DummyDataset(data, targets, trsf, self.use_path, is_image=self.is_image)
        else:
            return DummyDataset(data, targets, trsf, self.use_path, is_image=self.is_image)

    def _setup_data(self, dataset_name: str, shuffle: bool, seed, **kwargs):
        """Downloading data -> Set up train and test data"""
        logging.info("Set up data ...")
        idata: iData = _get_idata(dataset_name, **kwargs)
        idata.download_data()

        # Data
        self._train_data, self._train_targets = idata.train_data, idata.train_targets
        self._test_data, self._test_targets = idata.test_data, idata.test_targets
        self.use_path = idata.use_path

        # Transforms
        self._train_trsf = idata.train_trsf
        self._test_trsf = idata.test_trsf
        self._common_trsf = idata.common_trsf

        # Order
        order = [i for i in range(len(np.unique(self._train_targets)))]
        if shuffle:
            np.random.seed(seed=seed)
            order = np.random.permutation(len(order)).tolist()
            if dataset_name == "cic-ids-2017":
                order = [4, 0, 8, 2, 3, 7, 9, 6, 5, 1, 10, 11]
            elif dataset_name == "kdd99":
                order = [8, 2, 4, 0, 7, 1, 6, 10, 9, 5, 3]
        else:
            order = idata.class_order
        self._class_order = order

        # print mapping if idata has label dict
        if hasattr(idata, "label_dict"):
            class_order_name = []
            for class_idx in self._class_order:
                for name, idx in idata.label_dict.items():
                    if class_idx == idx:
                        class_order_name.append(name)
            logging.info(f"Class order is: {class_order_name}")
        logging.info(f"Class order is: {self._class_order}")

        # Map indices
        self._train_targets = _map_new_class_index(self._train_targets, self._class_order)
        self._test_targets = _map_new_class_index(self._test_targets, self._class_order)

        del idata

    def _select(self, x, y, low_range, high_range):
        idxes = np.where(np.logical_and(y >= low_range, y < high_range))[0]
        return x[idxes], y[idxes]

    def _select_rmm(self, x, y, low_range, high_range, m_rate):
        assert m_rate is not None
        if m_rate != 0:
            indxes = np.where(np.logical_and(y >= low_range, y < high_range))[0]
            selected_idxes = np.random.randint(0, len(indxes), size=int((1 - m_rate) * len(indxes)))
            new_idxes = indxes[selected_idxes]
            new_idxes = np.sort(new_idxes)
        else:
            new_idxes = np.where(np.logical_and(y >= low_range, y < high_range))[0]
        return x[new_idxes], y[new_idxes]

    def getlen(self, index):
        """Return length of train target of given index"""
        y = self._train_targets
        return np.sum(np.where(y == index))


class DummyDataset(Dataset):
    def __init__(self, images, labels, trsf, use_path=False, is_image: bool = True):
        assert len(images) == len(labels), "Data size error!"

        self.images = images
        del images

        self.labels = labels
        del labels

        self.trsf = trsf
        self.use_path = use_path
        self.is_image = is_image

    def __len__(self):
        return len(self.images)

    def __getitem__(self, idx):
        label = self.labels[idx]

        # Handling data
        if self.is_image:
            if self.use_path:
                image = self.trsf(pil_loader(self.images[idx]))
            else:
                image = self.trsf(Image.fromarray(self.images[idx]))
        else:
            image = self.images[idx]

        return idx, image, label


def _map_new_class_index(y, order: list):
    return np.array(list(map(lambda x: order.index(x), y)))


def _get_idata(dataset_name: str, **kwargs):
    """Return dataset name"""
    logging.info("Get idata ...")
    name = dataset_name.lower()
    if name == "cifar10":
        return iCIFAR10()
    elif name == "cifar100":
        return iCIFAR100()
    elif name == "kdd99":
        return KDD99(**kwargs)
    elif name == "cic-ids-2017":
        return CIC_IDS_2017(**kwargs)
    elif name == "ton-iot-network":
        return TON_IoT_Network()
    elif name == "imagenet100":
        return iImageNet100()
    elif name == "unsw-nb15":
        return UNSW_NB15(**kwargs)
    else:
        raise NotImplementedError("Unknown dataset {}.".format(dataset_name))


def pil_loader(path):
    with open(path, "rb") as f:
        img = Image.open(f)
        return img.convert("RGB")
