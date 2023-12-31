from torch import nn
import argparse


def setup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Reproduce of multiple continual learning algorithms.")
    parser.add_argument("--convnet_type", "-net", type=str, default="resnet32")
    return parser


def get_convnet(convnet_type: str, pretrained: bool = False):
    name = convnet_type.lower()
    if name == "memo_resnet32":
        _basenet, _adaptive_net = 


class BaseLeaner(object):
    def __init__(self, args):
        self.args = args
        self._cur_task = -1
        self._known_classes = 0
        self._total_classes = 0


class MEMO(BaseLeaner):
    def __init__(self, args):
        super().__init__(args)
        self._old_base = None
        self._network = AdaptiveNet(args["convnet_type"], False)


class BaseNet(nn.Module):
    def __init__(self, convnet_type, pretrained):
        super(BaseNet, self).__init__()
        self.convnet = get_convnet(convnet_type, pretrained)


class IncrementNet(BaseNet):
    def __init__(self, convnet_type, pretrained):
        super().__init__(convnet_type, pretrained)


class AdaptiveNet(nn.Module):
    def __init__(self, convnet_type, pretrained):
        super(AdaptiveNet, self).__init__()
        self.convnet_type = convnet_type
        self.TaskAgnosticExtractor, _ = get_convnet


def train(args):
    model = MEMO(args=args)


def main():
    args = setup_parser().parse_args()
    args = vars(args)
    train(args=args)


if __name__ == "__main__":
    main()
