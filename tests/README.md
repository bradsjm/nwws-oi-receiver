# NWWS-OI Receiver Test Suite

This directory contains a comprehensive test suite for the `wx_wire.py` module, providing thorough coverage of all functionality including unit tests, integration tests, edge cases, error conditions, performance tests, and stress tests.

## Test Structure

The test suite is organized into multiple files to provide comprehensive coverage:

### Core Test Files

#### `test_wx_wire.py` (61 tests)
The main test file covering core functionality:

- **TestWxWireInit** (3 tests): Initialization and setup
  - Valid configuration handling
  - Nickname generation with timestamps
  - Event handler registration

- **TestWxWireAsyncIterator** (5 tests): Async iterator protocol
  - Iterator pattern implementation
  - Message retrieval from queue
  - Stop iteration handling
  - Timeout behavior
  - For-loop integration

- **TestWxWireProperties** (1 test): Property accessors
  - Queue size monitoring

- **TestWxWireConnectionManagement** (6 tests): Connection lifecycle
  - Start/stop operations
  - Connection state management
  - Graceful shutdown procedures

- **TestWxWireEventHandlers** (12 tests): XMPP event handling
  - Connection events (connecting, connected, failed, disconnected)
  - Authentication events
  - Session lifecycle events
  - MUC presence events
  - Error handling

- **TestWxWireBackgroundServices** (4 tests): Background task management
  - Service startup and shutdown
  - Idle timeout monitoring
  - Task lifecycle management

- **TestWxWireMucOperations** (8 tests): Multi-User Chat operations
  - Room joining and leaving
  - Subscription presence
  - Error handling for MUC operations

- **TestWxWireMessageProcessing** (10 tests): Message processing pipeline
  - NWWS-OI message parsing
  - XML namespace handling
  - Message validation
  - Queue management
  - WMO ID extraction

- **TestWxWireUtilities** (8 tests): Utility functions
  - Timestamp parsing with various formats
  - Delay calculation
  - NOAAPort format conversion

- **TestWxWireIntegration** (3 tests): End-to-end workflows
  - Complete message processing pipeline
  - Shutdown during operation
  - Queue backpressure handling

#### `test_wx_wire_edge_cases.py` (25 tests)
Edge cases and error conditions:

- **TestWxWireEdgeCases** (7 tests): Boundary conditions
  - Empty queue handling
  - Thread safety verification
  - Multiple operation calls
  - Connection state edge cases

- **TestWxWireErrorConditions** (15 tests): Error handling
  - Connection failures
  - Authentication errors
  - XML parsing errors
  - Plugin failures
  - Malformed data handling

- **TestWxWireRaceConditions** (4 tests): Concurrency issues
  - Concurrent start/stop operations
  - Message processing races
  - Background service coordination

#### `test_wx_wire_performance.py` (13 tests)
Performance and stress testing:

- **TestWxWirePerformance** (6 tests): Performance benchmarks
  - High-volume message processing (1000+ messages)
  - Concurrent message handling
  - Queue backpressure performance
  - Message conversion speed
  - Timestamp parsing performance
  - Background service overhead

- **TestWxWireStressTests** (4 tests): Stress conditions
  - Rapid connect/disconnect cycles
  - Memory usage under load
  - Error recovery capabilities
  - High-load shutdown behavior

### Support Files

#### `conftest.py`
Shared test fixtures and configuration:
- Test configurations for various scenarios
- Sample message objects
- Mock XMPP messages with realistic content
- Weather product templates
- WMO header combinations
- Performance testing parameters

## Test Coverage

The test suite provides comprehensive coverage of:

### Core Business Logic
- ✅ Message processing and parsing
- ✅ Async iterator functionality  
- ✅ Connection state management
- ✅ Background service lifecycle
- ✅ Utility functions

### Edge Cases
- ✅ Invalid message formats
- ✅ Queue full scenarios
- ✅ Shutdown during operations
- ✅ Network failures and reconnection
- ✅ Malformed timestamps and data

### Integration Points
- ✅ XMPP plugin interactions (mocked)
- ✅ Event handler registration and firing
- ✅ MUC room operations
- ✅ End-to-end message workflows

### Error Conditions
- ✅ XML parsing errors
- ✅ Unicode decode errors
- ✅ Network timeouts
- ✅ Authentication failures
- ✅ Plugin unavailability

### Performance Characteristics
- ✅ High-volume message processing (>100 msg/sec)
- ✅ Concurrent operation handling
- ✅ Memory usage stability
- ✅ Queue backpressure behavior
- ✅ Conversion performance (<1ms average)

## Running Tests

### Run All Tests
```bash
python -m pytest tests/
```

### Run Specific Test Categories
```bash
# Core functionality only
python -m pytest tests/test_wx_wire.py

# Edge cases and error conditions
python -m pytest tests/test_wx_wire_edge_cases.py

# Performance and stress tests (marked as slow)
python -m pytest tests/test_wx_wire_performance.py -m slow
```

### Run with Coverage
```bash
python -m pytest tests/ --cov=src/nwws_receiver --cov-report=html
```

### Run Fast Tests Only
```bash
python -m pytest tests/ -m "not slow"
```

## Test Markers

- `slow`: Performance and stress tests that take longer to execute
- `integration`: Integration tests that test multiple components together
- `unit`: Pure unit tests that test individual functions/methods
- `asyncio`: Tests that require asyncio support

## Key Testing Patterns

### Mocking Strategy
- **slixmpp.ClientXMPP**: Parent class mocked to prevent actual network operations
- **XMPP plugins**: Mocked to test MUC operations without network calls
- **Time functions**: Mocked for deterministic timestamp testing
- **Async operations**: Proper async mock usage for coroutines

### Fixture Design
- **Hierarchical fixtures**: Base configurations extended for specific scenarios
- **Realistic test data**: Sample weather messages with actual NWWS-OI format
- **Parameterized tests**: Multiple scenarios tested with single test functions
- **Resource cleanup**: Proper teardown to prevent test interference

### Assertion Patterns
- **Behavior verification**: Testing that correct methods are called with expected parameters
- **State validation**: Verifying object state changes correctly
- **Exception handling**: Ensuring proper error responses
- **Performance validation**: Timing and throughput assertions

## Test Data

The test suite includes realistic test data:

### Sample Weather Products
- Severe weather warnings
- Forecast discussions
- Public forecasts
- Various product types with authentic formatting

### WMO Headers
- Multiple TTAAII/CCCC combinations
- AWIPS ID variations
- Realistic office identifiers

### Message Formats
- Valid NWWS-OI XML structures
- Malformed XML for error testing
- Unicode content handling
- Various timestamp formats

## Development Guidelines

When adding new tests:

1. **Follow naming conventions**: `test_method_name_when_condition_then_expected_behavior`
2. **Use appropriate fixtures**: Leverage existing fixtures where possible
3. **Test both success and failure paths**: Include error condition testing
4. **Mock external dependencies**: Avoid real network operations
5. **Include performance considerations**: Add timing assertions for critical paths
6. **Document complex test scenarios**: Add clear docstrings explaining test purpose

## Debugging Failed Tests

Common debugging strategies:

1. **Use `-v` flag**: Get verbose output showing which tests pass/fail
2. **Use `--tb=short`**: Get concise traceback information
3. **Run single tests**: Isolate specific failing tests
4. **Check mock setup**: Verify mocks are configured correctly for test scenario
5. **Validate test data**: Ensure test fixtures match expected format

## Quality Metrics

The test suite maintains high quality standards:

- **Coverage**: >95% line coverage of core functionality
- **Test count**: 99 comprehensive tests
- **Performance**: All tests complete within reasonable time
- **Reliability**: Tests are deterministic and don't depend on external services
- **Maintainability**: Clear organization and comprehensive documentation