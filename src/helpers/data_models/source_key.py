import hashlib
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import pandas as pd
import requests
from pydantic import AnyUrl, BaseModel, Field, field_validator, model_validator
from pydantic_core import core_schema


class ResourceGroup(str, Enum):
    """Enum identifying the provenance of registered resources.
    
    Members:
        HCR_LISTS_2024_ZIP: HCR Lists from 2024 ZIP archive
        REGISTERED_SAMPLES: Registered sample datasets
        LLAMA_CPP: LlamaCpp generated or processed resources
        SCISCINET_HF: SciSciNet datasets from HuggingFace
        KTP_PILOT_SAMPLE: KTP pilot sample data
    """
    
    HCR_LISTS_2024_ZIP = "hcr_lists_2024_zip"
    REGISTERED_SAMPLES = "registered_samples"
    LLAMA_CPP = "llama_cpp"
    SCISCINET_HF = "sciscinet_hf"
    KTP_PILOT_SAMPLE = "ktp_pilot_sample"


class FragmentType(str, Enum):
    """Enum identifying the type of fragment within a registered resource.
    
    Members:
        EXCEL_ROW: Row index in an Excel spreadsheet
        DRAW_NUMBER: Draw number identifier
        CHAT_ID: Chat conversation identifier
        AUTHOR_ID: Author unique identifier
        PAPER_ID: Paper unique identifier
        CSV_ROW: Row index in a CSV file
        PARQUET_ROW: Row index in a Parquet file
        DOCX_ROW: Row index in a DOCX table
    """
    
    EXCEL_ROW = "excel_row"
    DRAW_NUMBER = "draw_number"
    CHAT_ID = "chat_id"
    AUTHOR_ID = "author_id"
    PAPER_ID = "paper_id"
    CSV_ROW = "csv_row"
    PARQUET_ROW = "parquet_row"
    DOCX_ROW = "docx_row"


class RegisteredResource(BaseModel):
    """Represents a registered file or resource with integrity verification.
    
    Implements __fspath__ protocol, allowing it to be used directly with pathlib.Path(),
    open(), and other file operations when url is a file:/// URL.
    """
    
    name: str = Field(..., description="Resource name, e.g., 'somefile.docx'")
    hash: str = Field(..., description="SHA256 hash of file contents for integrity verification")
    group: ResourceGroup = Field(..., description="Provenance group this resource belongs to")
    fragment_type: FragmentType = Field(
        ..., description="Type of fragments contained in this resource")
    description: str | None = Field(None, description="Optional human-readable description")
    url: AnyUrl | None = Field(
        None, description="URL to resource (file:/// for local paths, https:// for remote)")
    verify_hash_on_init: bool = Field(
        default=True,
        description="If True, verify hash matches file content on initialization"
    )

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: AnyUrl | None) -> AnyUrl | None:
        """Validate URL is non-empty and has no fragment."""
        if v is None:
            return None
        
        url_str = str(v)
        if not url_str or url_str.isspace():
            raise ValueError("URL must be a valid non-empty URL")
        
        parsed = urlparse(url_str)
        
        # Reject URLs with fragments (e.g., file:///path/to/file#section)
        if parsed.fragment:
            raise ValueError(
                f"URLs with fragments are not supported. "
                f"Found fragment '{parsed.fragment}' in URL. "
                f"Please use a URL without the '#' fragment component."
            )
        
        return v
    
    @model_validator(mode='after')
    def verify_hash_if_requested(self) -> 'RegisteredResource':
        """Verify hash matches file content if verify_hash_on_init is True."""
        if self.verify_hash_on_init:
            if self.url is None:
                raise ValueError(
                    f"Could not verify hash for resource '{self.name}': URL is required"
                )
            try:
                actual_hash = self._compute_hash()
                if actual_hash != self.hash:
                    raise ValueError(
                        f"Hash mismatch for resource '{self.name}': "
                        f"expected {self.hash}, got {actual_hash}"
                    )
            except Exception as e:
                if isinstance(e, ValueError) and "Hash mismatch" in str(e):
                    raise
                raise ValueError(
                    f"Could not verify hash for resource '{self.name}': {e}"
                ) from e
        return self
    
    def _compute_hash(self, algorithm: Literal["sha256", "md5"] = "sha256") -> str:
        """Compute hash of file content.
        
        Args:
            algorithm: Hash algorithm to use (default: sha256)
            
        Returns:
            Hex digest of file hash
            
        Raises:
            ValueError: If file cannot be accessed or read
        """
        url_str = str(self.url)
        
        if url_str.startswith("file:///"):
            # Local file - read from filesystem
            try:
                path = Path(self.__fspath__())
                hasher = hashlib.new(algorithm)
                with open(path, 'rb') as f:
                    for chunk in iter(lambda: f.read(8192), b''):
                        hasher.update(chunk)
                return hasher.hexdigest()
            except Exception as e:
                raise ValueError(f"Could not read local file: {e}") from e
        
        elif url_str.startswith(("http://", "https://")):
            # Remote file - download and hash
            try:
                response = requests.get(url_str, stream=True)
                response.raise_for_status()
                hasher = hashlib.new(algorithm)
                for chunk in response.iter_content(chunk_size=8192):
                    hasher.update(chunk)
                return hasher.hexdigest()
            except Exception as e:
                raise ValueError(f"Could not download remote file: {e}") from e
        
        else:
            raise ValueError(f"Unsupported URL scheme for hashing: {url_str}")
    
    def verify_hash(self, algorithm: Literal["sha256", "md5"] = "sha256") -> bool:
        """Verify that stored hash matches file content.
        
        Args:
            algorithm: Hash algorithm to use (default: sha256)
            
        Returns:
            True if hash matches, raises ValueError if not
            
        Raises:
            ValueError: If hash doesn't match or file cannot be accessed
        """
        actual_hash = self._compute_hash(algorithm)
        if actual_hash != self.hash:
            raise ValueError(
                f"Hash verification failed for '{self.name}': "
                f"expected {self.hash}, got {actual_hash}"
            )
        return True
    
    def __fspath__(self) -> str:
        """Return filesystem path for use with pathlib and file operations.
        
        Raises:
            ValueError: If url is not a file:/// URL.
        """
        if self.url is None:
            raise ValueError(f"Resource '{self.name}' has no URL")

        url_str = str(self.url)
        if not url_str.startswith("file:///"):
            raise ValueError(
                f"Resource '{self.name}' URL is not a file path (got {url_str[:20]}...) - "
                f"cannot be used as a path"
            )
        
        parsed = urlparse(url_str)
        path_str = unquote(parsed.path)
        
        # Handle Windows paths: file:///C:/path -> C:/path (remove leading slash)
        if len(path_str) > 2 and path_str[0] == '/' and path_str[2] == ':':
            path_str = path_str[1:]  # Remove leading '/' for Windows
        
        return path_str


class Fragment(str):
    type: FragmentType | None = None  # programmatically set later

    def __new__(cls, value: str = ""):
        return super().__new__(cls, value)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: Any, _handler: Any) -> core_schema.CoreSchema:
        # Parse like a string, then wrap into Fragment
        return core_schema.no_info_after_validator_function(
            cls._validate,
            core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda v: str(v)
            ),
        )

    @classmethod
    def _validate(cls, v: str) -> "Fragment":
        return cls(v)


class SourceKey(BaseModel):
    """Uniquely identifies the source of a particular InnerDict.
    
    Replaces the dataset_id_field in InnerDict by providing both the resource
    context and the specific fragment within that resource.
    
    The fragment attribute is a string that also has a .type attribute mixed in,
    allowing access to the fragment type via source_key.fragment.type
    """
    
    resource: RegisteredResource = Field(
        ..., description="The registered resource containing this data")
    fragment: Fragment = Field(
        ..., description="The fragment identifier value (e.g., row number, author ID)")
    
    def model_post_init(self, __context: Any) -> None:
        # type is set programmatically here
        self.fragment.type = self.resource.fragment_type
    
    def to_string_key(self) -> str:
        """Generate a unique string representation for this source."""
        return f"{self.resource.name}#{self.resource.fragment_type.value}:{self.fragment}"
    
    @classmethod
    def from_string_key(cls, key: str, resource: RegisteredResource) -> "SourceKey":
        """Parse a string key back into a SourceKey (requires resource context).
        
        Format: "filename#fragment_type:fragment_id"
        """
        parts = key.split("#", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid source key format: {key}")
        
        fragment_parts = parts[1].split(":", 1)
        if len(fragment_parts) != 2:
            raise ValueError(f"Invalid fragment format in key: {key}")
        
        fragment_type_str, fragment_id = fragment_parts
        
        # Validate fragment type matches resource
        if FragmentType(fragment_type_str) != resource.fragment_type:
            raise ValueError(
                f"Fragment type '{fragment_type_str}' doesn't match "
                f"resource fragment type '{resource.fragment_type.value}'"
            )
        
        return cls(resource=resource, fragment=fragment_id)  # ok to init fragment with a str


# Usage examples:
if __name__ == "__main__":
    # Create a registered resource
    resource = RegisteredResource(
        name="authors.parquet",
        hash="abc123...",
        group=ResourceGroup.SCISCINET_HF,
        fragment_type=FragmentType.AUTHOR_ID,
        url="file:///path/to/authors.parquet"
    )

    # Use as path (thanks to __fspath__)
    df = pd.read_parquet(resource)
    Path(resource).exists()

    # Create a source key
    source_key = SourceKey(resource=resource, fragment="A12345")

    # Access fragment as string
    print(source_key.fragment)  # "A12345"
    print(len(source_key.fragment))  # 6

    # Access fragment type (mixed in!)
    print(source_key.fragment.type)  # FragmentType.AUTHOR_ID

    # Serialize
    key_str = source_key.to_string_key()  # "authors.parquet#author_id:A12345"

    # Deserialize
    restored = SourceKey.from_string_key(key_str, resource)
