import torch

from torch import nn

import swav_resnet as resnet_models


def accuracy(output, target, topk=(1,)):
    """Computes the accuracy over the k top predictions for the specified values of k"""
    with torch.no_grad():
        maxk = max(topk)
        batch_size = target.size(0)

        _, pred = output.topk(maxk, 1, True, True)
        pred = pred.t()
        correct = pred.eq(target.view(1, -1).expand_as(pred))

        res = []
        for k in topk:
            correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
            res.append(correct_k.mul_(100.0 / batch_size))
        return res


class Classification(nn.Module):
    def __init__(self, cfg):
        super(Classification, self).__init__()

        self.device = torch.device(cfg.MODEL.DEVICE)

        # self.network = cfg.build_backbone(
        #     cfg, input_shape=ShapeSpec(channels=len(cfg.MODEL.PIXEL_MEAN)))
        self.network = resnet_models.__dict__[cfg.MODEL.RESNETS.ARCH](output_dim=0, eval_mode=True)

        self.av_pool = nn.AdaptiveAvgPool2d((1, 1))
        self.linear = nn.Linear(2048, cfg.MODEL.RESNETS.NUM_CLASSES)
        # init the fc layer
        self.linear.weight.data.normal_(mean=0.0, std=0.01)
        self.linear.bias.data.zero_()

        self.freeze()
        self.network.eval()

        self.loss_evaluator = nn.CrossEntropyLoss()

        pixel_mean = torch.Tensor(cfg.MODEL.PIXEL_MEAN).to(self.device).view(3, 1, 1)
        pixel_std = torch.Tensor(cfg.MODEL.PIXEL_STD).to(self.device).view(3, 1, 1)
        self.normalizer = lambda x: (x / 255.0 - pixel_mean) / pixel_std

        self.to(self.device)

    def freeze(self):
        for name, param in self.network.named_parameters():
            param.requires_grad = False

    def forward(self, batched_inputs):
        self.network.eval()

        images = self.preprocess_image(batched_inputs)
        outputs = torch.flatten(self.av_pool(self.network(images)), 1)
        preds = self.linear(outputs) 

        if self.training:
            labels = torch.tensor([gi["category_id"] for gi in batched_inputs]).cuda()
            losses = self.loss_evaluator(preds, labels)
            acc1, acc5 = accuracy(preds, labels, topk=(1, 5))

            return {
                "loss_cls": losses,
                "top1_acc": acc1,
                "top5_acc": acc5,
            }
        else:
            return preds

    def preprocess_image(self, batched_inputs):
        """
        Normalize, pad and batch the input images.
        """
        images = [x["image"].float().to(self.device) for x in batched_inputs]
        images = torch.stack([self.normalizer(x) for x in images])
        return images
