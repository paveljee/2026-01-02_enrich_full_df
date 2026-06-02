import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.helpers.data_models import (
    FragmentType,
    RegisteredResource,
    ResourceGroup,
    SourceKey,
)


class TestEnums:
    """Test suite for enum types."""
    
    def test_resource_group_values(self):
        """Test ResourceGroup enum has expected values."""
        assert ResourceGroup.SCISCINET_HF == "sciscinet_hf"
        assert ResourceGroup.LLAMA_CPP == "llama_cpp"
        assert ResourceGroup.KTP_PIPELINE_ARTIFACT == "ktp_pipeline_artifact"
        assert len(list(ResourceGroup)) == 6
    
    def test_fragment_type_values(self):
        """Test FragmentType enum has expected values."""
        assert FragmentType.AUTHOR_ID == "author_id"
        assert FragmentType.EXCEL_ROW == "excel_row"
        assert len(list(FragmentType)) == 8


class TestRegisteredResource:
    """Test suite for RegisteredResource model."""
    
    @pytest.fixture
    def valid_resource_data(self):
        return {
            "name": "test.parquet",
            "hash": "abc123",
            "group": ResourceGroup.SCISCINET_HF,
            "fragment_type": FragmentType.AUTHOR_ID,
            "url": "file:///data/test.parquet"
        }
    
    def test_create_minimal(self):
        """Test creating resource with only required fields."""
        resource = RegisteredResource(
            name="test.csv",
            hash="hash123",
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            verify_hash_on_init=False,
        )
        assert resource.url is None
        assert resource.description is None
    
    def test_url_validation_rejects_empty(self):
        """Test URL validation rejects empty/whitespace strings."""
        with pytest.raises(ValidationError, match="Input should be a valid URL"):
            RegisteredResource(
                name="test.csv", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
                fragment_type=FragmentType.CSV_ROW, url=""
            )
    
    def test_url_accepts_various_protocols(self):
        """Test URL accepts file://, https://, http:// protocols."""
        for url in ["file:///path/file", "https://example.com/file", "http://example.com/file"]:
            resource = RegisteredResource(
                name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
                fragment_type=FragmentType.CSV_ROW, url=url, verify_hash_on_init=False
            )
            assert resource.url is not None
    
    @pytest.mark.parametrize("url,expected_path", [
        ("file:///home/user/data.csv", "/home/user/data.csv"),
        ("file:///C:/Users/user/data.csv", "C:/Users/user/data.csv"),  # Windows
        ("file:///home/user/spaced%20file.csv", "/home/user/spaced file.csv"),  # URL-encoded
    ])
    def test_fspath_extracts_paths(self, url, expected_path):
        """Test __fspath__ correctly extracts filesystem paths."""
        resource = RegisteredResource(
            name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW, url=url, verify_hash_on_init=False
        )
        assert resource.__fspath__() == expected_path
    
    def test_fspath_raises_for_missing_url(self):
        """Test __fspath__ raises when URL is None."""
        resource = RegisteredResource(
            name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW, verify_hash_on_init=False
        )
        with pytest.raises(ValueError, match="has no URL"):
            resource.__fspath__()
    
    def test_fspath_raises_for_non_file_url(self):
        """Test __fspath__ raises for HTTP URLs."""
        resource = RegisteredResource(
            name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url="https://example.com/data.csv",
            verify_hash_on_init=False,
        )
        with pytest.raises(ValueError, match="not a file path"):
            resource.__fspath__()
    
    def test_pathlib_integration(self):
        """Test that __fspath__ works with pathlib.Path."""
        resource = RegisteredResource(
            name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url="file:///data/test.csv",
            verify_hash_on_init=False,
        )
        path = Path(resource)
        assert isinstance(path, Path)
        assert str(path) == "/data/test.csv"


class TestSourceKey:
    """Test suite for SourceKey model."""
    
    @pytest.fixture
    def sample_resource(self):
        return RegisteredResource(
            name="authors.parquet",
            hash="abc123",
            group=ResourceGroup.SCISCINET_HF,
            fragment_type=FragmentType.AUTHOR_ID,
            url="file:///data/authors.parquet",
            verify_hash_on_init=False,
        )
    
    def test_fragment_has_type_mixin(self, sample_resource):
        """Test fragment string has .type attribute mixed in."""
        sk = SourceKey(resource=sample_resource, fragment="A12345")
        assert sk.fragment == "A12345"  # Works as string
        assert sk.fragment.type == FragmentType.AUTHOR_ID  # Has type attribute
        assert len(sk.fragment) == 6  # String methods work
    
    def test_to_string_key(self, sample_resource):
        """Test serialization to string key."""
        sk = SourceKey(resource=sample_resource, fragment="A12345")
        assert sk.to_string_key() == "authors.parquet#author_id:A12345"
    
    def test_from_string_key_roundtrip(self, sample_resource):
        """Test serialization roundtrip."""
        original = SourceKey(resource=sample_resource, fragment="A99999")
        key_str = original.to_string_key()
        restored = SourceKey.from_string_key(key_str, sample_resource)
        assert restored.fragment == original.fragment
        assert restored.fragment.type == original.fragment.type
    
    def test_from_string_key_validation_errors(self, sample_resource):
        """Test from_string_key raises on invalid formats."""
        with pytest.raises(ValueError, match="Invalid source key format"):
            SourceKey.from_string_key("no_hash_separator", sample_resource)
        
        with pytest.raises(ValueError, match="Invalid fragment format"):
            SourceKey.from_string_key("file#no_colon", sample_resource)
    
    def test_from_string_key_fragment_type_mismatch(self, sample_resource):
        """Test from_string_key raises when fragment type doesn't match resource."""
        # sample_resource has AUTHOR_ID, but key has PAPER_ID
        with pytest.raises(ValueError, match="doesn't match"):
            SourceKey.from_string_key("authors.parquet#paper_id:P123", sample_resource)


class TestRegisteredResourceEnhanced:
    """Tests for hash verification and cross-platform paths."""
    
    def test_url_with_fragment_rejected(self):
        """Test URLs with fragments (#) are rejected."""
        with pytest.raises(ValidationError, match="URLs with fragments are not supported"):
            RegisteredResource(
                name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
                fragment_type=FragmentType.CSV_ROW,
                url="file:///data/file.csv#section",
                verify_hash_on_init=False
            )
    
    def test_url_with_query_string_accepted(self):
        """Test URLs with query strings (?) are accepted."""
        resource = RegisteredResource(
            name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url="https://example.com/data.csv?version=1",
            verify_hash_on_init=False
        )
        assert resource.url is not None
    
    def test_windows_path_handling(self):
        """Test Windows file paths are handled correctly."""
        resource = RegisteredResource(
            name="test", hash="h", group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url="file:///C:/Users/test/data.csv",
            verify_hash_on_init=False
        )
        path = resource.__fspath__()
        assert path == "C:/Users/test/data.csv"
        # Verify Path works
        assert Path(path).parts[0] == "C:"
    
    def test_hash_verification_on_init(self, tmp_path):
        """Test hash is verified on init when verify_hash_on_init=True."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        # Compute correct hash
        correct_hash = hashlib.sha256(b"test content").hexdigest()
        
        # Should succeed with correct hash
        resource = RegisteredResource(
            name="test.txt",
            hash=correct_hash,
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url=f"file:///{test_file}",
            verify_hash_on_init=True
        )
        assert resource is not None
        
        # Should fail with wrong hash
        with pytest.raises(ValidationError, match="Hash mismatch"):
            RegisteredResource(
                name="test.txt",
                hash="wrong_hash",
                group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
                fragment_type=FragmentType.CSV_ROW,
                url=f"file:///{test_file}",
                verify_hash_on_init=True
            )
    
    def test_skip_hash_verification(self, tmp_path):
        """Test hash verification can be skipped."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        
        # Should succeed even with wrong hash when verification disabled
        resource = RegisteredResource(
            name="test.txt",
            hash="any_string_works",
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url=f"file:///{test_file}",
            verify_hash_on_init=False
        )
        assert resource.hash == "any_string_works"
    
    def test_verify_hash_method(self, tmp_path):
        """Test manual hash verification with verify_hash() method."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")
        correct_hash = hashlib.sha256(b"test content").hexdigest()
        
        resource = RegisteredResource(
            name="test.txt",
            hash=correct_hash,
            group=ResourceGroup.KTP_MANUAL_EXTRACTIONS,
            fragment_type=FragmentType.CSV_ROW,
            url=f"file:///{test_file}",
            verify_hash_on_init=False
        )
        
        # Verify hash manually
        assert resource.verify_hash() is True
        
        # Change file content
        test_file.write_text("different content")
        
        # Verification should now fail
        with pytest.raises(ValueError, match="Hash verification failed"):
            resource.verify_hash()
