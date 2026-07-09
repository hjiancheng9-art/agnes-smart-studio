def scan_comfyui_environment(comfyui_path: str | Path) -> ComfyUIEnvironment:
    """
    离线扫描 ComfyUI 环境。

    参数：
      comfyui_path:
        ComfyUI 根目录，例如：
        C:/Users/xxx/ComfyUI
        D:/AI/ComfyUI

    返回：
      ComfyUIEnvironment
        - custom_node_packages: 已安装 custom_nodes 包
        - possible_custom_class_types: 从源码静态解析出的疑似 NODE_CLASS_MAPPINGS key
        - models: checkpoints / loras / vae / controlnet 等模型文件
        - summary: 统计信息
        - warnings: 缺失目录 / 异常说明
    """

    root = Path(comfyui_path).expanduser().resolve()
    custom_nodes_dir = root / "custom_nodes"
    models_dir = root / "models"

    warnings: List[str] = []

    if not root.exists():
        warnings.append(f"ComfyUI root not found: {root}")

    if not custom_nodes_dir.exists():
        warnings.append(f"custom_nodes directory not found: {custom_nodes_dir}")

    if not models_dir.exists():
        warnings.append(f"models directory not found: {models_dir}")

    custom_node_packages = _scan_custom_node_packages(custom_nodes_dir, warnings)
    possible_class_types = sorted({
        class_type
        for pkg in custom_node_packages
        for class_type in pkg.possible_class_types
    })

    models = _scan_models(models_dir, warnings)

    summary = {
        "os": platform.system(),
        "python": platform.python_version(),
        "custom_node_package_count": len(custom_node_packages),
        "possible_custom_class_type_count": len(possible_class_types),
        "model_counts": {
            category: len(files)
            for category, files in models.items()
        },
        "has_checkpoints": len(models.get("checkpoints", [])) > 0,
        "has_loras": len(models.get("loras", [])) > 0,
        "has_vae": len(models.get("vae", [])) > 0,
        "has_controlnet": len(models.get("controlnet", [])) > 0,
        "has_upscale_models": len(models.get("upscale_models", [])) > 0,
        "has_sdxl_candidate": _has_keyword_model(
            models.get("checkpoints", []),
            ["sdxl", "sd_xl", "xl", "juggernautxl", "realvisxl"],
        ),
        "has_sd15_candidate": _has_keyword_model(
            models.get("checkpoints", []),
            ["sd15", "sd1.5", "v1-5", "1.5", "anything", "revanimated"],
        ),
    }

    return ComfyUIEnvironment(
        comfyui_path=str(root),
        exists=root.exists(),
        custom_nodes_path=str(custom_nodes_dir),
        models_path=str(models_dir),
        custom_node_packages=custom_node_packages,
        possible_custom_class_types=possible_class_types,
        models=models,
        summary=summary,
        warnings=warnings,
    )


def _scan_custom_node_packages(
    custom_nodes_dir: Path,
    warnings: List[str],
) -> List[CustomNodePackage]:
    if not custom_nodes_dir.exists():
        return []

    packages: List[CustomNodePackage] = []

    for item in sorted(custom_nodes_dir.iterdir(), key=lambda p: p.name.lower()):
        if item.name.startswith("."):
            continue

        if item.is_dir():
            pkg = _scan_custom_node_dir(item, warnings)
            packages.append(pkg)

        elif item.is_file() and item.suffix.lower() == ".py":
            # custom_nodes 下也可能直接放单文件节点
            class_types = _extract_node_class_mappings_from_file(item)
            packages.append(CustomNodePackage(
                name=item.stem,
                path=str(item),
                has_init=False,
                has_requirements=False,
                has_pyproject=False,
                possible_class_types=class_types,
            ))

    return packages


def _scan_custom_node_dir(
    node_dir: Path,
    warnings: List[str],
) -> CustomNodePackage:
    py_files = list(node_dir.rglob("*.py"))

    possible_class_types: List[str] = []
    for py_file in py_files:
        # 跳过过大的文件，避免扫描很慢
        try:
            if py_file.stat().st_size > 2_000_000:
                continue
        except OSError:
            continue

        try:
            possible_class_types.extend(_extract_node_class_mappings_from_file(py_file))
        except Exception as e:
            warnings.append(f"Failed to parse custom node file {py_file}: {e}")

    possible_class_types = sorted(set(possible_class_types))

    return CustomNodePackage(
        name=node_dir.name,
        path=str(node_dir),
        has_init=(node_dir / "__init__.py").exists(),
        has_requirements=(node_dir / "requirements.txt").exists(),
        has_pyproject=(node_dir / "pyproject.toml").exists(),
        possible_class_types=possible_class_types,
    )


def _extract_node_class_mappings_from_file(py_file: Path) -> List[str]:
    """
    静态解析 custom node 文件中的 NODE_CLASS_MAPPINGS。

    支持常见写法：
      NODE_CLASS_MAPPINGS = {
          "MyNode": MyNode,
          "AnotherNode": AnotherNode,
      }

    不执行 Python 文件，避免 import 副作用。
    动态构建的 mappings 可能解析不到，这是正常的。
    """
    text = py_file.read_text(encoding="utf-8", errors="ignore")

    result: List[str] = []

    # 方法 1：AST 解析字面量 dict 的 key
    try:
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "NODE_CLASS_MAPPINGS":
                        if isinstance(node.value, ast.Dict):
                            for key in node.value.keys:
                                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                                    result.append(key.value)
                                elif isinstance(key, ast.Str):
                                    result.append(key.s)
    except SyntaxError:
        pass

    # 方法 2：regex 兜底，抓 NODE_CLASS_MAPPINGS 附近的字符串 key
    if not result and "NODE_CLASS_MAPPINGS" in text:
        match = re.search(
            r"NODE_CLASS_MAPPINGS\s*=\s*\{(?P<body>.*?)\n\}",
            text,
            flags=re.S,
        )
        if match:
            body = match.group("body")
            result.extend(re.findall(r"""["']([^"']+)["']\s*:""", body))

    return sorted(set(result))


def _scan_models(
    models_dir: Path,
    warnings: List[str],
) -> Dict[str, List[ModelFile]]:
    models: Dict[str, List[ModelFile]] = {
        category: []
        for category in MODEL_DIR_ALIASES.keys()
    }

    if not models_dir.exists():
        return models

    for category, aliases in MODEL_DIR_ALIASES.items():
        files: List[ModelFile] = []

        for alias in aliases:
            model_subdir = models_dir / alias
            if not model_subdir.exists():
                continue

            files.extend(_scan_model_files(model_subdir, models_dir, warnings))

        models[category] = sorted(
            files,
            key=lambda f: f.relative_path.lower(),
        )

    # 额外扫描 models 根目录下散落的模型
    root_files = []
    for file in models_dir.iterdir():
        if file.is_file() and file.suffix.lower() in MODEL_EXTENSIONS:
            root_files.append(_to_model_file(file, models_dir))

    if root_files:
        models["_root"] = sorted(root_files, key=lambda f: f.relative_path.lower())

    return models


def _scan_model_files(
    directory: Path,
    models_root: Path,
    warnings: List[str],
) -> List[ModelFile]:
    result: List[ModelFile] = []

    try:
        for file in directory.rglob("*"):
            if not file.is_file():
                continue

            if file.suffix.lower() not in MODEL_EXTENSIONS:
                continue

            result.append(_to_model_file(file, models_root))

    except Exception as e:
        warnings.append(f"Failed to scan model directory {directory}: {e}")

    return result


def _to_model_file(file: Path, models_root: Path) -> ModelFile:
    try:
        size_gb = round(file.stat().st_size / 1024**3, 3)
    except OSError:
        size_gb = 0.0

    try:
        rel = file.relative_to(models_root)
    except ValueError:
        rel = file.name

    return ModelFile(
        name=file.name,
        relative_path=str(rel).replace("\\", "/"),
        absolute_path=str(file),
        size_gb=size_gb,
        extension=file.suffix.lower(),
    )


def _has_keyword_model(files: List[ModelFile], keywords: List[str]) -> bool:
    for f in files:
        name = f.name.lower()
        rel = f.relative_path.lower()
        if any(k.lower() in name or k.lower() in rel for k in keywords):
            return True
    return False


def environment_to_jsonable(env: ComfyUIEnvironment) -> Dict[str, Any]:
    return {
        "comfyui_path": env.comfyui_path,
        "exists": env.exists,
        "custom_nodes_path": env.custom_nodes_path,
        "models_path": env.models_path,
        "custom_node_packages": [
            asdict(pkg)
            for pkg in env.custom_node_packages
        ],
        "possible_custom_class_types": env.possible_custom_class_types,
        "models": {
            category: [asdict(model) for model in files]
            for category, files in env.models.items()
        },
        "summary": env.summary,
        "warnings": env.warnings,
    }


def save_environment_report(env: ComfyUIEnvironment, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.write_text(
        json.dumps(environment_to_jsonable(env), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

