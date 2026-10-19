"""Reads the existing CostPilot model YAML; does not define a second config scheme."""

from pathlib import Path
from typing import Any

import yaml


def load_model_config(path: str) -> tuple[dict[str, str], dict[str, str]]:
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise FileNotFoundError(f"Model configuration not found: {config_path}")

    with config_path.open(encoding="utf-8") as stream:
        raw: Any = yaml.safe_load(stream)
    if not isinstance(raw, dict):
        raise ValueError("Model configuration must be a YAML mapping.")

    selections: list[dict[str, str]] = []
    for section in ("embedding", "reranking"):
        models = raw.get(section)
        if not isinstance(models, dict) or len(models) != 1:
            raise ValueError(
                f"For this demo, {section!r} must contain exactly one model."
            )
        model = next(iter(models.values()))
        if not isinstance(model, dict) or any(
            not isinstance(model.get(key), str) or not model[key].strip()
            for key in ("name", "version", "path")
        ):
            raise ValueError(f"Model in {section!r} needs name/version/path.")
        selections.append({key: model[key] for key in ("name", "version", "path")})

    return selections[0], selections[1]
