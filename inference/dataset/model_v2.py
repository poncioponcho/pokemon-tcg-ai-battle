"""Model v2: large teacher (GPU training) + small student (CPU/numpy inference).

Design contract
---------------
- Teacher: deep residual MLP with LayerNorm/GELU/Dropout. Trained on Kaggle GPU
  with BC -> AWR. Capacity is regularized by dropout + weight decay + early stop
  because the dataset is only ~846K decisions.
- Student: plain Linear+ReLU MLP (no LayerNorm) so the forward pass can be
  reproduced exactly in pure numpy inside the Kaggle submission (main.py),
  where torch is unavailable. Distilled from the frozen teacher.
- Both models consume the SAME feature layout as train_bc.Policy:
    st: (B, 11*CARD_DIM) uint8-ish card counts, normalized by DIV at forward time
    sc: (B, 90) scalars
    opts: (B, K, O_DIM) per-option features
    mask: (B, K) 1/0 valid-option mask
  and output (B, K) logits with invalid options set to -inf.
"""
from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

NEG_INF = float('-inf')


class ResBlock(nn.Module):
    def __init__(self, dim: int, dropout: float):
        super().__init__()
        self.net = nn.Sequential(
            nn.LayerNorm(dim),
            nn.Linear(dim, dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(dim, dim),
        )

    def forward(self, x):
        return x + self.net(x)


class PolicyTeacher(nn.Module):
    """Large policy used only during training (never shipped to the submission)."""

    def __init__(self, st_dim: int, sc_dim: int, o_dim: int, k: int = 64,
                 hidden: int = 1024, out: int = 512, opt_emb: int = 128,
                 blocks: int = 2, dropout: float = 0.10, div: torch.Tensor = None):
        super().__init__()
        self.k = k
        self.register_buffer('div', div if div is not None else torch.ones(st_dim))
        self.stem = nn.Sequential(nn.Linear(st_dim + sc_dim, hidden), nn.GELU())
        self.blocks = nn.Sequential(*[ResBlock(hidden, dropout) for _ in range(blocks)])
        self.to_out = nn.Sequential(nn.LayerNorm(hidden), nn.Linear(hidden, out), nn.GELU())
        self.opt_proj = nn.Sequential(nn.Linear(o_dim, opt_emb), nn.GELU())
        self.head = nn.Sequential(
            nn.Linear(out + opt_emb, 256), nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128), nn.GELU(),
            nn.Linear(128, 1),
        )

    def forward(self, st, sc, opts, mask):
        x = torch.cat([st / self.div, sc], 1)
        e = self.to_out(self.blocks(self.stem(x)))          # (B, out)
        oe = self.opt_proj(opts)                             # (B, K, opt_emb)
        be = e.unsqueeze(1).expand(-1, self.k, -1)
        h = self.head(torch.cat([be, oe], 2)).squeeze(2)     # (B, K)
        return h.masked_fill(mask == 0, NEG_INF)


class PolicyStudent(nn.Module):
    """Small Linear+ReLU policy. Mirrors must be reproducible in numpy.

    Keep layers in fixed order so export_student.py can map weights by index:
      enc = [Linear, ReLU, Linear, ReLU, Linear, ReLU]
      head = [Linear, ReLU, Linear]
    """

    def __init__(self, st_dim: int, sc_dim: int, o_dim: int, k: int = 64,
                 hidden: int = 384, out: int = 192, div: torch.Tensor = None):
        super().__init__()
        self.k = k
        self.register_buffer('div', div if div is not None else torch.ones(st_dim))
        self.enc = nn.Sequential(
            nn.Linear(st_dim + sc_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, out), nn.ReLU(),
        )
        self.head = nn.Sequential(
            nn.Linear(out + o_dim, 192), nn.ReLU(),
            nn.Linear(192, 1),
        )

    def forward(self, st, sc, opts, mask):
        x = torch.cat([st / self.div, sc], 1)
        e = self.enc(x)                                      # (B, out)
        be = e.unsqueeze(1).expand(-1, self.k, -1)
        h = self.head(torch.cat([be, opts], 2)).squeeze(2)   # (B, K)
        return h.masked_fill(mask == 0, NEG_INF)


def ce_per_sample(logits, labels, mask):
    """Per-sample multi-label CE, mirrors train_bc.ce_loss without reduction."""
    logp = F.log_softmax(logits, 1)
    safe = logp.clone()
    safe[mask == 0] = 0
    sel = labels * mask
    cnt = sel.sum(1).clamp(min=1).float()
    return -(sel * safe).sum(1) / cnt


def distill_per_sample_loss(student_logits, teacher_logits, labels, mask,
                            temperature=3.0, alpha=0.3):
    """alpha * hard CE + (1-alpha) * T^2 * KL(teacher || student), per sample.

    NOTE: masked options must be zeroed BEFORE the product. At mask==0 positions
    student logits are -inf (-> log_softmax -inf) while teacher softmax prob is
    exactly 0, so `p_t * logp_s` would be 0 * -inf = NaN and poison the whole
    batch mean. Zeroing logp_s first keeps masked rows clean.
    """
    hard = ce_per_sample(student_logits, labels, mask)
    s = student_logits / temperature
    t = teacher_logits / temperature
    logp_s = F.log_softmax(s, 1)
    p_t = F.softmax(t, 1)
    logp_s = logp_s.clone()
    logp_s[mask == 0] = 0.0
    soft = -(p_t * logp_s).sum(1) * (temperature * temperature)
    return alpha * hard + (1.0 - alpha) * soft


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)
