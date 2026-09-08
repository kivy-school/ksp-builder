


like in 
* .venv/lib/python3.13/site-packages/compilekv/cli.py

we need to implement compilekv in ksp-builder to process all kv files (and ofc the .py which is paired with them)
and ofc only if compile_kv is true

```toml
[tool.ksp-builder]
cythonize = true
py_to_pyx = true

# kv files
compile_kv = true
# if all 3 are true then save compiled kv as .pyx instead directly in the .cy_src part
```

also instead of .cy_src when cythonize lets call it .dist_src so it general for both when cythonize and compilekv mode.

