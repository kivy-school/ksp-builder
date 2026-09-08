we need to implement both the pre and post build part of ksp_builder/_pre_post_build.py into the ksp-builder where it reads key from 
pyproject.toml

```toml
[tool.ksp-builder]
before_build = "path/to/before_build_script.py"
after_build = "path/to/after_build_script.py"
```

and if any of them is present is should execute them.. 