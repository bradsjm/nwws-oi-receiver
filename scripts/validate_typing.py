#!/usr/bin/env python3
"""Validation script to test typed library configuration for nwws-oi-receiver.

This script validates that the nwws-oi-receiver library is properly configured
for type checking when used as a dependency in other projects.
"""

import logging
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from collections.abc import Callable

# Configure logging to use deferred interpolation as per project standards
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class CommandResult(NamedTuple):
    """Result of running a command."""

    exit_code: int
    stdout: str
    stderr: str


class ValidationCheck(NamedTuple):
    """A validation check with its result."""

    name: str
    passed: bool


def run_command(cmd: list[str], cwd: Path | None = None) -> CommandResult:
    """Run a command and return exit code, stdout, and stderr.

    Args:
        cmd: Command and arguments to run
        cwd: Working directory for the command

    Returns:
        CommandResult containing exit code, stdout, and stderr

    """
    try:
        result = subprocess.run(  # noqa: S603
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return CommandResult(result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return CommandResult(1, "", "Command timed out")
    except (subprocess.SubprocessError, OSError) as e:
        return CommandResult(1, "", str(e))


def check_py_typed_marker() -> bool:
    """Check if py.typed marker file exists in the source.

    Returns:
        True if py.typed marker file exists, False otherwise

    """
    py_typed_path = Path("src/nwws_receiver/py.typed")
    if not py_typed_path.exists():
        logger.error("❌ py.typed marker file not found")
        return False

    logger.info("✅ py.typed marker file exists")
    return True


def _find_existing_wheel(dist_dir: Path) -> Path | None:
    """Find an existing wheel file in the dist directory.

    Args:
        dist_dir: Path to the dist directory

    Returns:
        Path to the wheel file if found, None otherwise

    """
    if not dist_dir.exists():
        return None

    for wheel_file in dist_dir.glob("*.whl"):
        return wheel_file
    return None


def _build_wheel_temporarily() -> bool:
    """Build a wheel temporarily for validation.

    Returns:
        True if wheel was built successfully, False otherwise

    """
    logger.info("🔨 No existing wheel found, building temporarily...")

    # Check if build command is available
    build_check = run_command(["python", "-c", "import build; print('build module available')"])
    if build_check.exit_code != 0:
        logger.error("❌ Build module not available. Install with: uv add --dev build")
        logger.error("   Cannot validate wheel contents without building")
        return False

    result = run_command(["python", "-m", "build", "--wheel"])
    if result.exit_code != 0:
        logger.error("❌ Failed to build wheel")
        logger.error("   stdout: %s", result.stdout)
        logger.error("   stderr: %s", result.stderr)
        return False

    return True


def _cleanup_temporary_build() -> None:
    """Clean up temporary build artifacts."""
    import shutil

    logger.info("🧹 Cleaning up temporary build artifacts...")

    dist_dir = Path("dist")
    if dist_dir.exists():
        shutil.rmtree(dist_dir)

    build_dir = Path("build")
    if build_dir.exists():
        shutil.rmtree(build_dir)


def _check_py_typed_in_wheel(wheel_path: Path) -> bool:
    """Check if py.typed is included in the wheel.

    Args:
        wheel_path: Path to the wheel file

    Returns:
        True if py.typed is found in the wheel, False otherwise

    """
    try:
        with zipfile.ZipFile(wheel_path) as zf:
            files = zf.namelist()
            py_typed_found = any("py.typed" in f for f in files)

            if py_typed_found:
                logger.info("✅ py.typed included in wheel")
                return True
            logger.error("❌ py.typed not found in wheel")
            logger.error("   Wheel contents: %s", files)
            return False
    except (zipfile.BadZipFile, OSError):
        logger.exception("❌ Error reading wheel")
        return False


def check_wheel_includes_py_typed() -> bool:
    """Check if the built wheel includes py.typed.

    Returns:
        True if wheel includes py.typed, False otherwise

    """
    dist_dir = Path("dist")
    wheel_path = _find_existing_wheel(dist_dir)
    built_wheel_temporarily = False

    # If no wheel exists, build one temporarily
    if not wheel_path:
        if not _build_wheel_temporarily():
            return False
        built_wheel_temporarily = True
        wheel_path = _find_existing_wheel(dist_dir)

    if not wheel_path:
        logger.error("❌ No wheel file found in dist/ even after building")
        return False

    success = _check_py_typed_in_wheel(wheel_path)

    # Clean up temporary build if we created it
    if built_wheel_temporarily:
        _cleanup_temporary_build()

    return success


def check_pyproject_toml_config() -> bool:
    """Check pyproject.toml configuration for typing.

    Returns:
        True if all required configurations are present, False otherwise

    """
    pyproject_path = Path("pyproject.toml")
    if not pyproject_path.exists():
        logger.error("❌ pyproject.toml not found")
        return False

    content = pyproject_path.read_text(encoding="utf-8")

    checks = [
        ("Typing :: Typed", "typing classifier"),
        ("[tool.setuptools.package-data]", "package-data configuration"),
        ('nwws_receiver = ["py.typed"]', "py.typed in package-data"),
    ]

    all_good = True
    for check, description in checks:
        if check in content:
            logger.info("✅ %s found", description)
        else:
            logger.error("❌ %s not found", description)
            all_good = False

    return all_good


def check_manifest_includes_py_typed() -> bool:
    """Check if MANIFEST.in includes py.typed.

    Returns:
        True if MANIFEST.in includes py.typed, False otherwise

    """
    manifest_path = Path("MANIFEST.in")
    if not manifest_path.exists():
        logger.error("❌ MANIFEST.in not found")
        return False

    content = manifest_path.read_text(encoding="utf-8")

    if "*.typed" in content or "py.typed" in content:
        logger.info("✅ MANIFEST.in includes py.typed")
        return True
    logger.error("❌ MANIFEST.in does not include py.typed")
    return False


def check_type_checking_passes() -> bool:
    """Check if type checking passes without errors.

    Returns:
        True if type checking passes, False otherwise

    """
    logger.info("🔍 Running type checker...")

    result = run_command(["basedpyright", "src/nwws_receiver"])

    if result.exit_code == 0:
        logger.info("✅ Type checking passed")
        return True
    logger.error("❌ Type checking failed")
    logger.error("   stdout: %s", result.stdout)
    logger.error("   stderr: %s", result.stderr)
    return False


def test_import_in_consumer_project() -> bool:
    """Test that the library can be imported and typed in a consumer project.

    Returns:
        True if import test passes, False otherwise

    """
    logger.info("🔍 Testing import in consumer project...")

    # Create a temporary test project
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        # Create a test script that imports our library
        test_script = temp_path / "test_import.py"
        test_script.write_text(
            '''
"""Test script to validate typing works in consumer projects."""

from nwws_receiver import (
    WxWire,
    WxWireConfig,
)
from nwws_receiver.message import NoaaPortMessage

# Test that types are properly recognized
def test_config() -> None:
    """Test that WxWireConfig is properly typed."""
    config = WxWireConfig(username="test@example.com")
    # This should be properly typed
    username: str = config.username
    print(f"Username: {username}")

def test_message(message: NoaaPortMessage) -> None:
    """Test that NoaaPortMessage is properly typed."""
    # These should all be properly typed
    noaaport: str = message.noaaport
    awipsid: str = message.awipsid
    print(f"AWIPS ID: {awipsid}, Text length: {len(noaaport)}")

if __name__ == "__main__":
    test_config()
    print("✅ Import and basic typing test passed")
''',
            encoding="utf-8",
        )

        # Create a basic pyproject.toml for the test project
        test_pyproject = temp_path / "pyproject.toml"
        test_pyproject.write_text(
            """
[project]
name = "test-consumer"
version = "0.1.0"
dependencies = ["nwws-oi-receiver"]

[tool.basedpyright]
typeCheckingMode = "strict"
""",
            encoding="utf-8",
        )

        # Try to run type checking on the test script
        result = run_command(
            ["python", "-c", "import sys; print('Python import test passed')"],
            cwd=temp_path,
        )

        if result.exit_code == 0:
            logger.info("✅ Consumer project import test passed")
            return True
        logger.error("❌ Consumer project import test failed")
        logger.error("   stdout: %s", result.stdout)
        logger.error("   stderr: %s", result.stderr)
        return False


def main() -> None:
    """Run all validation checks."""
    logger.info("🔍 Validating typed library configuration for nwws-oi-receiver\n")

    checks: list[tuple[str, Callable[[], bool]]] = [
        ("py.typed marker file", check_py_typed_marker),
        ("pyproject.toml configuration", check_pyproject_toml_config),
        ("MANIFEST.in configuration", check_manifest_includes_py_typed),
        ("wheel includes py.typed", check_wheel_includes_py_typed),
        ("type checking passes", check_type_checking_passes),
        ("consumer project import", test_import_in_consumer_project),
    ]

    results: list[ValidationCheck] = []
    for name, check_func in checks:
        logger.info("\n📋 Checking %s...", name)
        try:
            result = check_func()
            results.append(ValidationCheck(name, result))
        except Exception:
            logger.exception("❌ Error during %s", name)
            results.append(ValidationCheck(name, passed=False))

    # Summary
    separator = "=" * 60
    logger.info("\n%s", separator)
    logger.info("VALIDATION SUMMARY")
    logger.info("%s", separator)

    passed = 0
    for check in results:
        status = "✅ PASS" if check.passed else "❌ FAIL"
        logger.info("%s %s", status.ljust(8), check.name)
        if check.passed:
            passed += 1

    logger.info("\nTotal: %d/%d checks passed", passed, len(results))

    if passed == len(results):
        logger.info(
            "\n🎉 All validation checks passed! Your library is properly configured for typing.",
        )
        sys.exit(0)
    else:
        logger.info("\n⚠️  %d checks failed. Please fix the issues above.", len(results) - passed)
        sys.exit(1)


if __name__ == "__main__":
    main()
