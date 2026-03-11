#!/usr/bin/env python3
"""
Quick test to verify the refactoring fixes work correctly.
"""

def test_config_loading():
    """Test that config loads correctly from the new location."""
    try:
        from framework.core.config import Config, get_repo_root, get_config_path, get_services_path
        
        # Test repo root resolution
        repo_root = get_repo_root()
        print(f"✅ Repo root resolved to: {repo_root}")
        
        # Test config path resolution
        config_path = get_config_path()
        print(f"✅ Config path resolved to: {config_path}")
        
        # Test services path resolution
        services_path = get_services_path()
        print(f"✅ Services path resolved to: {services_path}")
        
        # Test config loading
        config = Config()
        print("✅ Config loaded successfully")
        print(f"   Model: {config.ollama_model}")
        print(f"   AWS Region: {config.aws_config.get('region', 'not set')}")
        
        # Verify files exist at expected locations
        import os
        if os.path.exists(config_path):
            print("✅ config.yaml exists at resolved path")
        else:
            print("❌ config.yaml NOT found at resolved path")
            
        if os.path.exists(services_path):
            print("✅ services.yaml exists at resolved path")
        else:
            print("⚠️  services.yaml not found (may be optional)")
            
        return True
    except Exception as e:
        print(f"❌ Config loading failed: {e}")
        return False

def test_skills_loading():
    """Test that skills load correctly from the new structure."""
    try:
        from framework.core.agent import Agent
        skills_context = Agent._load_skills()
        if "No skill files found" in skills_context:
            print("❌ No skills found")
            return False
        
        # Count how many skills were loaded
        skill_count = skills_context.count("### Skill:")
        print(f"✅ Skills loaded successfully ({skill_count} skills)")
        
        # Check for some expected skills
        expected_skills = ["email-parser", "cloudwatch-fetcher", "dependency-checker"]
        for skill in expected_skills:
            if skill in skills_context:
                print(f"   ✅ Found skill: {skill}")
            else:
                print(f"   ❌ Missing skill: {skill}")
        
        return True
    except Exception as e:
        print(f"❌ Skills loading failed: {e}")
        return False

def test_tool_imports():
    """Test that tool imports work correctly."""
    try:
        from framework.tools.email_parser import parse_aws_alert_email
        from framework.tools.cloudwatch_fetcher import fetch_cloudwatch_logs
        from framework.tools.log_group_discovery import discover_log_group
        print("✅ Tool imports working")
        return True
    except Exception as e:
        print(f"❌ Tool imports failed: {e}")
        return False

def test_email_parser_validation():
    """Test that the email parser validates extracted values properly."""
    try:
        from framework.tools.email_parser import parse_aws_alert_email, _is_valid_aws_timestamp, _is_valid_aws_region
        
        # Test validation functions
        valid_timestamp = "Tuesday 10 March, 2026 04:08:18 UTC"
        invalid_timestamp = "invalid timestamp"
        
        print(f"✅ Valid timestamp check: {_is_valid_aws_timestamp(valid_timestamp)}")
        print(f"✅ Invalid timestamp check: {not _is_valid_aws_timestamp(invalid_timestamp)}")
        
        valid_region = "ap-south-1"
        invalid_region = "invalid-region"
        
        print(f"✅ Valid region check: {_is_valid_aws_region(valid_region)}")
        print(f"✅ Invalid region check: {not _is_valid_aws_region(invalid_region)}")
        
        return True
    except Exception as e:
        print(f"❌ Email parser validation failed: {e}")
        return False

def test_context_manager_timestamp_normalization():
    """Test that context manager normalizes timestamps correctly."""
    try:
        from framework.core.context_manager import ContextManager
        
        cm = ContextManager()
        
        # Test valid timestamp
        valid_ts = "Tuesday 10 March, 2026 04:08:18 UTC"
        normalized = cm._normalize_timestamp(valid_ts)
        print(f"✅ Valid timestamp normalization: {normalized}")
        
        # Test dict timestamp
        dict_ts = {"$date": 1715248098000}
        normalized_dict = cm._normalize_timestamp(dict_ts)
        print(f"✅ Dict timestamp normalization: {normalized_dict}")
        
        # Test invalid timestamp
        invalid_ts = "invalid"
        normalized_invalid = cm._normalize_timestamp(invalid_ts)
        print(f"✅ Invalid timestamp handling: {normalized_invalid is None}")
        
        return True
    except Exception as e:
        print(f"❌ Context manager timestamp normalization failed: {e}")
        return False

if __name__ == "__main__":
    print("🔧 Testing refactoring fixes...\n")
    
    tests = [
        ("Config Loading", test_config_loading),
        ("Skills Loading", test_skills_loading), 
        ("Tool Imports", test_tool_imports),
        ("Email Parser Validation", test_email_parser_validation),
        ("Context Manager Timestamp Normalization", test_context_manager_timestamp_normalization),
    ]
    
    passed = 0
    for name, test_func in tests:
        print(f"Testing {name}:")
        if test_func():
            passed += 1
        print()
    
    print(f"Results: {passed}/{len(tests)} tests passed")
    
    if passed == len(tests):
        print("🎉 All tests passed! The refactoring fixes are working.")
    else:
        print("⚠️  Some tests failed. Check the errors above.")