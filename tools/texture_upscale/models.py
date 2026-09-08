"""Inference architectures for the pinned Real-ESRGAN checkpoints.

Adapted from Real-ESRGAN under BSD-3-Clause and BasicSR under Apache-2.0.
See MODEL_LICENSES.txt.
Training initialization and the external model registry are not needed here.
"""

import torch
from torch import nn
from torch.nn import functional as F


class SRVGGNetCompact(nn.Module):
    def __init__(self, num_conv: int):
        super().__init__()
        self.body = nn.ModuleList([nn.Conv2d(3, 64, 3, 1, 1), nn.PReLU(64)])
        for _ in range(num_conv):
            self.body.extend([nn.Conv2d(64, 64, 3, 1, 1), nn.PReLU(64)])
        self.body.append(nn.Conv2d(64, 48, 3, 1, 1))
        self.upsampler = nn.PixelShuffle(4)

    def forward(self, x):
        out = x
        for layer in self.body:
            out = layer(out)
        return self.upsampler(out) + F.interpolate(x, scale_factor=4, mode="nearest")


class ResidualDenseBlock(nn.Module):
    def __init__(self):
        super().__init__()
        for index in range(1, 6):
            setattr(
                self,
                f"conv{index}",
                nn.Conv2d(64 + 32 * (index - 1), 64 if index == 5 else 32, 3, 1, 1),
            )
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        outputs = [x]
        for index in range(1, 5):
            outputs.append(
                self.lrelu(getattr(self, f"conv{index}")(torch.cat(outputs, 1)))
            )
        return self.conv5(torch.cat(outputs, 1)) * 0.2 + x


class RRDB(nn.Module):
    def __init__(self):
        super().__init__()
        self.rdb1 = ResidualDenseBlock()
        self.rdb2 = ResidualDenseBlock()
        self.rdb3 = ResidualDenseBlock()

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv_first = nn.Conv2d(3, 64, 3, 1, 1)
        self.body = nn.Sequential(*(RRDB() for _ in range(23)))
        self.conv_body = nn.Conv2d(64, 64, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(64, 64, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(64, 64, 3, 1, 1)
        self.conv_hr = nn.Conv2d(64, 64, 3, 1, 1)
        self.conv_last = nn.Conv2d(64, 3, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(negative_slope=0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(
            self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest"))
        )
        feat = self.lrelu(
            self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest"))
        )
        return self.conv_last(self.lrelu(self.conv_hr(feat)))
