import hashlib
import json
from collections.abc import Callable
from os import PathLike
from pathlib import Path
from tempfile import NamedTemporaryFile
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

        self._check_for_new_hashes: bool = True
        self._all_hashes: list[str] = []

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

        self._check_for_new_hashes = True

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

    def set_description(self, config_hash: str, description: str) -> None:
        """
        Set or update the description for a specific configuration.

        Parameters
        ----------
        config_hash
            The hash of the configuration to update.
        description
            The description to set for the configuration.

        Raises
        ------
        FileNotFoundError
            If no configuration file with the given hash exists.
        ValueError
            If the description contains invalid characters.
        OSError
            If there is an error reading or writing the descriptions file.
        """

        if not self.exists(config_hash):
            raise FileNotFoundError(f"No configuration found with hash {config_hash}.")

        banned_chars = {":", "\n"}
        if any(char in description for char in banned_chars):
            raise ValueError(f"Description cannot contain the following characters: {banned_chars}")

        descriptions: dict[str, str] = {}

        hash_desc_file = self._storage_dir / "descriptions.txt"
        if hash_desc_file.exists():
            try:
                with hash_desc_file.open(mode="r", encoding="utf-8") as f:
                    for line in f:
                        hash_key, desc = line.rstrip("\n").split(":", 1)
                        descriptions[hash_key] = desc

            except Exception as e:
                raise OSError("Failed to read existing descriptions.") from e

        descriptions[config_hash] = description
        descriptions_items = sorted(descriptions.items())

        tmp_path: Path | None = None
        try:
            with NamedTemporaryFile(mode="w", dir=self._storage_dir, delete=False, encoding="utf-8") as tmp_file:
                tmp_path = Path(tmp_file.name)
                for hash_key, desc in descriptions_items:
                    tmp_file.write(f"{hash_key}:{desc}\n")

                tmp_file.flush()

            tmp_path.replace(hash_desc_file)

        except Exception as e:
            if tmp_path and tmp_path.exists():
                tmp_path.unlink()

            raise OSError("Failed to write descriptions.") from e

    def get_description(self, config_hash: str) -> str:
        """
        Retrieve the description for a specific configuration.

        Parameters
        ----------
        config_hash
            The hash of the configuration to retrieve the description for.

        Returns
        -------
        str
            The description of the configuration, or None if not found.

        Raises
        ------
        FileNotFoundError
            If no configuration file with the given hash exists.
        OSError
            If there is an error reading the descriptions file.
        """

        hash_desc_file = self._storage_dir / "descriptions.txt"
        if not hash_desc_file.exists():
            hash_desc_file.touch()

        if not self.exists(config_hash):
            raise FileNotFoundError(f"No configuration found with hash {config_hash}.")

        try:
            with hash_desc_file.open(mode="r", encoding="utf-8") as f:
                for line in f:
                    hash_key, desc = line.rstrip("\n").split(":", 1)
                    if hash_key == config_hash:
                        return desc

        except Exception as e:
            raise OSError("Failed to read descriptions file.") from e

    def get_all_hashes(self) -> list[str]:
        """
        Retrieve all configuration hashes stored in the storage directory.

        Returns
        -------
        list[str]
            A list of all configuration hashes.
        """

        if self._check_for_new_hashes:
            self._all_hashes = [file.stem for file in self._storage_dir.glob("*.json")]
            self._check_for_new_hashes = False

        return self._all_hashes

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
