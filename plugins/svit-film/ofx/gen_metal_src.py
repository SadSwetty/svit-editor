#!/usr/bin/env python3
"""Збирає текст Metal-шейдерів (gpu_shared.h + metal_kernels.metal) у src/metal_src.inc як C++ raw string."""
import os
here = os.path.dirname(os.path.abspath(__file__))
shared = open(os.path.join(here, "src", "gpu_shared.h"), encoding="utf-8").read()
kern = open(os.path.join(here, "src", "metal_kernels.metal"), encoding="utf-8").read()
text = shared + "\n" + kern
assert ")SVITMSL" not in text
open(os.path.join(here, "src", "metal_src.inc"), "w", encoding="utf-8").write('R"SVITMSL(' + text + ')SVITMSL"\n')
print("metal_src.inc:", len(text), "chars")
