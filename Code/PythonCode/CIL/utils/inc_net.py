import copy
import logging
import torch
from torch import nn
import numpy as np


from convs.linears import SimpleLinear
from convs.memo_cifar_resnet import get_resnet32_a2fc as get_memo_resnet32
import matplotlib.pyplot as plt


def get_convnet(convnet_type: str, pretrained: bool = False) -> (nn.Module, nn.Module):
    """Return generalize block + specialize block"""
    name = convnet_type.lower()
    if name == "resnet32":
        pass
    elif name == "memo_resnet32":
        return get_memo_resnet32()


class AdaptiveNet(nn.Module):
    TaskAgnosticExtractor: nn.Module
    """Generalized block"""
    AdaptiveExtractors: nn.ModuleList
    "Specialized block"
    fc: SimpleLinear
    "Fully connected block"

    def __init__(self, convnet_type: str, pretrained: bool):
        super(AdaptiveNet, self).__init__()
        self.convnet_type = convnet_type
        self.TaskAgnosticExtractor: nn.Module
        self.TaskAgnosticExtractor, _ = get_convnet(convnet_type=convnet_type, pretrained=pretrained)
        logging.info(f"Task Agnostic Extractor is: {type(self.TaskAgnosticExtractor)}")
        logging.info(f"Task agnostic extractor structure: {self.TaskAgnosticExtractor}")
        self.TaskAgnosticExtractor.train()
        self.AdaptiveExtractors = nn.ModuleList()
        self.out_dim = None
        self.fc = None
        self.aux_fc = None
        self.task_sizes = []

    @property
    def feature_dim(self):
        """Feature dimension. Apparently it is used as input for fully connected layer LOL."""
        if self.out_dim is None:
            return 0
        return self.out_dim*len(self.AdaptiveExtractors)

    def extract_vector(self, x):
        base_feature_map = self.TaskAgnosticExtractor(x)
        features = [extractor(base_feature_map) for extractor in self.AdaptiveExtractors]
        features = torch.cat(features, 1)
        return features

    def update_fc(self, nb_classes):
        """Updating specialized adaptive net and fully connected layers"""
        logging.info("----------------------------------------------------")
        logging.info("Calling function update_fc from Adaptive net class...")
        logging.info("Updating fully connected layer...")
        # if self.fc is not None:
        #     plt.imshow(self.fc.weight.detach().numpy())
        #     plt.show()

        _, _new_extractor = get_convnet(self.convnet_type)
        # logging.info("Get extractor")
        # logging.info(_new_extractor)

        if len(self.AdaptiveExtractors) == 0:
            self.AdaptiveExtractors.append(_new_extractor)
        else:
            self.AdaptiveExtractors.append(_new_extractor)
            self.AdaptiveExtractors[-1].load_state_dict(self.AdaptiveExtractors[-2].state_dict())

        logging.info(f"Current adaptive extractor: {self.AdaptiveExtractors}")

        if self.out_dim is None:
            # logging.info(self.AdaptiveExtractors[-1])
            self.out_dim = self.AdaptiveExtractors[-1].feature_dim

        logging.info(f"out dim is: {self.out_dim}")
        logging.info(f"Current fc is: {self.fc}")
        logging.info(f"Generating fully connected layer with in_dim {self.feature_dim}, out_dim {nb_classes}")

        fc = self.generate_fc(in_dim=self.feature_dim, out_dim=nb_classes)

        if self.fc is not None:
            # with open("data.json", "a+") as f:
                # json.dump(self.fc.weight.data, f)
                # json.dump(self.fc.weight.requires_grad, f)
            # torch.save(self.fc.weight, "tensor.pt")
            np.savetxt(fname=f"tensor-{len(self.AdaptiveExtractors)}.txt", X=self.fc.weight.detach().numpy())

        if self.fc is not None:
            nb_output = self.fc.out_features
            weight = copy.deepcopy(self.fc.weight.data)
            bias = copy.deepcopy(self.fc.bias.data)
            fc.weight.data[:nb_output, :self.feature_dim-self.out_dim] = weight
            fc.bias.data[:nb_output] = bias
        del self.fc
        self.fc = fc
        logging.info(f"New fc is: {self.fc}")
        new_task_size = nb_classes - sum(self.task_sizes)
        self.task_sizes.append(new_task_size)
        self.aux_fc = self.generate_fc(self.out_dim, new_task_size + 1)

    def generate_fc(self, in_dim: int, out_dim: int):
        fc = SimpleLinear(in_features=in_dim, out_features=out_dim)
        return fc

    def weight_align(self, increment):
        weights = self.fc.weight.data
        newnorm = (torch.norm(weights[-increment:, :], p=2, dim=1))
        oldnorm = (torch.norm(weights[:-increment, :], p=2, dim=1))
        meannew = torch.mean(newnorm)
        meanold = torch.mean(oldnorm)
        gamma = meanold/meannew
        print('alignweights,gamma=', gamma)
        self.fc.weight.data[-increment:, :] *= gamma

    def forward(self, x):
        base_feature_map = self.TaskAgnosticExtractor(x)
        features = [extractor(base_feature_map) for extractor in self.AdaptiveExtractors]

        # logging.info(f"output feature size is: {len(features)}")

        features = torch.cat(features, 1)

        # logging.info(f"output feature size is: {features.size()}")

        out = self.fc(features)  # {logits: self.fc(features)}

        aux_logits = self.aux_fc(features[:, -self.out_dim:])["logits"]

        out.update({"aux_logits": aux_logits, "features": features})
        out.update({"base_features": base_feature_map})
        return out

        '''
        {
            'features': features
            'logits': logits
            'aux_logits':aux_logits
        }
        '''

    def load_checkpoint(self, args):
        if args["init_cls"] == 50:
            pkl_name = "{}_{}_{}_B{}_Inc{}".format(args["dataset"],
                                                   args["seed"],
                                                   args["convnet_type"], 0, args["init_cls"])
            checkpoint_name = f"checkpoints/finetune_{pkl_name}_0.pkl"
        else:
            checkpoint_name = f"checkpoints/finetune_{args['csv_name']}_0.pkl"
        checkpoint_name = checkpoint_name.replace("memo_", "")
        model_infos = torch.load(checkpoint_name)
        model_dict: dict = model_infos["convnet"]
        assert len(self.AdaptiveExtractors) == 1

        base_state_dict = self.TaskAgnosticExtractor.state_dict()
        adapt_base_dict = self.AdaptiveExtractors[0].state_dict()
        pretrained_base_dict = {
            k: v for k, v in model_dict.items() if k in base_state_dict
        }
        pretrained_adap_dict = {
            k: v for k, v in model_dict.items() if k in adapt_base_dict
        }
        base_state_dict.update(pretrained_base_dict)
        adapt_base_dict.update(pretrained_adap_dict)

        self.TaskAgnosticExtractor.load_state_dict(base_state_dict)
        self.AdaptiveExtractors.load_state_dict(adapt_base_dict)
        self.fc.load_state_dict(model_infos["fc"])
        test_acc = model_infos["test_acc"]
        return test_acc
