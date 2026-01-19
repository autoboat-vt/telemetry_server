import hashlib
import json
from collections.abc import Callable
from os import PathLike
from pathlib import Path
from typing import TypeVar

from autoboat_telemetry_server.types import AutopilotParametersType

T = TypeVar("T")


class AutopilotConfigManager:
    """
    Manages storage and retrieval of autopilot parameter configurations.

    Parameters
    ----------
    storage_dir
        Path to the directory where config files will be stored.
    """

    @staticmethod
    def compute_hash(config: AutopilotParametersType) -> str:
        """
        Compute a SHA-256 hash of the config with sorted keys to ensure consistent hashing regardless of dictionary ordering.

        Parameters
        ----------
        config
            The autopilot parameters configuration to hash.

        Returns
        -------
        str
            The SHA-256 hash of the configuration as a string.
        """

        config_json = json.dumps(config, sort_keys=True, separators=(",", ":"))
        hash_obj = hashlib.sha256(config_json.encode(encoding="utf-8"))
        return hash_obj.hexdigest()

    def __init__(self, storage_dir: PathLike[str]) -> None:
        """
        Parameters
        ----------
        storage_dir
            Path to the directory where config files will be stored.
        """

        self._storage_dir = Path(storage_dir)

    @property
    def storage_dir(self) -> Path:
        """
        Returns the storage directory path.

        Returns
        -------
        Path
            The directory where configuration files are stored.
        """

        return self._storage_dir

    def save(self, config: T, validate_function: Callable[[T], bool]) -> str:
        """
        Save a configuration to storage.

        If a configuration with the same content already exists, it will not be overwritten (content-addressable storage).

        Parameters
        ----------
        config
            The autopilot parameters configuration to save.
        validate_function
            A function to validate the configuration structure before saving.

        Raises
        ------
        TypeError
            If the config structure is invalid.
        FileExistsError
            If a configuration with the same hash already exists.

        Returns
        -------
        str
            The hash of the saved configuration.
        """

        if not validate_function(config):
            raise TypeError("Invalid configuration structure.")

        config_hash = AutopilotConfigManager.compute_hash(config)
        file_path = self._storage_dir / f"{config_hash}.json"

        if file_path.exists():
            raise FileExistsError(f"Configuration with hash {config_hash} already exists.")

        config_json = json.dumps(config, indent=4)
        file_path.write_text(config_json, encoding="utf-8")

        return config_hash

    def load(self, config_hash: str) -> AutopilotParametersType:
        """
        Load a configuration from storage by its hash.

        Parameters
        ----------
        config_hash
            The hash of the configuration to load.

        Raises
        ------
        FileNotFoundError
            If no configuration file with the given hash exists.
        ValueError
            If the configuration file content is invalid.

        Returns
        -------
        AutopilotParametersType
            The loaded autopilot parameters configuration.
        """

        file_path = self._storage_dir / f"{config_hash}.json"

        if not file_path.exists():
            raise FileNotFoundError(f"No configuration found with hash {config_hash}.")

        try:
            config_json = file_path.read_text(encoding="utf-8")
            config = json.loads(config_json)

        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError("Failed to decode configuration file content.") from e

        return config

    def get_all_hashes(self) -> list[str]:
        """
        Retrieve all configuration hashes stored in the storage directory.

        Returns
        -------
        list[str]
            A list of all configuration hashes.
        """

        config_hashes = []
        for file in self._storage_dir.glob("*.json"):
            config_hash = file.stem
            config_hashes.append(config_hash)

        return config_hashes

    def exists(self, config_hash: str) -> bool:
        """
        Check if a configuration with the given hash exists in storage.

        Parameters
        ----------
        config_hash
            The hash of the configuration to check.

        Returns
        -------
        bool
            True if the configuration file exists, False otherwise.
        """

        file_path = self._storage_dir / f"{config_hash}.json"
        return file_path.exists()
