import logging
import numpy as np
from tqdm import tqdm
import torch
from torch import nn
from torch import optim
from torch.nn import functional as F
from models.base import BaseLearner
from torch.utils.data import DataLoader
from utils.inc_net import AdaptiveNet
from utils.data_manager import DataManager
from utils.toolkit import count_parameters, tensor2numpy

num_workers = 8


class MEMO(BaseLearner):
    _network: AdaptiveNet

    def __init__(self, args):
        super().__init__(args)
        self.args = args
        self._network = AdaptiveNet(convnet_type=args["convnet_type"], pretrained=False)
        logging.info(
            f">>> train generalized blocks:{self.args['train_base']} train_adaptive: {self.args['train_adaptive']}")

    def after_task(self):
        """After task"""
        logging.info("Running after task....")
        self._known_classes = self._total_classes
        if self._cur_task == 0:
            if self.args["train_base"]:
                logging.info("Train Generalized Blocks...")
                self._network.TaskAgnosticExtractor.train()
                for param in self._network.TaskAgnosticExtractor.parameters():
                    param.requires_grad = True
            else:
                logging.info("Fix Generalized Blocks...")
                self._network.TaskAgnosticExtractor.eval()
                for param in self._network.TaskAgnosticExtractor.parameters():
                    param.requires_grad = False
        logging.info("Exemplar size: {}".format(self.exemplar_size))

    def incremental_training(self, data_manager: DataManager):
        """Training model"""
        self._cur_task += 1
        self._total_classes = self._known_classes + data_manager.get_task_size(self._cur_task)
        self._network.update_fc(self._total_classes)

        logging.info("Learning on {}-{}".format(self._known_classes, self._total_classes))

        if self._cur_task > 0:
            for i in range(self._cur_task):
                for p in self._network.AdaptiveExtractors[i].parameters():
                    if self.args["train_adaptive"]:
                        p.requires_grad = True
                    else:
                        p.requires_grad = False

        logging.info("All params: {}".format(count_parameters(self._network, trainable=False)))
        logging.info("Trainable params: {}".format(count_parameters(self._network, trainable=True)))

        train_dataset = data_manager.get_dataset(
            indices=np.arange(self._known_classes, self._total_classes),
            source="train",
            mode="train",
            appendent=self._get_memory()
        )
        self.train_loader = DataLoader(dataset=train_dataset, batch_size=self.args["batch_size"],
                                       shuffle=True, num_workers=num_workers)

        test_dataset = data_manager.get_dataset(
            indices=np.arange(0, self._total_classes),
            source="test",
            mode="test",
        )
        self.test_loader = DataLoader(dataset=test_dataset, batch_size=self.args["batch_size"],
                                      shuffle=False, num_workers=num_workers)
        if len(self._multiple_gpus) > 1:
            self._network = nn.DataParallel(module=self._network, device_ids=self._multiple_gpus)
        self._train(self.train_loader, self.test_loader)

    def set_network(self):
        if len(self._multiple_gpus) > 1:
            self._network = self._network.module
        self._network.train()
        if self.args["train_base"]:
            self._network.TaskAgnosticExtractor.train()
        else:
            self._network.TaskAgnosticExtractor.eval()

        # set adaptive extractor's status
        self._network.AdaptiveExtractor[-1].train()
        if self._cur_task >= 1:
            for i in range(self._cur_task):
                if self.args["train_adaptive"]:
                    self._network.AdaptiveExtractor[i].train()
                else:
                    self._network.AdaptiveExtractor[i].eval()
        if len(self._multiple_gpus) > 1:
            self._network == nn.DataParallel(self._network, self._multiple_gpus)

    def _train(self, train_loader, test_loader):
        self._network.to(self._device)
        if self._cur_task == 0:
            optimizer = optim.SGD(params=filter(lambda p: p.requires_grad, self._network.parameters()),
                                  lr=self.args["lrate"],
                                  momentum=0.9,
                                  weight_decay=self.args["weight_decay"]
                                  )
            if self.args["scheduler"] == "steplr":
                scheduler = optim.lr_scheduler.MultiStepLR(
                    optimizer=optimizer,
                    milestones=self.args["init_milestones"],
                    gamma=self.args["lrate_decay"],
                )
            elif self.args["scheduler"] == "cosine":
                assert self.args["t_max"] is not None
                scheduler = optim.lr_scheduler.CosineAnnealingLR(
                    optimizer=optimizer,
                    T_max=self.args["t_max"]
                )
            else:
                raise NotImplementedError
            if not self.args["skip"]:
                self._init_train(train_loader, test_loader, optimizer, scheduler)
            else:
                if isinstance(self._network, nn.DataParallel):
                    self._network = self._network.module
                load_acc = self._network.load_checkpoint(self.args)
                self._network.to(self._device)

                if len(self._multiple_gpus) > 1:
                    self._network = nn.DataParallel(self._network, self._multiple_gpus)
                cur_test_acc = self._compute_accuracy(self._network, self.test_loader)
                logging.info(f"Loaded_Test_Acc:{load_acc} Cur_Test_Acc:{cur_test_acc}")
        else:
            optimizer = optim.SGD(
                params=filter(lambda p: p.requires_grad, self._network.parameters()),
                lr=self.args["lrate"],
                momentum=0.9,
                weight_decay=self.args["weight_decay"],
            )
            if self.args["scheduler"] == "steplr":
                scheduler = optim.lr_scheduler.MultiStepLR(
                    optimizer=optimizer,
                    milestones=self.args["milestones"],
                    gamma=self.args["lrate_decay"],
                )
            elif self.args["scheduler"] == "cosine":
                assert self.args["t_max"] is not None
                scheduler = optim.lr_scheduler.CosineAnnealingLR(
                    optimizer=optimizer,
                    T_max=self.args["t_max"],
                )
            else:
                raise NotImplementedError
            self._update_representation(train_loader, test_loader, optimizer, scheduler)
            if len(self._multiple_gpus) > 1:
                self._network.module.weight_align(self._total_classes - self._known_classes)
            else:
                self._network.weight_align(self._total_classes - self._known_classes)

    def _init_train(self, train_loader: DataLoader, test_loader: DataLoader, optimizer, scheduler):
        prog_bar = tqdm(range(self.args["init_epoch"]))
        for _, epoch in enumerate(prog_bar):
            self._network.train()
            losses = 0
            correct, total = 0, 0

            for i, (_, inputs, targets) in enumerate(train_loader):
                inputs, targets = inputs.to(self._device), targets.to(self._device)
                logits = self._network(inputs)["logits"]
                loss = F.cross_entropy(logits, targets)
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()
                losses += loss.item()

                _, preds = torch.max(logits, dim=1)
                correct += preds.eq(targets.expand_as(preds)).cpu().sum()
                total += len(targets)

            scheduler.step()

            train_acc = np.around(tensor2numpy(correct) * 100 / total, decimals=2)

            # Generate info message
            if epoch % 5 == 0:
                test_acc = self._compute_accuracy(self._network, test_loader)
                info = 'Task {}, Epoch {}/{} => Loss {:.3f}, Train_accy {:.2f}, Test_accy {:.2f}'.format(
                    self._cur_task, epoch + 1,
                    self.args["init_epoch"],
                    losses / len(train_loader), train_acc, test_acc
                )
            else:
                info = "Task {}, Epoch {}/{} => Loss {:.3f}, Train_accy {:.2f}".format(
                    self._cur_task, epoch + 1, self.args["init_epoch"], losses / len(train_loader), train_acc
                )
            logging.info(info)

    def _update_representation(self, train_loader: DataLoader,
                               test_loader: DataLoader, optimizer: optim.SGD, scheduler):
        prog_bar = tqdm(range(self.args["epochs"]))
        for _, epoch in enumerate(prog_bar):
            self.set_network()
            losses = 0.
            losses_clf = 0.
            losses_aux = 0.
            correct, total = 0, 0
            for i, (_, inputs, targets) in enumerate(train_loader):
                inputs, targets = inputs.to(self._device), targets.to(self._device)
                outputs = self._network(inputs)
                logits, aux_logits = outputs["logits"], outputs["aux_logits"]
                loss_clf = F.cross_entropy(logits, targets)
                logging.info(f"Type of target is: {type(targets)}")
                aux_targets = targets.clone()
                aux_targets = torch.where(condition=aux_targets-self._known_classes + 1 > 0,
                                          input=aux_targets - self._known_classes + 1, other=0)
                loss_aux = F.cross_entropy(aux_logits, aux_targets)
                loss = loss_clf + self.args["alpla_aux"] * loss_aux

                optimizer.zero_grad()
                loss.bachward()
                optimizer.step()
                losses += loss.item()
                losses_aux += loss_aux.item()
                losses_clf += loss_clf.item()

                _, preds = torch.max(logits, dim=1)
                correct += preds.eq(targets.expand_as(preds)).cpu().sum()
                total += len(targets)

                scheduler.step()
                train_acc = np.around(tensor2numpy(correct) * 100 / total, decimals=2)
                if epoch % 5 == 0:
                    test_acc = self._compute_accuracy(self._network, test_loader)
                    info = "Task {}, Epoch {}/{} => Loss {:.3f}, Loss_clf {:.3f}, Loss_aux {:.3f}, Train_accy {:.2f}, Test_accy {:.2f}".format(
                        self._cur_task,
                        epoch + 1,
                        self.args["epochs"],
                        losses/len(train_loader),
                        losses_clf/len(train_loader),
                        losses_aux/len(train_loader),
                        train_acc,
                        test_acc
                    )
                else:
                    info = "Task {}, Epoch {}/{} => Loss {:.3f}, Loss_clf {:.3f}, Loss_aux {:.3f} Train_accy {:.2f}".format(
                        self._cur_task,
                        epoch + 1,
                        self.args["epochs"],
                        losses/len(train_loader),
                        losses_clf/len(train_loader),
                        loss_aux/len(train_loader),
                        train_acc,
                    )
                prog_bar.set_description(info)
                logging.info(info)