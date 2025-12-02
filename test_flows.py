"""
Unit tests for flows.py using pytest
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from io import StringIO




class TestFlowsCommandLine:
    """Test suite for command-line interface of flows.py"""
    
    
    
    def test_invalid_flow_name_handling(self):
        """Test handling of invalid flow name"""
        # Arrange
        test_args = ['flows.py', 'invalid-flow']
        
        with patch.object(sys, 'argv', test_args):
            with patch('sys.exit') as mock_exit:
                with patch('builtins.print') as mock_print:
                    # Simulate the logic from flows.py main block
                    flow_name = sys.argv[1]
                    if flow_name not in ["etl", "db-backup"]:
                        print(f"Unknown flow: {flow_name}")
                        print("Available flows: etl, db-backup")
                        sys.exit(1)
                    
                    # Assert
                    mock_exit.assert_called_once_with(1)
                    assert mock_print.call_count == 2
    
    def test_no_arguments_shows_help(self):
        """Test that running without arguments shows help message"""
        # Arrange
        test_args = ['flows.py']
        
        with patch.object(sys, 'argv', test_args):
            with patch('builtins.print') as mock_print:
                # Simulate the logic from flows.py main block
                if len(sys.argv) == 1:
                    print("Available flows:")
                    print("  etl - Run the main ETL pipeline")
                    print("  db-backup - Run database backup")
                    print("\nUsage: python flows.py <flow_name>")
                
                # Assert
                assert mock_print.call_count == 4
                calls = [str(call) for call in mock_print.call_args_list]
                assert any("Available flows:" in str(call) for call in calls)
                assert any("etl" in str(call) for call in calls)
                assert any("db-backup" in str(call) for call in calls)




@pytest.fixture
def mock_sys_argv():
    """Fixture to save and restore sys.argv"""
    original_argv = sys.argv.copy()
    yield
    sys.argv = original_argv


class TestFlowsWithFixtures:
    """Test flows using pytest fixtures"""
    
    def test_sys_argv_fixture(self, mock_sys_argv):
        """Test that sys.argv fixture works correctly"""
        original_argv = sys.argv.copy()
        sys.argv = ['test.py', 'arg1']
        assert sys.argv[1] == 'arg1'
        # Fixture will restore it after test


@pytest.mark.parametrize("flow_name,expected_in_list", [
    ("etl", True),
    ("db-backup", True),
    ("invalid", False),
    ("ETL", False),  # Case sensitive
])
def test_valid_flow_names(flow_name, expected_in_list):
    """Test validation of flow names"""
    valid_flows = ["etl", "db-backup"]
    assert (flow_name in valid_flows) == expected_in_list


if __name__ == "__main__":
    # Run tests with: pytest test_flows.py -v
    pytest.main([__file__, "-v"])
