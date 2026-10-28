"""Mixed precision that also runs on GPUs without bfloat16 (Kaggle T4 and P100).

bf16 where the GPU supports it (local RTX cards: unchanged behaviour), otherwise fp16 with
gradient scaling; fp32 on the CPU.
"""

import torch


def amp_dtype(device: torch.device) -> torch.dtype | None:
    if device.type != "cuda":
        return None
    return torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16


class Amp:
    def __init__(self, device: torch.device):
        self.device = device
        self.dtype = amp_dtype(device)
        self.scaler = torch.amp.GradScaler("cuda", enabled=self.dtype == torch.float16)

    def autocast(self, enabled: bool = True):
        return torch.autocast(
            self.device.type,
            dtype=self.dtype or torch.float32,
            enabled=enabled and self.dtype is not None,
        )

    def step(self, loss, model, optimizer, max_norm: float = 1.0) -> None:
        """Backward, clip and optimizer step; the scaler is a no-op outside fp16."""
        self.scaler.scale(loss).backward()
        self.scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm)
        self.scaler.step(optimizer)
        self.scaler.update()
