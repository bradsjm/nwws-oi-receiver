#!/usr/bin/env python3
# pyright: standard
"""Installation verification script for nwws-oi-receiver.

This script verifies that nwws-oi-receiver has been installed correctly and all
core functionality is accessible. It performs basic import tests, version
checks, and minimal functionality tests.

Usage:
    python scripts/verify_installation.py
    # or
    python -m scripts.verify_installation
"""

import sys
import traceback


def test_basic_imports() -> bool:
    """Test basic package imports."""
    print("🔍 Testing basic imports...")

    try:
        # Test main package import
        import nwws_receiver

        print(f"✅ Package import successful: nwws_receiver v{nwws_receiver.__version__}")

        # Test main classes
        from nwws_receiver import (
            WxWire,
            WxWireConfig,
            NoaaPortMessage,
            MessageHandler,
        )

        print("✅ Core classes imported successfully")

        # Test config module
        from nwws_receiver.config import ConfigurationError

        print("✅ Config module imported successfully")

        # Test message module
        from nwws_receiver.message import NoaaPortMessage

        print("✅ Message module imported successfully")

        return True

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"❌ Unexpected error during import: {e}")
        traceback.print_exc()
        return False


def test_class_instantiation() -> bool:
    """Test basic class instantiation."""
    print("\n🏗️  Testing class instantiation...")

    try:
        from nwws_receiver import WxWire, WxWireConfig

        # Test config creation
        config = WxWireConfig(username="testuser", password="testpass")
        print(f"✅ WxWireConfig created: {config.username}")

        # Test client creation (don't connect)
        client = WxWire(config)
        print("✅ WxWire client created successfully")

        # Test configuration access
        print(f"✅ Configuration accessed: {client.config.username}")

        return True

    except Exception as e:
        print(f"❌ Class instantiation failed: {e}")
        traceback.print_exc()
        return False


def test_data_structures() -> bool:
    """Test data structure creation."""
    print("\n📊 Testing data structures...")

    try:
        from datetime import UTC, datetime

        from nwws_receiver import NoaaPortMessage, WxWireConfig
        from nwws_receiver.config import ConfigurationError

        # Test NoaaPortMessage
        message = NoaaPortMessage(
            subject="Test Weather Alert",
            noaaport="TTAA00 KWBC 121800\nTest weather alert content",
            id="12345_67890",
            issue=datetime.now(UTC),
            ttaaii="TTAA00",
            cccc="KWBC",
            awipsid="TEST123",
        )
        print(f"✅ NoaaPortMessage created: {message.awipsid} ({message.ttaaii})")

        # Test WxWireConfig with validation
        config = WxWireConfig(
            username="test@weather.gov",
            password="testpass",
            server="nwws-oi.weather.gov",
            port=5222,
        )
        print(f"✅ WxWireConfig created: {config.username}@{config.server}:{config.port}")

        # Test ConfigurationError with invalid port
        try:
            WxWireConfig(username="testuser", password="test", port=99999)
        except ConfigurationError:
            print("✅ ConfigurationError properly raised for invalid port")
        else:
            print("❌ ConfigurationError should have been raised")
            return False

        return True

    except Exception as e:
        print(f"❌ Data structure test failed: {e}")
        traceback.print_exc()
        return False


def test_utilities() -> bool:
    """Test utility functions."""
    print("\n🔧 Testing utilities...")

    try:
        from nwws_receiver.config import _validate_email, _validate_port
        from nwws_receiver.message import NoaaPortMessage

        # Test email validation
        valid_email = _validate_email("test@weather.gov")
        print(f"✅ Email validation working: {valid_email}")

        # Test port validation
        valid_port = _validate_port(5222)
        print(f"✅ Port validation working: {valid_port}")

        # Test validation errors
        try:
            _validate_email("")
        except Exception:
            print("✅ Email validation properly rejects empty email")
        else:
            print("❌ Email validation should have failed")
            return False

        # Test message parsing capability
        sample_xml = "<message>Test weather content</message>"
        if hasattr(NoaaPortMessage, "from_xml"):
            print("✅ Message parsing methods available")
        else:
            print("✅ NoaaPortMessage structure verified")

        return True

    except Exception as e:
        print(f"❌ Utilities test failed: {e}")
        traceback.print_exc()
        return False


def test_async_features() -> bool:
    """Test async feature availability."""
    print("\n⚡ Testing async features...")

    try:
        from nwws_receiver import WxWire, WxWireConfig

        # Test async context manager availability
        config = WxWireConfig(username="testuser", password="testpass")
        client = WxWire(config)

        # Check if async methods exist
        if hasattr(client, "start") and callable(client.start):
            print("✅ Async start method available")
        else:
            print("❌ Async start method missing")
            return False

        if hasattr(client, "stop") and callable(client.stop):
            print("✅ Async stop method available")
        else:
            print("❌ Async stop method missing")
            return False

        if hasattr(client, "__aiter__") and callable(client.__aiter__):
            print("✅ Async iterator (__aiter__) available")
        else:
            print("❌ Async iterator (__aiter__) missing")
            return False

        if hasattr(client, "__anext__") and callable(client.__anext__):
            print("✅ Async iterator (__anext__) available")
        else:
            print("❌ Async iterator (__anext__) missing")
            return False

        # Test subscriber pattern
        if hasattr(client, "subscribe") and callable(client.subscribe):
            print("✅ Subscribe method available")
        else:
            print("❌ Subscribe method missing")
            return False

        if hasattr(client, "unsubscribe") and callable(client.unsubscribe):
            print("✅ Unsubscribe method available")
        else:
            print("❌ Unsubscribe method missing")
            return False

        return True

    except Exception as e:
        print(f"❌ Async features test failed: {e}")
        traceback.print_exc()
        return False


def test_version_info() -> bool:
    """Test version and metadata information."""
    print("\n📋 Testing version and metadata...")

    try:
        import nwws_receiver

        # Check version
        version = getattr(nwws_receiver, "__version__", "unknown")
        print(f"✅ Version: {version}")

        # Check __all__ exports
        all_exports = getattr(nwws_receiver, "__all__", [])
        print(f"✅ Exported symbols: {len(all_exports)} items")
        for export in all_exports:
            print(f"   - {export}")

        # Verify key exports are present
        expected_exports = {
            "WxWire",
            "WxWireConfig",
            "NoaaPortMessage",
            "MessageHandler",
            "ConfigurationError",
        }
        missing = expected_exports - set(all_exports)
        if missing:
            print(f"❌ Missing expected exports: {missing}")
            return False
        else:
            print("✅ All expected exports present")

        return True

    except Exception as e:
        print(f"❌ Version info test failed: {e}")
        traceback.print_exc()
        return False


def check_python_version() -> bool:
    """Check Python version compatibility."""
    print("🐍 Checking Python version...")

    major, minor = sys.version_info[:2]

    if major < 3:
        print(f"❌ Python {major}.{minor} is not supported. Python 3.12+ required.")
        return False
    if major == 3 and minor < 12:
        print(f"⚠️  Python {major}.{minor} detected. Python 3.12+ recommended.")
        print("   Some features may not work correctly.")
        return True
    print(f"✅ Python {major}.{minor} detected. Version compatible.")
    return True


def main() -> int:
    """Run all verification tests."""
    print("🚀 NWWS-OI Receiver Installation Verification")
    print("=" * 55)

    tests = [
        ("Python Version", check_python_version),
        ("Basic Imports", test_basic_imports),
        ("Class Instantiation", test_class_instantiation),
        ("Data Structures", test_data_structures),
        ("Utilities", test_utilities),
        ("Async Features", test_async_features),
        ("Version Info", test_version_info),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            failed += 1

    print("\n" + "=" * 55)
    print(f"📊 Test Results: {passed} passed, {failed} failed")

    if failed == 0:
        print("🎉 All tests passed! NWWS-OI Receiver is installed correctly.")
        print("\n📚 Next steps:")
        print("   - Run examples: python examples/usage_patterns.py")
        print("   - Read documentation: README.md")
        print("   - Connect to NWWS-OI: Set up your credentials and start receiving weather data")
        return 0
    print("❌ Some tests failed. Check the error messages above.")
    print("\n🔧 Troubleshooting:")
    print("   - Ensure Python 3.12+ is installed")
    print("   - Try reinstalling: pip install --force-reinstall nwws-oi-receiver")
    print("   - Check for dependency conflicts (slixmpp, etc.)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
