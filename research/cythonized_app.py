from setuptools import setup, Extension, find_packages, Command
from Cython.Build import cythonize
from os.path import curdir, abspath,join, splitext, dirname, basename, split, relpath, exists
import os
from shutil import move, copy
from pathlib import Path

print("WORK_DIR",abspath(curdir))

root_dir = abspath(curdir)

src_path = build_path = dirname(__file__)

extentions = []

cy_src = join(root_dir, ".cy_src")

exts = []

for (root, dir, files) in os.walk(join(root_dir, "src")):
    
    rp = relpath(root, root_dir + "/src")

    if rp == "." and "main.py" in files:
        continue

    target_folder = join(cy_src, rp)
    if not exists(target_folder):
        os.makedirs(target_folder)
    
    cy_path = rp.replace("/", ".")
        
    for file in files:
        
        if file == "__init__.py":
            copy(join(root, file), join(target_folder, file))
        else:
            fn, ext = splitext(file)
            if ext != ".py": continue

            py = join(root, file)
            pyx = join(target_folder, f"{fn}.pyx")
            
            print(py,"->", pyx)
            copy(py, pyx)
            exts.append(
                Extension(f"{cy_path}.{fn}", [join(".cy_src",rp, f"{fn}.pyx")])
            )

setup(
    ext_modules=cythonize(exts)
)