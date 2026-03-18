# Model Weight Storage

Use this directory to store large model weight files needed for symbol detection or other ML components. Keep the following guidelines in mind:

- Place raw checkpoints inside dedicated subfolders such as `weights/` or `checkpoints/`.
- Do **not** commit binary artifacts (ONNX, PyTorch, TensorFlow, ZIP archives). They are ignored via `.gitignore`.
- Document the source, version, and expected hash for each weight file in this README or a sibling note.
- Provide lightweight configuration files or scripts that know how to download weights if reproducibility is required.
