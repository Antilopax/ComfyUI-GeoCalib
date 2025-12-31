import torch
import numpy as np

# Try to import GeoCalib; handle the error if it's not installed
try:
    from geocalib import GeoCalib
    from geocalib.utils import rad2deg
    GEOCALIB_AVAILABLE = True
except ImportError:
    GEOCALIB_AVAILABLE = False
    print("⚠️ GeoCalib node warning: 'geocalib' module not found. Please install it: pip install git+https://github.com/cvg/GeoCalib")

# Cache models to avoid reloading them on every execution
_MODELS = {}

class GeoCalibNode:
    """
    ComfyUI Node to extract Roll, Pitch, and vFoV using GeoCalib.
    """
    
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "weights": (["pinhole", "distorted"], {"default": "pinhole"}),
                "camera_model": (["pinhole", "simple_radial", "simple_divisional"], {"default": "pinhole"}),
            },
        }

    RETURN_TYPES = ("FLOAT", "FLOAT", "FLOAT")
    RETURN_NAMES = ("roll", "pitch", "vfov")
    FUNCTION = "analyze_image"
    CATEGORY = "GeoCalib"

    def analyze_image(self, image, weights, camera_model):
        if not GEOCALIB_AVAILABLE:
            raise ImportError("GeoCalib library not found. Please install it using: pip install git+https://github.com/cvg/GeoCalib")

        device = "cuda" if torch.cuda.is_available() else "cpu"

        # Load the model if not already loaded
        if weights not in _MODELS:
            print(f"Loading GeoCalib model (weights='{weights}')...")
            # This will download weights on the first run
            _MODELS[weights] = GeoCalib(weights=weights).to(device)
        
        model = _MODELS[weights]
        
        # Prepare outputs
        rolls = []
        pitches = []
        vfovs = []

        # Process batch (ComfyUI passes images as [B, H, W, C])
        for i in range(image.shape[0]):
            # Convert to [C, H, W] and send to device
            img_tensor = image[i].permute(2, 0, 1).to(device)
            
            with torch.inference_mode():
                # Run calibration
                results = model.calibrate(img_tensor, camera_model=camera_model)
            
            camera = results["camera"]
            gravity = results["gravity"]

            # Extract vFoV (Vertical Field of View)
            # GeoCalib returns vfov in radians, convert to degrees
            vfov_deg = rad2deg(camera.vfov).item()
            
            # Extract Roll and Pitch
            # gravity.rp contains roll and pitch in radians
            rp_deg = rad2deg(gravity.rp) # Tensor shape usually [2]
            
            # Ensure we get scalar values
            if rp_deg.numel() == 2:
                roll_deg, pitch_deg = rp_deg.unbind(-1)
                roll_val = roll_deg.item()
                pitch_val = pitch_deg.item()
            else:
                # Fallback if shape is unexpected
                roll_val = rp_deg[0].item()
                pitch_val = rp_deg[1].item()

            rolls.append(roll_val)
            pitches.append(pitch_val)
            vfovs.append(vfov_deg)

        # If processing a single image, return single floats.
        # If batch > 1, ComfyUI handles lists if the receiving node supports it, 
        # or you can use a "Get Item" node. 
        if len(rolls) == 1:
            return (rolls[0], pitches[0], vfovs[0])
        else:
            return (rolls, pitches, vfovs)

# Mapping for ComfyUI to recognize the node
NODE_CLASS_MAPPINGS = {
    "GeoCalibNode": GeoCalibNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "GeoCalibNode": "GeoCalib Estimator"
}