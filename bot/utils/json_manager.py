import json
import os
from typing import Dict, List


class JsonManager:
    @staticmethod
    def save_to_json(path: str, data: dict) -> None:
        existing_data = JsonManager.load_from_json(path)
        if not existing_data:
            existing_data = []
        new_data = existing_data.append(data)
        try:
            with open(path, "w") as f:
                json.dump(new_data, f, indent=4)
        except Exception as error:
            raise Exception(
                f"Unable to save json file: {path} | {error or 'Unknown error'}"
            )

    @staticmethod
    def load_from_json(path: str) -> List[Dict[str, str]]:
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r") as f:
                return json.load(f)
        except json.decoder.JSONDecodeError:
            raise Exception(f"Unable to parse json file: {path}")
        except Exception as error:
            raise Exception(
                f"Unable to load json file: {path} | {error or 'Unknown error'}"
            )
