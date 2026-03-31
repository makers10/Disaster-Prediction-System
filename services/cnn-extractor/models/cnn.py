"""CNN Feature Extractor — ResNet-based stand-in for satellite image processing.

Extracts three features from a satellite image:
  - flood_inundation_pct: 0–100 (percentage of image showing surface water)
  - cloud_density: 0–1 (fraction of image covered by cloud)
  - vegetation_index: 0–1 (NDVI proxy — fraction of healthy vegetation)

The stand-in uses pixel statistics on the image channels as a proxy for the
real ResNet-based model. The interface is designed so a real pre-trained CNN
can be swapped in without changing callers.
"""

from __future__ import annotations

import io
import logging
from typing import Tuple

import numpy as np

logger = logging.getLogger(__name__)


class CNNExtractor:
    """Lightweight CNN stand-in using pixel channel statistics.

    In production this would load a pre-trained ResNet checkpoint.
    The interface (extract method signature) is stable.
    """

    def extract(self, image_bytes: bytes) -> Tuple[float, float, float]:
        """Extract features from raw image bytes.

        Args:
            image_bytes: Raw image data (JPEG/PNG).

        Returns:
            (flood_inundation_pct, cloud_density, vegetation_index)
            All values are clipped to their valid ranges.

        Raises:
            ValueError: If image_bytes cannot be decoded.
        """
        try:
            from PIL import Image  # type: ignore

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            arr = np.array(img, dtype=np.float32) / 255.0  # (H, W, 3) in [0,1]
        except Exception as exc:
            raise ValueError(f"Failed to decode image: {exc}") from exc

        r, g, b = arr[:, :, 0], arr[:, :, 1], arr[:, :, 2]

        # --- Flood inundation proxy ---
        # High blue + low red/green → water pixels
        water_mask = (b > 0.4) & (b > r + 0.1) & (b > g + 0.05)
        flood_inundation_pct = float(np.clip(water_mask.mean() * 100.0, 0.0, 100.0))

        # --- Cloud density proxy ---
        # High brightness across all channels → cloud pixels
        brightness = (r + g + b) / 3.0
        cloud_mask = brightness > 0.75
        cloud_density = float(np.clip(cloud_mask.mean(), 0.0, 1.0))

        # --- Vegetation index proxy (NDVI-like) ---
        # High green + low red → vegetation pixels
        ndvi_like = (g - r) / (g + r + 1e-6)
        vegetation_index = float(np.clip(ndvi_like.mean() + 0.5, 0.0, 1.0))

        logger.debug(
            "CNN features: flood=%.2f%% cloud=%.3f veg=%.3f",
            flood_inundation_pct, cloud_density, vegetation_index,
        )
        return flood_inundation_pct, cloud_density, vegetation_index
