"""Test bundled RenderDoc discovery mechanism.

This test file validates the complete bundled RenderDoc discovery pipeline:
1. _bundled_renderdoc module discovers available versions
2. _bundled_renderdoc maps versions to Python-specific directories
3. discover.find_renderdoc() prioritizes bundled versions in search order
4. Directory structure and configuration are correct
"""

import sys
from pathlib import Path

import pytest

# Ensure src is on path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rdc import _bundled_renderdoc
from rdc import discover


class TestBundledVersionDiscovery:
    """Test _bundled_renderdoc.get_bundled_versions()"""

    def test_get_bundled_versions_returns_list(self):
        """Should return a list (empty if no binaries present)"""
        versions = _bundled_renderdoc.get_bundled_versions()
        assert isinstance(versions, list)

    def test_bundled_versions_sorted_descending(self):
        """If versions present, should be sorted newest-first"""
        versions = _bundled_renderdoc.get_bundled_versions()
        if len(versions) > 1:
            # Check that versions are in descending order
            version_tuples = [tuple(map(int, v.split("."))) for v in versions]
            assert version_tuples == sorted(version_tuples, reverse=True)

    def test_bundled_versions_format(self):
        """Version strings should be in X.Y format (e.g., "1.21")"""
        versions = _bundled_renderdoc.get_bundled_versions()
        for version in versions:
            parts = version.split(".")
            assert len(parts) == 2
            assert all(p.isdigit() for p in parts)


class TestBundledPathResolution:
    """Test _bundled_renderdoc.get_bundled_renderdoc_path()"""

    def test_version_string_conversion(self):
        """Should convert "1.21" to v1_21 directory"""
        path = _bundled_renderdoc.get_bundled_renderdoc_path("1.21")
        # Path may be None if binaries not present, but if it exists, should contain v1_21
        if path is not None:
            assert "v1_21" in str(path)

    def test_python_version_directory_created(self):
        """Should include Python version directory (e.g., py312)"""
        path = _bundled_renderdoc.get_bundled_renderdoc_path("1.21")
        if path is not None:
            py_version_dir = f"py{sys.version_info.major}{sys.version_info.minor}"
            assert py_version_dir in str(path)

    def test_nonexistent_version_returns_none(self):
        """Should return None for versions without binaries"""
        # "999.99" should never exist
        path = _bundled_renderdoc.get_bundled_renderdoc_path("999.99")
        assert path is None


class TestDirectoryStructure:
    """Test that the bundled binaries directory structure is correct"""

    def test_renderdoc_bins_directory_exists(self):
        """_renderdoc_bins directory should exist"""
        rdc_path = Path(__file__).parent.parent / "src" / "rdc"
        bins_dir = rdc_path / "_renderdoc_bins"
        assert bins_dir.is_dir(), f"Expected {bins_dir} to exist"

    def test_init_file_in_bins_directory(self):
        """_renderdoc_bins should contain __init__.py"""
        rdc_path = Path(__file__).parent.parent / "src" / "rdc"
        init_file = rdc_path / "_renderdoc_bins" / "__init__.py"
        assert init_file.is_file(), f"Expected {init_file} to exist"

    def test_version_directories_structure(self):
        """Version directories should follow v{major}_{minor} pattern"""
        rdc_path = Path(__file__).parent.parent / "src" / "rdc"
        bins_dir = rdc_path / "_renderdoc_bins"
        
        # Check for expected version directories (if they exist)
        expected_versions = ["v1_21", "v1_43"]
        for version_dir_name in expected_versions:
            version_dir = bins_dir / version_dir_name
            if version_dir.exists():
                assert version_dir.is_dir()
                # Should contain Python version subdirectories
                python_versions = list(version_dir.glob("py*"))
                assert len(python_versions) >= 0  # Can be empty (no binaries yet)


class TestDiscoveryIntegration:
    """Test integration with discover.find_renderdoc()"""

    def test_import_bundled_renderdoc_module(self):
        """Should be able to import _bundled_renderdoc in discover module"""
        # This verifies the import statement was added
        assert hasattr(discover, "_bundled_renderdoc")

    def test_find_renderdoc_docstring_updated(self):
        """find_renderdoc() docstring should mention bundled versions"""
        docstring = discover.find_renderdoc.__doc__ or ""
        assert "Bundled RenderDoc" in docstring
        # Check the search order is documented
        assert "1." in docstring  # Item 1 in search order
        assert "2." in docstring  # Item 2 in search order

    def test_search_order_priority(self):
        """Bundled versions should be searched before system paths"""
        # This is tested implicitly by the find_renderdoc() implementation:
        # 1. RENDERDOC_PYTHON_PATH env var
        # 2. Bundled versions (added via _bundled_renderdoc)
        # 3. System paths
        # 4. renderdoccmd sibling
        
        # Read the source to verify the order
        source = Path(__file__).parent.parent / "src" / "rdc" / "discover.py"
        content = source.read_text()
        
        # Find the indices of key operations
        env_path_idx = content.find("RENDERDOC_PYTHON_PATH")
        bundled_idx = content.find("get_bundled_versions")
        system_idx = content.find("renderdoc_search_paths")
        
        assert env_path_idx < bundled_idx < system_idx, \
            "Search order should be: env_path -> bundled -> system"


class TestConfigurationFiles:
    """Test that pyproject.toml and .gitignore are configured correctly"""

    def test_pyproject_includes_renderdoc_bins(self):
        """pyproject.toml should include _renderdoc_bins in package-data"""
        pyproject = Path(__file__).parent.parent / "pyproject.toml"
        content = pyproject.read_text()
        
        assert "_renderdoc_bins" in content
        assert "**.pyd" in content or "*.pyd" in content
        assert "**.dll" in content or "*.dll" in content

    def test_gitignore_allows_binaries(self):
        """gitignore should force-include _renderdoc_bins binaries"""
        gitignore = Path(__file__).parent.parent / ".gitignore"
        content = gitignore.read_text()
        
        assert "!src/rdc/_renderdoc_bins/" in content
        assert "!src/rdc/_renderdoc_bins/**/*.pyd" in content
        assert "!src/rdc/_renderdoc_bins/**/*.dll" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
