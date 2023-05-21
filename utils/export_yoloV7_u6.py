import os
import sys
import argparse
import warnings
import onnx
import torch
import torch.nn as nn
from models.experimental import attempt_load
from models.yolo import Detect, V6Detect, IV6Detect
from utils.torch_utils import select_device


class DeepStreamOutput(nn.Module):
    def __init__(self):
        super().__init__()

    def forward(self, x):
        x = x.transpose(1, 2)
        boxes = x[:, :, :4]
        scores, classes = torch.max(x[:, :, 4:], 2, keepdim=True)
        return torch.cat((boxes, scores, classes), dim=2)


def suppress_warnings():
    warnings.filterwarnings('ignore', category=torch.jit.TracerWarning)
    warnings.filterwarnings('ignore', category=UserWarning)
    warnings.filterwarnings('ignore', category=DeprecationWarning)


def yolov7_u6_export(weights, device):
    model = attempt_load(weights, device=device, inplace=True, fuse=True)
    model.eval()
    for k, m in model.named_modules():
        if isinstance(m, (Detect, V6Detect, IV6Detect)):
            m.inplace = False
            m.dynamic = False
            m.export = True
    return model


def main(args):
    suppress_warnings()
    device = select_device('cpu')
    model = yolov7_u6_export(args.weights, device)

    model = nn.Sequential(model, DeepStreamOutput())

    img_size = args.size * 2 if len(args.size) == 1 else args.size

    onnx_input_im = torch.zeros(1, 3, *img_size).to(device)
    onnx_output_file = os.path.basename(args.weights).split('.pt')[0] + '.onnx'

    torch.onnx.export(model, onnx_input_im, onnx_output_file, verbose=False, opset_version=args.opset,
                      do_constant_folding=True, input_names=['input'], output_names=['output'], dynamic_axes=None)

    if args.simplify:
        import onnxsim
        model_onnx = onnx.load(onnx_output_file)
        model_onnx, _ = onnxsim.simplify(model_onnx)
        onnx.save(model_onnx, onnx_output_file)


def parse_args():
    parser = argparse.ArgumentParser(description='DeepStream YOLOv7-u6 conversion')
    parser.add_argument('-w', '--weights', required=True, help='Input weights (.pt) file path (required)')
    parser.add_argument('-s', '--size', nargs='+', type=int, default=[640], help='Inference size [H,W] (default [640])')
    parser.add_argument('--opset', type=int, default=12, help='ONNX opset version')
    parser.add_argument('--simplify', action='store_true', help='ONNX simplify model')
    args = parser.parse_args()
    if not os.path.isfile(args.weights):
        raise SystemExit('Invalid weights file')
    return args


if __name__ == '__main__':
    args = parse_args()
    sys.exit(main(args))